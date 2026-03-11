from pathlib import Path
import pickle
import shutil
import subprocess
import uuid
from loguru import logger
import numpy as np
from PIL import Image
import cv2
import os
from tqdm import tqdm
import math

try:    
    import matlab.engine
except ImportError:
    print(" [warning] MATLAB engine for Python is not installed. Elastix alignment will not work.")

from riap.config import ProcessingConfig
from riap.helpers import (
    load_data_mm, get_all_folders, move_computed_folders, get_square_coordinates,
    get_masks, get_angle, get_statistics, create_masked_image, sort_stats_dict, create_pandas_stats
)
from riap.elastix import generate_config_file
from riap.align_utils import (
    align_with_sitk, run_alignment_pipeline, align_imgs_ImgJ
)
from riap.io_utils import write_mp_fp_txt_format
from riap.aligner import OpenCValigner
from riap.io_utils import create_alignment_gif

def process(processing_config: ProcessingConfig):
    """Main processing loop for all base directories."""
    processing_config.validate()
    
    for idx_folder, path_folder in enumerate(processing_config.base_dirs):
        
        # Remove previously acquired data
        path_polarimetry_wavelength = path_folder / processing_config.cfg.default_paths.polarimetry
        path_folder_50x50 = path_folder / processing_config.cfg.default_paths._50x50_images
        shutil.rmtree(path_folder_50x50, ignore_errors=True)
        path_folder_50x50.mkdir(parents=True, exist_ok=True)
            
        logger.info(f"Processing {path_folder.name}: {idx_folder + 1}/{len(processing_config.base_dirs)}\n")
        link_folder_value = {}
        
        MM = load_data_mm(path_polarimetry_wavelength / 'MM.npz', angle=0)
        if processing_config.instrument == 'IMPV1':
            mask_pixels = np.logical_and(MM['Msk'], ~MM['dilated_mask'])
        else:
            mask_pixels = np.logical_and(MM['Msk'], MM['dilated_mask'] == 1)
        
        all_folders = get_all_folders(path_folder, processing_config.time_base, instrument=processing_config.instrument)

        all_masks = {}
        all_masks[path_folder] = get_masks(path_folder, processing_config.cfg.default_paths.polarimetry)
        for folder_of_interest in tqdm(all_folders, desc="Creating masks for folders"):
            all_masks[folder_of_interest] = get_masks(
                folder_of_interest,
                processing_config.cfg.default_paths.polarimetry,
                base_folder=path_folder.name,
                cfg=processing_config.cfg,
                base_folder_mask=all_masks[path_folder]
            )

        mask_to_propagate = np.zeros(all_masks[path_folder].shape)
        mask = all_masks[path_folder]
        intensity_image = Image.open(path_polarimetry_wavelength / 'Intensity_img.png')

        logger.info(f"Found {len(all_folders)} folders to propagate to: {[f.name for f in all_folders]}")
        
        logger.info("Step 1: Selecting ROIs")
        for tissue_type in processing_config.tissue_types:
            intensity_image_masked = cv2.imread(str(path_polarimetry_wavelength / 'Intensity_img.png'), cv2.IMREAD_GRAYSCALE)
            WM = tissue_type == 'WM'
            matter_mask = mask == 255 if WM else mask == 128
            grid = np.zeros(matter_mask.shape)
            square_selection(
                processing_config.param_ROIs, tissue_type, path_folder_50x50, matter_mask,
                mask_pixels, grid, processing_config.instrument, intensity_image_masked,
                mask_to_propagate, link_folder_value
            )
        
        logger.info("Step 2: Aligning images and propagating ROIs")
        current_path_alignment = create_folder_to_align(
            processing_config.cfg, all_folders, processing_config.data_path, path_folder, path_polarimetry_wavelength,
            processing_config.path_to_align, mask_to_propagate
        )
        
        do_alignment(
            processing_config.cfg, processing_config.alignment_method, processing_config.path_to_align, current_path_alignment,
            all_folders, path_folder, processing_config.force_recompute
        )
        
        logger.info("Alignment completed")
        move_computed_folders(processing_config.path_to_align, processing_config.path_aligned)
        
        # change the current path variable
        current_path_alignment = Path(
            str(current_path_alignment).replace(f"{os.sep}to_align{os.sep}", f"{os.sep}aligned{os.sep}")
        )
        logger.success("Folders aligned successfully")
        
        logger.info("Step 3: Propagating ROIs and collecting statistics")
        propagate_roi(
            processing_config.cfg, path_folder, path_folder_50x50, current_path_alignment,
            all_folders, link_folder_value, mask_to_propagate, mask_pixels,
            MM, intensity_image, processing_config.alignment_method, processing_config.instrument,
            processing_config.histogram_parameters, processing_config.pixels_per_ROI
        )
        logger.success(f"Results saved in {path_folder_50x50}\n")


