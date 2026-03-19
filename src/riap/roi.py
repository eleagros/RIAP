"""ROI selection, mask propagation, and folder discovery utilities for RIAP."""

from pathlib import Path
import shutil
import tifffile as tiff
from PIL import Image
import numpy as np
import re
import copy
import cv2
import pickle

from riap.alignment import run_alignment_pipeline, OpenCVAligner
from riap.visualization import create_alignment_gif


def get_masks(
        path: str,
        default_path_polarimetry: str,
        priority: list = ['wm', 'gm'],
        base_folder=None,
        cfg=None,
        base_folder_mask=None
    ):
    annotation_path = path / 'annotation'
    out_path = annotation_path / 'all_merged.tif'

    angle_correction = get_angle_correction(annotation_path)
    camera_correction = get_camera_correction(annotation_path)

    values = {'wm': 255, 'gm': 128, 'bg': 0}
    masks = {}

    gm_files = sorted([f for f in annotation_path.glob('*.tif') if re.match(r'[Gg][Mm]_\d{2}\.tif$', f.name)])
    wm_files = sorted([f for f in annotation_path.glob('*.tif') if re.match(r'[Ww][Mm]_\d{2}\.tif$', f.name)])
    bg_files = sorted([f for f in annotation_path.glob('*.tif') if re.match(r'[Bb][Gg]_\d{2}\.tif$', f.name)])

    if not gm_files or not wm_files:
        if not base_folder:
            if out_path.exists():
                return np.array(Image.open(out_path))
            raise FileNotFoundError("No GM_XX.tif or WM_XX.tif files found in annotation folder.")
        all_merged = propagate_labels(
            path,
            base_folder,
            default_path_polarimetry,
            annotation_path,
            cfg,
            base_folder_mask
        )
    else:
        gm_stack = [tiff.imread(f) for f in gm_files]
        wm_stack = [tiff.imread(f) for f in wm_files]
        bg_stack = [tiff.imread(f) for f in bg_files] if bg_files else []

        ref_shape = gm_stack[0].shape
        if any(m.shape != ref_shape for m in gm_stack + wm_stack + bg_stack):
            raise ValueError("All GM, WM, and BG masks must have the same shape.")
        masks['gm'] = np.clip(np.sum(gm_stack, axis=0), 0, 255).astype(np.uint8)
        masks['wm'] = np.clip(np.sum(wm_stack, axis=0), 0, 255).astype(np.uint8)
        if bg_stack:
            masks['bg'] = np.clip(np.sum(bg_stack, axis=0), 0, 255).astype(np.uint8)
            masks['bg'] = np.logical_or(masks['bg'], (masks['wm'] == 0) & (masks['gm'] == 0)) * 255
        else:
            masks['bg'] = ((masks['wm'] == 0) & (masks['gm'] == 0)) * 255
        masks['bg'] = masks['bg'].astype(np.uint8)

        all_merged = np.zeros(masks['bg'].shape, dtype=np.uint8)
        for key in priority:
            all_merged[np.logical_and(masks[key] == 255, all_merged == 0)] = values[key]
        all_merged[masks['bg'] == 255] = values['bg']

        out_path = annotation_path / 'all_merged_original.tif'
        Image.fromarray(all_merged).save(out_path)

        if camera_correction == 'h':
            all_merged = all_merged[::-1, :]
        elif camera_correction == 'v':
            all_merged = all_merged[:, ::-1]
        elif camera_correction != '':
            raise ValueError(f"Invalid camera correction value: {camera_correction}. Expected 'h', 'v', or ''.")

        if angle_correction == 180:
            all_merged = all_merged[::-1, ::-1]
        elif angle_correction != 0:
            raise ValueError(f"Invalid angle correction value: {angle_correction}. Expected 0 or 180.")

    Image.fromarray(all_merged).save(out_path)

    img = Image.open(path / default_path_polarimetry / 'Intensity_img.png')
    img_blended = Image.blend(img.convert("RGBA"), Image.fromarray(all_merged).convert("RGBA"), alpha=0.05)
    img_blended.save(annotation_path / 'all_merged_blended.png')

    return all_merged


def propagate_labels(
    path,
    base_folder,
    default_path_polarimetry,
    annotation_path,
    cfg,
    base_folder_mask
):
    image1 = cv2.imread(str(path.parent / base_folder / default_path_polarimetry / 'Intensity_img.png'))
    image0 = cv2.imread(str(Path(path) / default_path_polarimetry / 'Intensity_img.png'))

    out_dir = annotation_path / 'propagation_masks'
    out_dir.mkdir(exist_ok=True, parents=True)

    if (annotation_path / 'propagation_masks' / 'warping_function.pickle').exists():
        with open(annotation_path / 'propagation_masks' / 'warping_function.pickle', "rb") as file_obj:
            warping_function = pickle.load(file_obj)
    else:
        _, _, results = run_alignment_pipeline(cfg, path, image0, image1, out_dir, out_dir)
        warping_function = results[-2]

    path_propagation_masks = annotation_path / 'propagation_masks'
    path_to_propagate = path_propagation_masks / 'to_propagate'
    path_to_propagate.mkdir(exist_ok=True, parents=True)
    cv2.imwrite(str(path_to_propagate / 'mask.png'), base_folder_mask)
    cv2.imwrite(str(path_to_propagate / 'intensity_img.png'), image1)

    with open(path_propagation_masks / 'warping_function.pickle', "wb") as file_obj:
        pickle.dump(warping_function, file_obj)

    aligner = OpenCVAligner(
        path_propagation_masks,
        path_propagation_masks,
        path_to_propagate,
        warping_function,
        None
    )
    aligner.run()

    cv2.imwrite(
        str(path_propagation_masks / 'all_merged_original.tif'),
        cv2.imread(str(path_propagation_masks / 'mask_warped.png'))
    )
    all_merged = cv2.imread(str(path_propagation_masks / 'all_merged_original.tif'), cv2.IMREAD_GRAYSCALE)
    create_alignment_gif(
        image0,
        np.array(Image.open(str(path_propagation_masks / 'intensity_img_warped.png'))),
        path_propagation_masks / 'gif_registered.gif',
        n_frames=20,
        duration=0.1
    )
    return all_merged


