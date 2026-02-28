from pathlib import Path
import pickle
import sys
import shutil
import subprocess
import tifffile as tiff
from PIL import Image
import matplotlib.pyplot as plt
import numpy as np
import re
import pandas as pd
import copy
import cv2
import platform
import SimpleITK as sitk
import imageio
import random
from scipy.stats import circmean, circstd

from riap.manual_steps import semi_automatic_processing

_MAX_VALUE = 2**16 - 1

def run_alignment_pipeline(cfg, folder, image0, image1, invreg_dir, output_folder):
    if (folder / "annotation" / "override.txt").exists():
        points_moving, points_reference = semi_automatic_processing(folder, image0, image1, force_recompute=False)
        points_reference = np.array(points_reference)
        points_moving = np.array(points_moving)
    else:

        if str(cfg.paths.match_anything_path) not in sys.path:
            sys.path.append(str(cfg.paths.match_anything_path))
        from imcui.ui.utils import run_matching


        random.seed(42)
        ransac_reproj_threshold = 12
                    
        results = run_matching(
            image0, image1,
            match_threshold=0.15,
            extract_max_keypoints=5000,
            keypoint_threshold=0.015,
            key="matchanything_roma",
            ransac_method="CV2_RANSAC",
            ransac_reproj_threshold=ransac_reproj_threshold,
            ransac_confidence=0.999,
            ransac_max_iter=10000,
            choice_geometry_type="Homography",
            matcher_zoo=get_matcher_zoo(),
            force_resize=False,
            image_width=640,
            image_height=480,
            use_cached_model=False,
            model=None,
            matcher=None,
            use_ransac=True,
        )

        points_reference, points_moving = results[3][0], results[3][1]
        dst = invreg_dir / f'match_anything_output_{folder.stem}.png'
        Image.fromarray(results[2]).save(dst)
        dst = invreg_dir / f'match_anything_output_full_{folder.stem}.png'
        Image.fromarray(results[1]).save(dst)

    with open(output_folder / f"matched_points.pickle", "wb") as f:
        pickle.dump((points_reference, points_moving), f)

    return points_reference, points_moving

# --- Mask and MM Loading Utilities ---

def get_masks(path: str, cfg, priority: list = ['bg', 'gm', 'wm']):
    """
    Load and merge tissue masks from annotation folder.
    Looks for all files matching GM_XX.tif and WM_XX.tif (XX = two digits).
    Returns a merged mask with values for WM, GM, and BG.
    """
    annotation_path = path / 'annotation'

    angle_correction = get_angle_correction(annotation_path)
    camera_correction = get_camera_correction(annotation_path)

    values = {'wm': 255, 'gm': 128, 'bg': 0}
    masks = {}

    # --- Find all GM_XX.tif and WM_XX.tif files ---
    gm_files = sorted([f for f in annotation_path.glob('*.tif') if re.match(r'[Gg][Mm]_\d{2}\.tif$', f.name)])
    wm_files = sorted([f for f in annotation_path.glob('*.tif') if re.match(r'[Ww][Mm]_\d{2}\.tif$', f.name)])

    if not gm_files or not wm_files:
        raise FileNotFoundError("No GM_XX.tif or WM_XX.tif files found in annotation folder.")

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
        
    out_path = annotation_path / 'all_merged.tif'
    Image.fromarray(all_merged).save(out_path)

    img = Image.open(path / cfg.default_paths.polarimetry / 'Intensity_img.png')
    img_blended = Image.blend(img.convert("RGBA"), Image.fromarray(all_merged).convert("RGBA"), alpha=0.05)
    img_blended.save(annotation_path / 'all_merged_blended.png')

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

# --- Alignment and File Management ---