def square_selection(param_ROIs, tissue_type, path_folder_50x50, matter_mask, mask_pixels, grid, instrument, intensity_image_masked, mask_to_propagate, link_folder_value):
    """
    Select random square ROIs for the current tissue type and update masks.
    """
    exit_error = False
    square_counter = 0
    
    while square_counter < param_ROIs["number_of_random_squares"] and not exit_error:
        new_folder_name = f"{tissue_type}_{square_counter + 1}"
        path_output = path_folder_50x50 / new_folder_name
            
        try:
            coordinates_long, grid = get_square_coordinates(
                matter_mask, mask_pixels, param_ROIs['square_size'],
                grid, treshold_valid_pixels=0.95 if instrument == 'IMPV1' else 0.01
            )
            if coordinates_long is None:
                exit_error = True
                logger.warning(f"Could not find more squares for {tissue_type}")
                break
        except Exception as e:
            exit_error = True
            logger.warning(f"Could not find more squares for {tissue_type}")
            break
        
        path_output.mkdir(parents=True, exist_ok=True)
        square_counter += 1
                    
        # Write the coordinates to a txt file for reuse
        with open(path_output / 'coordinates.txt', 'w') as textfile:
            for element in coordinates_long:
                textfile.write(str(element) + "\n")

        # Update intensity and mask images
        intensity_image_masked[coordinates_long[2]: coordinates_long[3], coordinates_long[0]:coordinates_long[1]] = 0 if tissue_type == 'WM' else 255
        mask_to_propagate[coordinates_long[2]: coordinates_long[3], coordinates_long[0]:coordinates_long[1]] = square_counter + param_ROIs["number_of_random_squares"] if tissue_type == 'WM' else square_counter
        link_folder_value[new_folder_name] = square_counter + param_ROIs["number_of_random_squares"] if tissue_type == 'WM' else square_counter
        
    Image.fromarray(intensity_image_masked).save(path_folder_50x50 / f'{tissue_type}_selection.png')
    logger.success(f"Selected {square_counter} ROIs for {tissue_type}.")


def create_folder_to_align(cfg, all_folders, data_path, path_folder, path_polarimetry_wavelength, path_to_align, mask_to_propagate):
    """
    Create a unique folder for alignment and copy necessary files.
    Returns the current_path_alignment.
    """
    unique_id = str(uuid.uuid4())
    dt_string = path_folder.name + '__' + unique_id
    current_path_alignment = path_to_align / dt_string
    current_path_alignment.mkdir(parents=True, exist_ok=True)
    (current_path_alignment / 'mask').mkdir(parents=True, exist_ok=True)
    Image.fromarray(mask_to_propagate.astype(np.uint8)).save(current_path_alignment / 'mask' / 'mask.png')
    shutil.copy(path_polarimetry_wavelength / 'Intensity_img.png', current_path_alignment / (path_folder.name + '_ref_align.png'))

    for folder in all_folders:
        shutil.copy(data_path / folder / cfg.default_paths.polarimetry / 'Intensity_img.png', current_path_alignment / (folder.stem + '.png'))
    
    return current_path_alignment


def do_alignment(cfg, alignment_method, path_to_align, current_path_alignment, all_folders, path_folder, force_recompute):
    """
    Call the alignment pipeline based on the selected method.
    """
    if alignment_method == 'elastix':
        elastix_alignment(cfg, path_to_align)
    elif alignment_method == 'superglue':
        superglue_alignment(cfg, current_path_alignment, all_folders, path_folder)
    elif 'MatchAnything' in alignment_method:
        match_anything_alignment(cfg, current_path_alignment, all_folders, path_folder, alignment_method, force_recompute)
    else:
        raise ValueError(f"Unsupported alignment method: {alignment_method}")


