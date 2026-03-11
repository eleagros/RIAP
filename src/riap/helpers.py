from pathlib import Path
import shutil
import tifffile as tiff
from PIL import Image
import matplotlib.pyplot as plt
import numpy as np
import re
import pandas as pd
import copy
import cv2
from scipy.stats import circmean, circstd
import pickle

from riap.align_utils import run_alignment_pipeline
from riap.aligner import OpenCValigner
from riap.io_utils import create_alignment_gif

# --- Mask and MM Loading Utilities ---

def get_masks(
        path: str,
        default_path_polarimetry: str,
        priority: list=['bg', 'gm', 'wm'],
        base_folder=None,
        cfg=None,
        base_folder_mask=None
    ):
    """
    Load and merge tissue masks from annotation folder.
    Looks for all files matching GM_XX.tif and WM_XX.tif (XX = two digits).
    Returns a merged mask with values for WM, GM, and BG.
    """
    annotation_path = path / 'annotation'
    out_path = annotation_path / 'all_merged.tif'

    angle_correction = get_angle_correction(annotation_path)
    camera_correction = get_camera_correction(annotation_path)

    values = {'wm': 255, 'gm': 128, 'bg': 0}
    masks = {}

    # --- Find all GM_XX.tif and WM_XX.tif files ---
    gm_files = sorted([f for f in annotation_path.glob('*.tif') if re.match(r'[Gg][Mm]_\d{2}\.tif$', f.name)])
    wm_files = sorted([f for f in annotation_path.glob('*.tif') if re.match(r'[Ww][Mm]_\d{2}\.tif$', f.name)])

    if not gm_files or not wm_files:
        if not base_folder:
            if out_path.exists():
                return np.array(Image.open(out_path))
            raise FileNotFoundError("No GM_XX.tif or WM_XX.tif files found in annotation folder.")
        else:
            all_merged = propagate_labels(
                path,
                base_folder,
                default_path_polarimetry,
                annotation_path,
                cfg,
                base_folder_mask
            )
    else:
        # --- Load and combine all GM and WM masks ---
        gm_stack = [tiff.imread(f) for f in gm_files]
        wm_stack = [tiff.imread(f) for f in wm_files]

        # Ensure all masks have same shape
        ref_shape = gm_stack[0].shape
        if any(m.shape != ref_shape for m in gm_stack + wm_stack):
            raise ValueError("All GM and WM masks must have the same shape.")

        masks['gm'] = np.clip(np.sum(gm_stack, axis=0), 0, 255).astype(np.uint8)
        masks['wm'] = np.clip(np.sum(wm_stack, axis=0), 0, 255).astype(np.uint8)

        # Background = where neither GM nor WM is present
        masks['bg'] = ((masks['wm'] == 0) & (masks['gm'] == 0)) * 255
        masks['bg'] = masks['bg'].astype(np.uint8)

        # --- Merge according to priority ---
        all_merged = np.zeros(masks['bg'].shape, dtype=np.uint8)
        for p in priority:
            all_merged[masks[p] == 255] = values[p]

        # --- Save merged mask ---
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
    out_dir.mkdir(exist_ok=True)

    if (annotation_path / 'propagation_masks' / 'warping_function.pickle').exists():
        with open(annotation_path / 'propagation_masks' / 'warping_function.pickle', "rb") as f:
            warping_function = pickle.load(f)
    else:
        _, _, results = run_alignment_pipeline(cfg, path, image0, image1, out_dir, out_dir)
        warping_function = results[-2]

    path_propagation_masks = annotation_path / 'propagation_masks'
    path_to_propagate = path_propagation_masks / 'to_propagate'
    path_to_propagate.mkdir(exist_ok=True, parents=True)
    cv2.imwrite(str(path_to_propagate / 'mask.png'), base_folder_mask)
    cv2.imwrite(str(path_to_propagate / 'intensity_img.png'), image1)

    with open(path_propagation_masks / 'warping_function.pickle', "wb") as f:
        pickle.dump(warping_function, f)

    aligner = OpenCValigner(
        path_propagation_masks,
        path_propagation_masks,
        path_to_propagate,
        warping_function,
        None
    )
    aligner.run()

    cv2.imwrite(str(path_propagation_masks / 'all_merged_original.tif'), cv2.imread(str(path_propagation_masks / 'mask_warped.png')))
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
    """Gets the angle correction from a file if available."""
    path = Path(path)
    file_path = path / 'rotation_MM.txt'

    if file_path.exists():
        try:
            with file_path.open() as f:
                return int(f.readline().strip())
        except (FileNotFoundError, ValueError):
            return 0  # Return 0 if file not found or invalid
    return 0  # Return 0 if neither file exists

