from pathlib import Path
import shutil
import tifffile
from PIL import Image
import matplotlib.pyplot as plt
import numpy as np
import re
import pandas as pd
import copy
import cv2
import platform
import SimpleITK as sitk
from scipy.stats import circmean, circstd

# --- Mask and MM Loading Utilities ---

def get_masks(path: str, priority: list = ['bg', 'gm', 'wm']):
    """
    Load and merge tissue masks from annotation folder.
    Looks for all files matching GM_XX.tif and WM_XX.tif (XX = two digits).
    Returns a merged mask with values for WM, GM, and BG.
    """
    annotation_path = path / 'annotation'
    values = {'wm': 255, 'gm': 128, 'bg': 0}
    masks = {}

    # --- Find all GM_XX.tif and WM_XX.tif files ---
    gm_files = sorted([f for f in annotation_path.glob('*.tif') if re.match(r'[Gg][Mm]_\d{2}\.tif$', f.name)])
    wm_files = sorted([f for f in annotation_path.glob('*.tif') if re.match(r'[Ww][Mm]_\d{2}\.tif$', f.name)])

    if not gm_files or not wm_files:
        raise FileNotFoundError("No GM_XX.tif or WM_XX.tif files found in annotation folder.")

    # --- Load and combine all GM and WM masks ---
    gm_stack = [tifffile.imread(f) for f in gm_files]
    wm_stack = [tifffile.imread(f) for f in wm_files]

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
    out_path = annotation_path / 'all_merged.tif'
    Image.fromarray(all_merged).save(out_path)

    return all_merged
    
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
    # Convert columns to string for consistency
    df.columns = [str(c) for c in df.columns]
    current_cols = df.shape[1]
    for i in range(current_cols, total_columns):
        df[str(i)] = np.nan
    # Ensure all columns exist and are in order
    all_col_names = [str(i) for i in range(total_columns)]
    for col in all_col_names:
        if col not in df.columns:
            df[col] = np.nan
    df = df[all_col_names]
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
    cv2.imwrite(path_save, intensity_image_msk)

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

def subtract_angles_series(series):
    """
    Apply subtract_angle between the first element and each entry of a pandas Series.
    """
    ref = series.iloc[0]
    return series.apply(lambda x: subtract_angle(ref, x))

def get_all_values_cv(all_values):
    """
    Compute coefficient of variation for all parameters across tissues.
    """
    all_values_cv = copy.deepcopy(all_values)

    for tissue, values in all_values_cv.items():
        for param, val in values.items():
            if param == 'azimuth':
                all_values_cv[tissue][param] = val.apply(subtract_angles_series, axis=0)
            else:
                all_values_cv[tissue][param] = val.div(val.iloc[0])
                
    return all_values_cv

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