def elastix_alignment(cfg, path_to_align):
    """
    Perform image alignment using Elastix via MATLAB engine.
    """
    dir_path = cfg.paths.elastix_path
    (dir_path / 'RegistrationElastix' / 'temp').mkdir(parents=True, exist_ok=True)
    with open(dir_path / 'RegistrationElastix' / 'temp' / 'path_alignment_batch.txt', 'w') as f:
        f.write(str(path_to_align))
    FixPattern = '_ref_align'
    with open(dir_path / 'RegistrationElastix' / 'temp' / 'FixPattern.txt', 'w') as f:
        f.write(FixPattern)
    Tag = 'AffineElastic'
    with open(dir_path / 'RegistrationElastix' / 'temp' / 'Tag.txt', 'w') as f:
        f.write(Tag)

    scripts_path = dir_path / 'RegistrationElastix' / 'RegistrationScripts'
    generate_config_file(cfg.paths.elastix_binaries, scripts_path)
    eng = matlab.engine.start_matlab()
    eng.cd(str(scripts_path), nargout=0)
    s = eng.genpath('0_NIfTI_IO')
    eng.addpath(s, nargout=0)
    eng.python_call(nargout=0)


def superglue_alignment(cfg, current_path_alignment, all_folders, path_folder):
    """
    Perform image alignment using SuperGlue.
    """
    invreg_dir = current_path_alignment / "invReg"
    invreg_dir.mkdir(parents=True, exist_ok=True)
    
    mask = cv2.imread(str(current_path_alignment / 'mask' / 'mask.png'), cv2.IMREAD_GRAYSCALE)
    for folder in all_folders:
        pair_dir = current_path_alignment / folder.stem
        pair_dir.mkdir(parents=True, exist_ok=True)

        shutil.copy(current_path_alignment / (path_folder.stem + '_ref_align.png'), pair_dir / f"fixed.png")
        shutil.copy(current_path_alignment / (folder.stem + '.png'), pair_dir / f"moving.png")
        
        cmd = [
            'python', str(cfg.paths.superglue / 'demo_superglue.py'),
            '--input', pair_dir,
            '--output_dir', pair_dir,
            "--resize", "-1",
            "--match_threshold", "0.2",
            '--no_display'
        ]
        subprocess.run(cmd)
        
        fixed_arr = cv2.imread(str(pair_dir / f"fixed.png"), cv2.IMREAD_GRAYSCALE)
        with open(pair_dir / f"matches_000000_000001.pickle", "rb") as f:
            matching_points = pickle.load(f)
            
        M, _ = cv2.estimateAffine2D(matching_points[0], matching_points[1], method=cv2.RANSAC)
        U, _, Vt = np.linalg.svd(M[:, :2])
        R = U @ Vt
        theta = np.arctan2(R[1,0], R[0,0]) * 180/np.pi
        with open(invreg_dir / f"{folder.stem}_angle.txt", "w") as f:
            f.write(str(theta))
        
        aligned_images = align_with_sitk(fixed_arr, mask, matching_points)
        out_path = invreg_dir / f"mask_PrpgTo_{folder.stem}.png"
        cv2.imwrite(str(out_path), aligned_images[0])
        
        out_path = invreg_dir / f"{folder.stem}_matched.png"
        cv2.imwrite(str(out_path), aligned_images[1])