def get_camera_correction(path: str) -> int:
    path = Path(path)
    primary_path = path / 'correct_intensities.txt'

    if primary_path.exists():
        try:
            with primary_path.open() as f:
                return f.readline().strip()
        except (FileNotFoundError, ValueError):
            return ''
    return ''

def load_data_mm(path_MM, angle=0):
    """
    Load Mueller Matrix and apply azimuth correction if needed.
    """
    mat = dict(np.load(path_MM))
    azimuth = mat['azimuth']
    if angle != 0:
        azimuth_corrected = np.zeros(azimuth.shape)
        for idx, x in enumerate(azimuth):
            for idy, y in enumerate(x):
                azimuth_corrected[idx, idy] = (y - angle) % 180
        mat['azimuth'] = azimuth_corrected
    return mat

def pad_dataframe_with_nans(df, total_columns):
    """
    Pad a DataFrame with additional columns of NaNs if not enough columns are provided.
    Columns are named as integers starting from 0.
    """
    n_missing = total_columns - df.shape[1]

    if n_missing > 0:
        for i in range(n_missing):
            df[f'col_{df.shape[1] + 1}'] = np.nan
    return df

# --- ROI Selection Utilities ---

def get_square_coordinates(mask, mask_pixels, square_size, grid, coordinates=None, treshold_valid_pixels=0.95):
    """
    Randomly select a square ROI in the image, ensuring tissue and validity.
    Returns coordinates and updated grid.
    """
    found = False
    counter = 0
    while not found and counter < 1000:
        random_row, random_col = get_random_pixel(mask)
        if mask[random_row, random_col] == 0:
            counter += 1
            continue
        region, region_pixels, grided, coordinates = select_region(
            mask.shape, mask, mask_pixels, random_row, random_col, square_size, grid
        )
        positive = (
            region.shape[0] * region.shape[1] == np.sum(region)
            and np.sum(grided) == 0
            and np.sum(region_pixels) > treshold_valid_pixels * region.shape[0] * region.shape[1] # contains at least treshold_valid_pixels% valid pixels
        )
        
        if positive:
            found = True
            grid = update_grid(grid, coordinates)
        counter += 1
    if found:
        return coordinates, grid
    return None, grid

def get_random_pixel(mask):
    """
    Returns a random row and column index from the mask.
    """
    random_row = np.random.randint(mask.shape[0])
    random_col = np.random.randint(mask.shape[1])
    return random_row, random_col