def generate_config_file(binaries_path, scripts_path):
    """
    Generate a configuration file with paths to Elastix executables and libraries for MATLAB engine.
    """
    if platform.system() == 'Windows':
        raise NotImplementedError(f"Please change the paths in the file {str(scripts_path / 'configFilePaths.cfg')} manually for Windows OS, as the current implementation is for Linux.")
    elastix_exe = binaries_path / "bin" / "elastix"
    transformix_exe = binaries_path / "bin" / "transformix"
    elastix_lib = binaries_path / "lib"
    
    shared_libs = r'# /lib/x86_64-linux-gnu/'

    original_file = [
        r'% This is a configuration file with paths to external wrapped executables,',
        r'% or auxiliary configuration data employed in the compiled package.',
        r'% Please specify the local FilePaths - leave blank otherwise.',
        r'% All Entries follow the pattern: #ExecutableTAG \n strExecutableFILEPATH',
        '% Header lines starting with \'%\' will be treated as comments and ignored.',
        r'#EXE_Elastix',
        elastix_exe,
        r'% Path HERE!',
        r'#EXE_Transformix',
        transformix_exe,
        r'% Path HERE!',
        r'#LIB_SystemSharedLibs',
        shared_libs,
        '% Find the above path by running \'ldd <#EXE_Elastix>\' in the UNIX terminal',
        r'#LIB_Elastix',
        elastix_lib,
        r'% Path HERE!'
    ]
    path = scripts_path / 'configFilePaths.cfg'
    with open(path, 'w') as fp:
        for item in original_file:
            fp.write("%s\n" % item)

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



# --- SITK alignments ---

def align_with_sitk(fixed_arr, to_propagate, matching_points):
    fixed_image = sitk.GetImageFromArray(fixed_arr)

    # set up the matching points
    fixed_points = matching_points[1]
    moving_points = matching_points[0]
    fixed_landmarks = fixed_points.astype(np.uint16).flatten().tolist()
    moving_landmarks = moving_points.astype(np.uint16).flatten().tolist()

    # set up the bspline transform
    transform = sitk.BSplineTransformInitializer(fixed_image, (3, 3), 3)
    landmark_initializer = sitk.LandmarkBasedTransformInitializerFilter()
    landmark_initializer.SetFixedLandmarks(fixed_landmarks)
    landmark_initializer.SetMovingLandmarks(moving_landmarks)
    landmark_initializer.SetReferenceImage(fixed_image)
    landmark_initializer.Execute(transform)
    output_transform = landmark_initializer.Execute(transform)

    # resample the moving images
    interpolator = sitk.sitkNearestNeighbor
    moving_images = [sitk.GetImageFromArray(to_propagate),
                     sitk.GetImageFromArray(fixed_arr)]
    resampled_images = []
    for moving_img in moving_images:
        resampled_images.append(
            sitk.GetArrayFromImage(sitk.Resample(moving_img, fixed_image, output_transform, interpolator, 0)))

    return resampled_images


def get_matcher_zoo() -> dict:
    """
    Returns a dictionary containing configurations for different MatchAnything models.
    """
    return {
        'matchanything_eloftr': {
            'matcher': {
                'output': 'matches-matchanything-eloftr', 
                'model': {
                    'name': 'matchanything',
                    'model_name': 'matchanything_eloftr',
                    'img_resize': 832,
                    'match_threshold': 0.020},
                'preprocessing': {
                    'grayscale': False,
                    'resize_max': 832,
                    'dfactor': 32,
                    'width': 640,
                    'height': 480,
                    'force_resize': True},
                'max_error': 1,
                'cell_size': 1},
            'dense': True},
        'matchanything_roma': {
            'matcher': {
                'output': 'matches-matchanything-roma',
                'model': {
                    'name': 'matchanything',
                    'model_name': 'matchanything_roma',
                    'img_resize': 832,
                    'match_threshold': 0.1},
                'preprocessing': {
                    'grayscale': False,
                    'resize_max': 832,
                    'dfactor': 32,
                    'width': 640,
                    'height': 480,
                    'force_resize': True},
                'max_error': 1,
                'cell_size': 1},
            'dense': True}
    }


# --- Fiji.app alignments ---