def match_anything_alignment(cfg, current_path_alignment, all_folders, path_folder, alignment_method, force_recompute):
    """
    Perform image alignment using MatchAnything.
    """
    invreg_dir = current_path_alignment / "invReg"
    invreg_dir.mkdir(parents=True, exist_ok=True)

    mask = cv2.imread(str(current_path_alignment / 'mask' / 'mask.png'), cv2.IMREAD_GRAYSCALE)
    for folder in all_folders:
        
        output_folder = folder / 'annotation' / 'alignment_results'
        output_folder.mkdir(parents=True, exist_ok=True)

        image1 = cv2.imread(str(current_path_alignment / (path_folder.stem + '_ref_align.png')))
        image1 = cv2.cvtColor(image1, cv2.COLOR_BGR2RGB)
        image0 = cv2.imread(str(current_path_alignment / (folder.stem + '.png')))
        image0 = cv2.cvtColor(image0, cv2.COLOR_BGR2RGB)
        
        if not force_recompute and (output_folder / f"matched_points.pickle").exists() and (output_folder / f"warping_function.pickle").exists():
            (points_moving, points_reference) = pickle.load((output_folder / f"matched_points.pickle").open("rb"))
            warping_function = pickle.load((output_folder / f"warping_function.pickle").open("rb"))
            logger.info(f"Matched points already exist for {folder.stem}. Skipping alignment.")
        else:
            points_moving, points_reference, results = run_alignment_pipeline(cfg, folder, image0, image1, invreg_dir, output_folder)
            warping_function = results[-2]
            with open(output_folder / 'warping_function.pickle', "wb") as f:
                pickle.dump(warping_function, f)

        M, _ = cv2.estimateAffine2D(points_reference, points_moving, method=cv2.RANSAC)
        U, _, Vt = np.linalg.svd(M[:, :2])
        R = U @ Vt
        theta = np.arctan2(R[1,0], R[0,0]) * 180/np.pi
        with open(output_folder / f"correction_angle.txt", "w") as f:
            f.write(str(theta))
        
        if "imageJ" in alignment_method:
            temp_imgJ_path = invreg_dir / f"temp_imgJ_{folder.stem}"
            temp_imgJ_path.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(temp_imgJ_path / "fixed.png"), image0)
            cv2.imwrite(str(temp_imgJ_path / "moving.png"), image1)
            text_mp_fp = write_mp_fp_txt_format(
                [points_reference, points_moving],
                feature_matching_method="matchanything_roma",
            )
            with open(temp_imgJ_path / 'coordinates.txt', 'w') as f:
                f.write(text_mp_fp)
            align_imgs_ImgJ(cfg, folder, temp_imgJ_path, mask)
            shutil.copy(output_folder / 'mask_registered.png', invreg_dir / f"mask_PrpgTo_{folder.stem}.png")

        elif "opencv" in alignment_method:
            output_folder_propagate = invreg_dir.parent / f"to_propagate"
            output_folder_propagate.mkdir(exist_ok=True, parents=True)
            cv2.imwrite(str(output_folder_propagate / 'mask.png'), mask)
            cv2.imwrite(str(output_folder_propagate / 'intensity_img.png'), image1)
        
            aligner = OpenCValigner(
                output_folder=invreg_dir,
                input_folder=folder,
                to_propagate=output_folder_propagate,
                fun=warping_function,
                initial_shape=None
            )
            aligner.run()
            shutil.copy(str(invreg_dir.parent / 'mask_warped.png'), invreg_dir / f"mask_PrpgTo_{folder.stem}.png")
            create_alignment_gif(
                image0,
                np.array(Image.open(str(invreg_dir.parent / 'intensity_img_warped.png'))),
                output_folder / 'gif_registered.gif',
                n_frames=20,
                duration=0.1
            )

        shutil.copy(output_folder / 'correction_angle.txt', invreg_dir / f"{folder.stem}_angle.txt")