def get_angle_correction(path: str) -> int:
    path = Path(path)
    file_path = path / 'rotation_MM.txt'

    if file_path.exists():
        try:
            with file_path.open() as file_obj:
                return int(file_obj.readline().strip())
        except (FileNotFoundError, ValueError):
            return 0
    return 0


def get_camera_correction(path: str) -> int:
    path = Path(path)
    primary_path = path / 'correct_intensities.txt'

    if primary_path.exists():
        try:
            with primary_path.open() as file_obj:
                return file_obj.readline().strip()
        except (FileNotFoundError, ValueError):
            return ''
    return ''


def get_square_coordinates(mask, mask_pixels, square_size, grid, coordinates=None, treshold_valid_pixels=0.95):
    found = False
    counter = 0
    while not found and counter < 1000:
        random_row, random_col = get_random_pixel(mask)
        if mask[random_row, random_col] == 0:
            counter += 1
            continue
        region, region_pixels, region_saturation, grided, coordinates = select_region(
            mask.shape, mask, mask_pixels, random_row, random_col, square_size, grid
        )
        positive = (
            region.shape[0] * region.shape[1] == np.sum(region)
            and np.sum(region_saturation) == np.sum(region)
            and np.sum(grided) == 0
            and np.sum(region_pixels) > treshold_valid_pixels * region.shape[0] * region.shape[1]
        )

        if positive:
            found = True
            grid = update_grid(grid, coordinates)
        counter += 1
    if found:
        return coordinates, grid
    return None, grid


def get_random_pixel(mask):
    random_row = np.random.randint(mask.shape[0])
    random_col = np.random.randint(mask.shape[1])
    return random_row, random_col


def select_region(shape, mask, mask_pixels, idx, idy, square_size, grid, border=1.5, offset=15):
    max_x, min_x = None, None
    max_y, min_y = None, None
    if idx - border * (square_size // 2 + 1) - offset < 0:
        min_x = offset
        max_x = square_size + offset
    if idy - border * (square_size // 2 + 1) - offset < 0:
        min_y = offset
        max_y = square_size + offset
    if idx + border * (square_size // 2 + 1) + offset > shape[0]:
        min_x = shape[0] - square_size - offset
        max_x = shape[0] - offset
    if idy + border * (square_size // 2 + 1) + offset > shape[1]:
        min_y = shape[1] - square_size - offset
        max_y = shape[1] - offset
    if max_x is None and min_x is None:
        min_x = idx - (square_size // 2)
        max_x = idx + (square_size // 2)
    if max_y is None and min_y is None:
        min_y = idy - (square_size // 2)
        max_y = idy + (square_size // 2)
    region_mask = mask[int(min_x):int(max_x), int(min_y):int(max_y)]
    region_grid = grid[int(min_x):int(max_x), int(min_y):int(max_y)]
    region_mask_pixels = mask_pixels[0][int(min_x):int(max_x), int(min_y):int(max_y)]
    region_mask_saturation = mask_pixels[1][int(min_x):int(max_x), int(min_y):int(max_y)]
    coordinates = [min_y, max_y, min_x, max_x]
    return region_mask, region_mask_pixels, region_mask_saturation, region_grid, coordinates

def update_grid(grided, coordinates):
    for idx, row in enumerate(grided):
        for idy, _ in enumerate(row):
            if coordinates[0] <= idy <= coordinates[1] and coordinates[2] <= idx <= coordinates[3]:
                grided[idx, idy] = 1
    return grided


def get_all_folders(folder: Path, time_base: str, instrument='IMPV1'):
    parent_dir = folder.parent
    base_name = folder.name

    if instrument == 'IMPV1':
        measurement = base_name.split(time_base)[0]
        index_measurement = base_name.split(time_base)[-1]
        return sorted([
            child for child in parent_dir.iterdir()
            if child.is_dir()
            and measurement in child.name
            and index_measurement in child.name
            and time_base not in child.name
        ], key=lambda path: path.name)

    index_measurement = f"_{base_name.replace(time_base, '').split('_')[-1]}"
    return sorted([
        child for child in parent_dir.iterdir()
        if child.is_dir()
        and index_measurement in child.name
        and time_base not in child.name
    ], key=lambda path: path.name)


def move_computed_folders(path_to_align, path_aligned):
    for fname in sorted(path_to_align.iterdir(), key=lambda path: path.name):
        if fname.is_dir():
            shutil.move(str(fname), str(path_aligned))
        else:
            assert fname.name.endswith('.txt'), "Only .txt files are allowed in the 'to_align' folder"
            shutil.move(str(fname), str(path_aligned / 'logbooks' / fname.name))


def create_masked_image(intensity_image, mask, path_save):
    intensity_image_msk = copy.deepcopy(intensity_image)
    intensity_image_msk[mask] = 0
    cv2.imwrite(str(path_save), intensity_image_msk)