def recover_and_reconstruct_labels(cfg, path_output, mask):
    """
    recover_and_reconstruct_labels load the aligned images and save them in the FolderAlignHistology object
    """
    registered_x = tiff.imread(path_output / "registered_x.tif") / _MAX_VALUE * cfg.settings.shape_imgs[0]
    registered_y = tiff.imread(path_output / "registered_y.tif") / _MAX_VALUE * cfg.settings.shape_imgs[1]

    mask_aligned = reconstruct_labels(cfg, [registered_x, registered_y], mask)
    Image.fromarray(mask_aligned).save(path_output / 'mask_registered.png')
    
    image_aligned = reconstruct_labels(cfg, [registered_x, registered_y], cv2.imread(str(path_output / "fixed.png"), cv2.IMREAD_GRAYSCALE))
    Image.fromarray(image_aligned).save(path_output / 'image_registered.png')


def reconstruct_labels(cfg, maps, original_labels):
    """
    reconstruct_labels is used to reconstruct the labels images from the aligned images and save them in the FolderAlignHistology object
    """
    [registered_x, registered_y] = maps
    reconstructed_labels = np.zeros((cfg.settings.shape_imgs[1], cfg.settings.shape_imgs[0]), dtype=np.uint8)

    for idx, x in enumerate(registered_x):
        for idy, y in enumerate(x):
            idy_original_image = round(y)
            idx_original_image = round(registered_y[idx, idy])
            if idx_original_image == cfg.settings.shape_imgs[1] or idy_original_image == cfg.settings.shape_imgs[0]:
                continue
            reconstructed_labels[idx, idy] = original_labels[idx_original_image, idy_original_image]

    return reconstructed_labels

def align_imgs_ImgJ(cfg, folder, path_output, mask):
    """
    align_img_master is the master function organizing the data for the alignment and calling the function actually performing the alignment (in "imgJ_align.py")
    """
    save_imgs_alignment(cfg, path_output)
    macro = generate_macro(path_output)
    macro_path = Path(path_output) / 'macro.ijm'
    with open(macro_path, "w") as f:
        f.write(macro)
    subprocess.run(["xvfb-run", "-a", str(cfg.paths.fiji_path), "--console", "-macro", macro_path], check=True)
    recover_and_reconstruct_labels(cfg, path_output, mask)
    move_the_alignment_results(path_output, folder)

def save_imgs_alignment(
    cfg, path_output
) -> None:
    """
    Saves images necessary for ImageJ alignment into the temp folder.
    """
    img_to_propagate = create_propagation_img(cfg)
    for idx, suffix in enumerate(['x', 'y']):
        path_img_tmp = path_output / f'img_brightfield_{suffix}.tif'
        cv2.imwrite(str(path_img_tmp), img_to_propagate[idx])
    return img_to_propagate

def create_propagation_img(cfg):
    """
    Creates a coordinate map for resampling the tiles, scaled based on the histology processing flag.
    """

    x_coords = np.arange(cfg.settings.shape_imgs[1])
    y_coords = np.arange(cfg.settings.shape_imgs[0])
    to_propagate = [np.tile(x_coords, (cfg.settings.shape_imgs[0], 1)), np.tile(y_coords, (cfg.settings.shape_imgs[1], 1)).T]
        
    scale = _MAX_VALUE
    max_ = _MAX_VALUE
    img_to_propagate = [np.clip(((to_propagate[1] / np.max(np.abs(to_propagate[1]))) * scale).T.astype('uint16'), 0, max_),
                        np.clip(((to_propagate[0] / np.max(np.abs(to_propagate[0]))) * scale).T.astype('uint16'), 0, max_)]
    return img_to_propagate

def move_the_alignment_results(path_output, folder):
    """
    move_the_alignment_results is used to move the results into the aligned folder
    """
    output_folder = folder / 'annotation' / 'alignment_results'
    output_folder.mkdir(parents=True, exist_ok=True)

    shutil.copy(path_output / 'mask_registered.png', output_folder / 'mask_registered.png')
    shutil.copy(path_output / 'image_registered.png', output_folder / 'image_registered.png')

    create_alignment_gif(np.array(Image.open(path_output / 'moving.png')), np.array(Image.open(path_output / 'image_registered.png')), output_folder / 'gif_registered.gif', n_frames=20, duration=0.1)