def propagate_roi(cfg, path_folder, path_folder_50x50, current_path_alignment, all_folders, link_folder_value, mask_to_propagate, mask_pixels, MM, intensity_image, alignment_method, instrument, histogram_parameters, pixels_per_ROI):
    """
    Propagate selected ROIs to all folders and collect statistics.
    Saves results as Excel files.
    """
    all_ROIs = [f.name for f in path_folder_50x50.iterdir() if f.is_dir()]
    all_masks, all_angles, all_MMs, all_intensity_images, propagated_masks, all_pixels_masks = {}, {}, {}, {}, {}, {}
    path_parameter_files = current_path_alignment / "invReg"

    # Load masks, angles, MM data, and intensity images for all folders
    for folder in all_folders:
        mask = get_masks(folder, cfg.default_paths.polarimetry)

        all_masks[folder] = {'WM': mask == 255, 'GM': mask == 128}
        if alignment_method == 'superglue' or 'MatchAnything' in alignment_method:
            with open(path_parameter_files / f"{folder.stem}_angle.txt", "r") as f:
                all_angles[folder] = float(f.read())
        elif alignment_method == 'elastix':
            all_angles[folder] = get_angle(path_parameter_files / f"{folder.stem}_AffineElastic_TransformParameters_0.txt")
        else:
            raise ValueError(f"Unsupported alignment method: {alignment_method}")

        path_polarimetry_wavelength = folder / cfg.default_paths.polarimetry
        all_MMs[folder] = load_data_mm(path_polarimetry_wavelength / 'MM.npz', angle=all_angles[folder])
        all_pixels_masks[folder] = np.logical_and(all_MMs[folder]['Msk'], all_MMs[folder]['dilated_mask'])
        all_intensity_images[folder] = cv2.imread(str(path_polarimetry_wavelength / 'Intensity_img.png'), cv2.IMREAD_GRAYSCALE)

        if alignment_method == 'elastix':
            propagated_masks[folder] = cv2.imread(
                str(path_parameter_files / f"mask_PrpgTo_{folder.stem}_AffineElastic_TransformParameters_0.png"),
                cv2.IMREAD_GRAYSCALE
            )
        elif alignment_method == 'superglue' or 'MatchAnything' in alignment_method:
            propagated_masks[folder] = cv2.imread(
                str(path_parameter_files / f"mask_PrpgTo_{folder.stem}.png"),
                cv2.IMREAD_GRAYSCALE
            )
        else:
            raise ValueError(f"Unsupported alignment method: {alignment_method}")
    
    statistics = {}

    base_folder = path_folder.name
    for ROI in tqdm(all_ROIs, desc="Processing ROIs"):
        statistics[ROI] = {}
        value_in_mask = link_folder_value[ROI]
        matter = "WM" if "WM" in ROI else "GM"
        statitic_folder = {}

        # Statistics for base folder
        for param_name in cfg.settings.polarimetric_parameters:
            mask_px = np.logical_and(mask_pixels, mask_to_propagate == value_in_mask)
            values_parameter = MM[param_name][mask_px]
            stats = get_statistics(
                values_parameter,
                histogram_parameters[param_name],
                param_name
            )
            statitic_folder[param_name] = stats
        statistics[ROI][base_folder] = statitic_folder

        create_masked_image(
            np.array(intensity_image),
            mask_to_propagate == value_in_mask,
            path_folder_50x50 / ROI / f"{base_folder}_selected.png"
        )

        # Statistics for propagated folders
        for folder in all_folders:
            mask = propagated_masks[folder] == value_in_mask
            mask_px = np.logical_and(all_pixels_masks[folder], propagated_masks[folder] == value_in_mask)
            statitic_folder = {}
            if np.sum(mask) == 0:
                for param_name in cfg.settings.polarimetric_parameters:
                    statitic_folder[param_name] = [math.nan] * 4
            else:
                valid_points = np.logical_and(all_masks[folder][matter], mask, mask_px)
                all_sum = np.sum(mask)
                proportion = np.sum(valid_points) / all_sum
                threshold = pixels_per_ROI * 0.9 if instrument == 'IMPV1' else pixels_per_ROI * 0.01
                if proportion < 0.90 or all_sum < threshold:
                    for param_name in cfg.settings.polarimetric_parameters:
                        statitic_folder[param_name] = [math.nan] * 4
                else:
                    for param_name in cfg.settings.polarimetric_parameters:
                        values_parameter = all_MMs[folder][param_name][valid_points]
                        stats = get_statistics(
                            values_parameter,
                            histogram_parameters[param_name],
                            param_name
                        )
                        statitic_folder[param_name] = stats
            statistics[ROI][folder.stem] = statitic_folder
            create_masked_image(
                all_intensity_images[folder],
                mask,
                path_folder_50x50 / ROI / f"{folder.stem}_selected.png"
            )
        statistics[ROI] = sort_stats_dict(statistics[ROI])

    # Convert statistics to pandas DataFrames and save as Excel
    pandas_stats = create_pandas_stats(statistics)
    for ROI, df in pandas_stats.items():
        df.to_excel(path_folder_50x50 / ROI / 'combined.xlsx')