def select_region(shape, mask, mask_pixels, idx, idy, square_size, grid, border=1.5, offset=15):
    """
    Selects a region in the image at a distance > offset from the border.
    Returns region mask, region grid, and coordinates.
    """
    max_x, min_x = None, None
    max_y, min_y = None, None
    # Handle borders
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
    # Middle of the image
    if max_x is None and min_x is None:
        min_x = idx - (square_size // 2)
        max_x = idx + (square_size // 2)
    if max_y is None and min_y is None:
        min_y = idy - (square_size // 2)
        max_y = idy + (square_size // 2)
    region_mask = mask[int(min_x):int(max_x), int(min_y):int(max_y)]
    region_grid = grid[int(min_x):int(max_x), int(min_y):int(max_y)]
    region_mask_pixels = mask_pixels[int(min_x):int(max_x), int(min_y):int(max_y)]
    coordinates = [min_y, max_y, min_x, max_x]
    return region_mask, region_mask_pixels, region_grid, coordinates

def search_for_validity(mask, idx, MM, coordinates=None):
    """
    Checks if the ROI fulfills tissue and valid pixel requirements.
    """
    positive = True
    for row in mask:
        for y in row:
            if y == idx:
                positive = False
    if positive and idx == 1:
        valid_pixels = np.sum(MM['Msk'][coordinates[2]:coordinates[3], coordinates[0]:coordinates[1]])
        positive = valid_pixels > 0 * mask.shape[0] * mask.shape[1]
    return positive

def update_grid(grided, coordinates):
    """
    Updates the grid to add the newly generated ROI.
    """
    for idx, x in enumerate(grided):
        for idy, y in enumerate(x):
            if coordinates[0] <= idy <= coordinates[1] and coordinates[2] <= idx <= coordinates[3]:
                grided[idx, idy] = 1
    return grided


def get_all_folders(folder: Path, time_base: str, instrument='IMPV1'):
    """
    Find all sibling folders of `folder` in the same parent directory
    that match the measurement/index pattern, excluding folders with time_base.
    """
    parent_dir = folder.parent
    base_name = folder.name

    if instrument == 'IMPV1':
        measurement = base_name.split(time_base)[0]
        index_measurement = base_name.split(time_base)[-1]
        return [
            f for f in parent_dir.iterdir()
            if f.is_dir()
            and measurement in f.name
            and index_measurement in f.name
            and time_base not in f.name
        ]
    else:
        index_measurement = f"_{base_name.replace(time_base, '').split('_')[-1]}"
        return [
            f for f in parent_dir.iterdir()
            if f.is_dir()
            and index_measurement in f.name
            and time_base not in f.name
        ]

def move_computed_folders(path_to_align, path_aligned):
    """
    Move aligned folders from 'to_align' to 'aligned'.
    """
    for fname in path_to_align.iterdir():
        if fname.is_dir():
            shutil.move(str(fname), str(path_aligned))
        else:
            assert fname.name.endswith('.txt'), "Only .txt files are allowed in the 'to_align' folder"
            shutil.move(str(fname), str(path_aligned / 'logbooks' / fname.name))

# --- Parameter and Statistics Utilities ---

def get_statistics(values, param, parameter):
    """
    Extract statistical descriptors for a parameter in the ROI.
    Returns mean, std, max, median.
    """
    listed = values
    listed = listed[listed != 0]
    try:
        assert len(listed) > 0
        if parameter == 'azimuth':
            mean = circmean(listed, high=180)
            stdev = circstd(listed, high=180)
            median = mean
        else:
            mean = np.mean(listed)
            stdev = np.std(listed)
            median = np.median(listed)
    except:
        mean = np.nan
        stdev = np.nan
        median = np.nan
    bins = np.linspace(param['borders'][0], param['borders'][1], num=param['num_bins'])
    data = plt.hist(listed, bins=bins)
    plt.close()
    arr = data[0]
    max_idx = np.where(arr == np.amax(arr))[0][0]
    maximum = data[1][max_idx]
    return mean, stdev, maximum, median

def natural_sort_key(s):
    """
    Sort key for folder names, e.g. t0, t1, t2, ...
    """
    match = re.search(r'_t(\d+)_', s)
    return int(match.group(1)) if match else float('inf')

def sort_stats_dict(stats_dict):
    """
    Sort statistics dictionary by folder name using natural sort.
    """
    return {k: stats_dict[k] for k in sorted(stats_dict, key=natural_sort_key)}

def create_pandas_stats(all_stats):
    """
    Convert nested statistics dictionary to pandas DataFrames for each ROI.
    """
    all_stats_pandas = {}
    for key_ROI, values in all_stats.items():
        dfs = []
        for folder, val in values.items():
            df = pd.DataFrame(val).T
            df.columns = ["mean", "std", "max", "median"]
            df["folder"] = folder
            dfs.append(df)
        dfs = pd.concat(dfs)
        dfs = dfs.reset_index().rename(columns={"index": "parameter"})
        dfs = dfs.sort_values(by=["parameter", "folder"]).reset_index(drop=True)
        all_stats_pandas[key_ROI] = dfs
    return all_stats_pandas

def create_masked_image(intensity_image, mask, path_save):
    """
    Save a masked intensity image to disk.
    """
    intensity_image_msk = copy.deepcopy(intensity_image)
    intensity_image_msk[mask] = 0
    cv2.imwrite(str(path_save), intensity_image_msk)

# --- Miscellaneous Utilities ---

def get_angle(fname):
    """
    Extract alignment angle from a parameter file.
    """
    with open(fname) as f:
        lines = f.readlines()
    for line in lines:
        if 'TransformParameters ' in line:
            angle_data = line
    angle_data = angle_data.split(' ')[1:5]
    angle = np.arctan(float(angle_data[2]) / float(angle_data[0]))
    return angle * 360 / (2 * np.pi)

def subtract_angle(targetA, sourceA):
    """
    Compute the minimal absolute difference between two angles (mod 180).
    """
    a = targetA - sourceA
    return abs((a + 90) % 180 - 90)