def create_alignment_gif(
        image1: np.ndarray,
        image2: np.ndarray,
        save_path: str,
        n_frames: int = 20,
        duration: float = 0.1,
        resize_factor: float = 1
    ):
    """
    Creates a looping GIF showing alignment by blending image1 to image2 and back.

    Parameters:
    - image1: np.array, first image (e.g. reference)
    - image2: np.array, second image (e.g. registered)
    - save_path: str, path to save GIF
    - n_frames: int, number of frames in one direction (total frames = 2*n_frames - 2)
    - duration: float, seconds per frame in GIF
    """
    # Convert to RGB for GIF
    def to_rgb(img):
        if img.ndim == 2:
            return cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
        else:
            return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    img1_rgb = to_rgb(image1)
    img2_rgb = to_rgb(image2)

    # Resize img2 to match img1 if needed
    if img1_rgb.shape != img2_rgb.shape:
        img2_rgb = cv2.resize(img2_rgb, (img1_rgb.shape[1], img1_rgb.shape[0]))

    # Resize both images to half their original size
    if resize_factor != 1:
        new_size = (int(img1_rgb.shape[1] * resize_factor), int(img1_rgb.shape[0] * resize_factor))
        img1_rgb = cv2.resize(img1_rgb, new_size)
        img2_rgb = cv2.resize(img2_rgb, new_size)
    
    # Blend forward frames (image1 -> image2)
    forward_frames = [cv2.addWeighted(img1_rgb, 1 - alpha, img2_rgb, alpha, 0) for alpha in np.linspace(0, 1, n_frames)]

    # Blend backward frames (image2 -> image1), exclude first and last frames to avoid duplicate frames at the ends
    backward_frames = forward_frames[-2:0:-1]

    frames = forward_frames + backward_frames

    frames_rgb = [cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) for frame in frames]
    imageio.mimsave(save_path, frames_rgb, duration=duration, loop=0)


def generate_macro(
    measurement_folder
) -> str:
    path_tmp = '"' + str(measurement_folder)
    path_tmp_no_start = path_tmp.replace('"', '')

    macro = """
    open(""" + path_tmp + """/fixed.png");
    open(""" + path_tmp + """/moving.png");
    call("bunwarpj.bUnwarpJ_.loadLandmarks", """ + path_tmp + """/coordinates.txt");
    run("bUnwarpJ", "load=""" + path_tmp_no_start + """/coordinates.txt source_image=moving.png target_image=fixed.png registration=Accurate image_subsample_factor=0 initial_deformation=[Very Coarse] final_deformation=[Coarse] divergence_weight=0.1 curl_weight=0.1 landmark_weight=1.5 image_weight=0 consistency_weight=10 stop_threshold=0.01 save_transformations save_direct_transformation=""" + path_tmp_no_start + """/global_img_direct_transf.txt save_inverse_transformation=""" + path_tmp_no_start + """/intensity_img_inverse_transf.txt");
    close();
    close();
    close();
    open(""" + path_tmp + """/fixed.png");
    open(""" + path_tmp + """/img_brightfield_x.tif");
    selectImage("img_brightfield_x.tif");
    call("bunwarpj.bUnwarpJ_.loadElasticTransform", """ + path_tmp + """/intensity_img_inverse_transf.txt", "fixed.png", "img_brightfield_x.tif");
    saveAs("Tiff", """ + path_tmp + """/registered_x.tif");
    close();
    close();
    open(""" + path_tmp + """/fixed.png");
    open(""" + path_tmp + """/img_brightfield_y.tif");
    selectImage("img_brightfield_y.tif");
    call("bunwarpj.bUnwarpJ_.loadElasticTransform", """ + path_tmp + """/intensity_img_inverse_transf.txt", "fixed.png", "img_brightfield_y.tif");
    saveAs("Tiff", """ + path_tmp + """/registered_y.tif");
    close();
    close();
    run("Quit");
    """
    return macro