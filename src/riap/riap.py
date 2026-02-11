from pathlib import Path
import os
import shutil
import pickle
import numpy as np
import omegaconf
from tqdm import tqdm
from PIL import Image
import cv2
import uuid
import math
import pandas as pd
from loguru import logger
import sys
from omegaconf import OmegaConf

try:    
    import matlab.engine
except ImportError:
    print(" [warning] MATLAB engine for Python is not installed. Elastix alignment will not work.")

import subprocess

from riap.helpers import (
    create_masked_image, get_masks, load_data_mm, create_pandas_stats, get_square_coordinates,
    sort_stats_dict, get_all_folders, move_computed_folders, get_angle, get_statistics,
    get_all_values_cv, pad_dataframe_with_nans, align_with_sitk, generate_config_file
)


def load_config(config_fname = "IMPV1.yaml") -> dict:
    """
    Load YAML configuration and apply any command-line overrides.

    Parameters
    ----------
    argv : list[str]
        Command-line arguments, typically sys.argv.

    Returns
    -------
    cfg : OmegaConf.DictConfig
        Loaded configuration with updated values.
    """
    cfg_path = get_default_config_path(config_fname=config_fname)
    if not cfg_path.exists():
        logger.error(f"Config file not found: {cfg_path}")
        sys.exit(1)

    cfg = OmegaConf.load(cfg_path)

    # Safely convert known path fields
    for path_field in cfg.paths:
        cfg.paths[path_field] = Path(cfg.paths[path_field])

    return cfg

def get_default_config_path(config_path = None, config_fname = "default.yaml") -> Path:
    """
    Returns the default configuration file path for gliometer.
    """
    if config_path:
        return Path(config_path).expanduser().resolve()
    return (Path(__file__).resolve().parents[2] / "configs" / config_fname).resolve()



class Riap:
    """
    The Riap class validates and stores configuration parameters for data processing.
    Handles ROI selection, mask creation, alignment, and propagation.
    """
    def __init__(
        self,
        cfg: dict,
        data_path: str = None,
        path_output: str = None,
        time_base: str = None,
        PDDN: bool = None,
        metric: str = None,
        output_alignement_folder: str = None,
        tissue_types: list = None,
        polarimetric_parameters: list = None,
        alignment_method: str = None,
        instrument: str = None,
        wavelength: str = None
    ):
        self.cfg = cfg

        if isinstance(data_path, str):
            self.cfg.paths.data_path = Path(data_path).expanduser().resolve()
            logger.info(f"Data path set to: {self.cfg.paths.data_path}")
        if not self.cfg.paths.data_path.exists() or not self.cfg.paths.data_path.is_dir():
            raise ValueError(f"The path '{self.cfg.paths.data_path}' does not exist or is not a directory.")
        self.data_path = self.cfg.paths.data_path
        
        if isinstance(time_base, str):
            self.cfg.settings.time_base = time_base
            logger.info(f"Time base set to: {self.cfg.settings.time_base}")
        if not isinstance(self.cfg.settings.time_base, str):
            raise TypeError("time_base must be a string.")
        self.time_base = self.cfg.settings.time_base

        if isinstance(PDDN, bool):
            self.cfg.settings.PDDN = PDDN
            logger.info(f"PDDN set to: {self.cfg.settings.PDDN}")
        if not isinstance(self.cfg.settings.PDDN, bool):
            raise TypeError("PDDN must be a boolean.")
        self.PDDN = self.cfg.settings.PDDN

        if isinstance(metric, str):
            self.cfg.settings.metric = metric
            logger.info(f"Metric set to: {self.cfg.settings.metric}")
        if not isinstance(self.cfg.settings.metric, str) or self.cfg.settings.metric not in ['mean', 'max', 'median']:
            raise ValueError("metric must be one of 'mean', 'max', or 'median'.")
        self.metric = self.cfg.settings.metric

        if isinstance(output_alignement_folder, str):
            self.cfg.paths.output_alignement_folder = Path(output_alignement_folder).expanduser().resolve()
            logger.info(f"Output alignment folder set to: {self.cfg.paths.output_alignement_folder}")
        if not isinstance(self.cfg.paths.output_alignement_folder, (str, Path)):
            raise TypeError("output_alignement_folder must be a string or Path object.")
        self.output_alignement_folder = self.cfg.paths.output_alignement_folder

        if isinstance(tissue_types, list):
            self.cfg.settings.tissue_types = tissue_types
            logger.info(f"Tissue types set to: {self.cfg.settings.tissue_types}")
        if not isinstance(self.cfg.settings.tissue_types, (list, omegaconf.listconfig.ListConfig)) or not all(isinstance(t, str) for t in self.cfg.settings.tissue_types):
            raise TypeError("tissue_types must be a list of strings.")
        self.tissue_types = self.cfg.settings.tissue_types

        if isinstance(polarimetric_parameters, list):
            self.cfg.settings.polarimetric_parameters = polarimetric_parameters
            logger.info(f"Polarimetric parameters set to: {self.cfg.settings.polarimetric_parameters}")
        if not isinstance(self.cfg.settings.polarimetric_parameters, (list, omegaconf.listconfig.ListConfig)) or not all(isinstance(p, str) for p in self.cfg.settings.polarimetric_parameters):
            raise TypeError("polarimetric_parameters must be a list of strings.")
        self.polarimetric_parameters = self.cfg.settings.polarimetric_parameters

        if isinstance(alignment_method, str):
            self.cfg.settings.alignment_method = alignment_method
            logger.info(f"Alignment method set to: {self.cfg.settings.alignment_method}")
        if not isinstance(self.cfg.settings.alignment_method, str) or self.cfg.settings.alignment_method not in ['elastix', 'superglue']:
            raise ValueError("alignment_method must be either 'elastix' or 'superglue'.")
        self.alignment_method = self.cfg.settings.alignment_method

        if isinstance(path_output, str):
            self.cfg.paths.output_path = Path(path_output).expanduser().resolve()
            logger.info(f"Output path set to: {self.cfg.paths.output_path}")
        else:
            self.cfg.paths.output_path = self.cfg.paths.output_path / self.alignment_method
        self.cfg.paths.output_path.mkdir(parents=True, exist_ok=True)
        self.output_path = self.cfg.paths.output_path

        if isinstance(instrument, str):
            self.cfg.settings.instrument = instrument
            logger.info(f"Instrument set to: {self.cfg.settings.instrument}")
        if not isinstance(self.cfg.settings.instrument, str) or self.cfg.settings.instrument not in ['IMPV1', 'IMPV2']:
            raise ValueError("instrument must be either 'IMPV1' or 'IMPV2'.")
        self.instrument = self.cfg.settings.instrument

        if isinstance(wavelength, str):
            self.cfg.settings.wavelength = wavelength
            logger.info(f"Wavelength set to: {self.cfg.settings.wavelength}")
        if not isinstance(self.cfg.settings.wavelength, str):
            raise TypeError("wavelength must be a string.")
        self.wavelength = self.cfg.settings.wavelength
        
        logger.info("Input parameters validated successfully")
        logger.info("Riap instance initiated successfully\n")
        
        # Load configuration and setup folders/masks
        self.__load_parameters()
        self.__create_alignment_folder()
        logger.info(f"Alignment folders will be available in: {self.cfg.paths.output_alignement_folder}")
        
        self.__get_the_base_dirs()
        logger.info(f"Base directories identified: {[str(dir) for dir in self.base_dirs]}")
        
        self.__create_the_masks()
        logger.info("Tissue masks generated successfully")
        logger.info("Riap instance created successfully")

    def __load_parameters(self):
        self.param_ROIs = self.cfg.rois
        self.histogram_parameters = self.cfg.histograms
        self.pixels_per_ROI = self.param_ROIs['square_size'] ** 2
        
    def __create_alignment_folder(self):
        """Create alignment and temporary folders for processing."""
        # Determine base directory for temporary files
        self.output_alignement_folder.mkdir(parents=True, exist_ok=True)
        self.path_alignment = self.output_alignement_folder / 'alignment'
        self.path_alignment.mkdir(parents=True, exist_ok=True)   
        self.path_to_align = self.path_alignment / 'to_align'
        self.path_to_align.mkdir(parents=True, exist_ok=True)
        self.path_aligned = self.path_alignment / 'aligned'
        self.path_aligned.mkdir(parents=True, exist_ok=True)
        (self.path_aligned / "logbooks").mkdir(parents=True, exist_ok=True)
        
    def __get_the_base_dirs(self):
        """Identify base directories i.e., those containing the time_base string, for processing."""
        base_dirs = []
        for path_folder in self.data_path.iterdir():
            if self.time_base in path_folder.name and path_folder.is_dir():
                base_dirs.append(path_folder)
        self.base_dirs = base_dirs
        
    def __create_the_masks(self):
        """Create masks for all folders in the data path."""
        self.all_folders = [Path(folder) for folder in self.data_path.iterdir() if folder.is_dir()]
        self.all_masks = {}
        for folder_of_interest in tqdm(self.all_folders, desc="Creating masks for folders"):
            self.all_masks[folder_of_interest] = get_masks(folder_of_interest)
            
    def process(self):
        """Main processing loop for all base directories."""
        for idx_folder, self.path_folder in enumerate(self.base_dirs):
            
            # Remove previously acquired data
            self.path_polarimetry_wavelength = self.path_folder / self.cfg.default_paths.polarimetry
            self.path_folder_50x50 = self.path_folder / self.cfg.default_paths._50x50_images
            shutil.rmtree(self.path_folder_50x50, ignore_errors=True)
            self.path_folder_50x50.mkdir(parents=True, exist_ok=True)
                
            logger.info(f"Processing {self.path_folder.name}: {idx_folder}/{len(self.base_dirs)}\n")
            propagation_lists = {}
            self.link_folder_value = {}
            
            self.MM = load_data_mm(self.path_polarimetry_wavelength / 'MM.npz', angle = 0)
            if self.instrument == 'IMPV1':
                self.mask_pixels = np.logical_and(self.MM['Msk'], ~self.MM['dilated_mask'])
            else:
                self.mask_pixels = np.logical_and(self.MM['Msk'], self.MM['dilated_mask'] == 1)

            self.mask = self.all_masks[self.path_folder]
            self.intensity_image = Image.open(self.path_polarimetry_wavelength / 'Intensity_img.png')
            
            self.all_folders = get_all_folders(self.path_folder, self.time_base, instrument=self.instrument)
            self.mask_to_propagate = np.zeros(self.mask.shape)

            logger.info(f"Found {len(self.all_folders)} folders to propagate to: {[f.name for f in self.all_folders]}")
            
            logger.info("Step 1: Selecting ROIs")
            for self.tissue_type in self.tissue_types:
                self.intensity_image_masked = cv2.imread(str(self.path_polarimetry_wavelength / 'Intensity_img.png'), cv2.IMREAD_GRAYSCALE)
                WM = self.tissue_type == 'WM'
                self.matter_mask = self.mask == 255 if WM else self.mask == 128
                self.grid = np.zeros(self.matter_mask.shape)
                propagation_lists[self.tissue_type] = self.__square_selection()
            
            logger.info("Step 2: Aligning images and propagating ROIs")
            self.__create_folder_to_align()  
            self.__do_alignment()
            logger.info("Alignment completed")
            move_computed_folders(self.path_to_align, self.path_aligned)
            # change the current path variable
            self.current_path_alignment = Path(
                str(self.current_path_alignment).replace(f"{os.sep}to_align{os.sep}", f"{os.sep}aligned{os.sep}")
            )
            logger.success("Folders aligned successfully")
            
            logger.info("Step 3: Propagating ROIs and collecting statistics")
            self.__propagate_roi()
            logger.success(f"Results saved in {self.path_folder_50x50}\n")
        
    
    def __square_selection(self):
        """
        Select random square ROIs for the current tissue type and update masks.
        Returns a list of propagation results.
        """
        propagation_list = []
        exit_error = False
        square_counter = 0
        
        while square_counter < self.param_ROIs["number_of_random_squares"] and not exit_error:
            new_folder_name = f"{self.tissue_type}_{square_counter + 1}"
            path_output = self.path_folder_50x50 / new_folder_name
                
            try:
                coordinates_long, self.grid = get_square_coordinates(
                    self.matter_mask, self.mask_pixels, self.param_ROIs['square_size'],
                    self.grid, treshold_valid_pixels=0.95 if self.instrument == 'IMPV1' else 0.01
                )
                if coordinates_long is None:
                    exit_error = True
                    logger.warning(f"Could not find more squares for {self.tissue_type}")
                    break
            except Exception as e:
                exit_error = True
                logger.warning(f"Could not find more squares for {self.tissue_type}")
                break
            
            path_output.mkdir(parents=True, exist_ok=True)
            square_counter += 1
                        
            # Write the coordinates to a txt file for reuse
            with open(path_output / 'coordinates.txt', 'w') as textfile:
                for element in coordinates_long:
                    textfile.write(str(element) + "\n")

            # Update intensity and mask images
            self.intensity_image_masked[coordinates_long[2]: coordinates_long[3], coordinates_long[0]:coordinates_long[1]] = 0 if self.tissue_type == 'WM' else 255
            self.mask_to_propagate[coordinates_long[2]: coordinates_long[3], coordinates_long[0]:coordinates_long[1]] = square_counter + self.param_ROIs["number_of_random_squares"] if self.tissue_type == 'WM' else square_counter
            self.link_folder_value[new_folder_name] = square_counter + self.param_ROIs["number_of_random_squares"] if self.tissue_type == 'WM' else square_counter
            
        Image.fromarray(self.intensity_image_masked).save(self.path_folder_50x50 / f'{self.tissue_type}_selection.png')

        logger.success(f"Selected {square_counter} ROIs for {self.tissue_type}.")
        return propagation_list

    def __create_folder_to_align(self):
        """
        Create a unique folder for alignment and copy necessary files.
        """
        unique_id = str(uuid.uuid4())
        dt_string = self.path_folder.name + '__' + unique_id
        self.current_path_alignment = self.path_to_align / dt_string
        self.current_path_alignment.mkdir(parents=True, exist_ok=True)
        (self.current_path_alignment / 'mask').mkdir(parents=True, exist_ok=True)
        Image.fromarray(self.mask_to_propagate.astype(np.uint8)).save(self.current_path_alignment / 'mask' / 'mask.png')
        shutil.copy(self.path_polarimetry_wavelength / 'Intensity_img.png', self.current_path_alignment / (self.path_folder.name + '_ref_align.png'))

        for folder in self.all_folders:
            shutil.copy(self.data_path / folder / self.cfg.default_paths.polarimetry / 'Intensity_img.png', self.current_path_alignment / (folder.stem + '.png'))
         
    def __do_alignment(self):
        """
        Call the MATLAB pipeline to align images and propagate ROIs.
        """
        if self.alignment_method == 'elastix':
            self.__elastix_alignment()
        elif self.alignment_method == 'superglue':
            self.__superglue_alignment()
            
    def __elastix_alignment(self):
        """
        Perform image alignment using Elastix via MATLAB engine.
        """
        dir_path = self.cfg.paths.elastix_path
        (dir_path / 'RegistrationElastix' / 'temp').mkdir(parents=True, exist_ok=True)
        with open(dir_path / 'RegistrationElastix' / 'temp' / 'path_alignment_batch.txt', 'w') as f:
            f.write(str(self.path_to_align))
        FixPattern = '_ref_align'
        with open(dir_path / 'RegistrationElastix' / 'temp' / 'FixPattern.txt', 'w') as f:
            f.write(FixPattern)
        Tag = 'AffineElastic'
        with open(dir_path / 'RegistrationElastix' / 'temp' / 'Tag.txt', 'w') as f:
            f.write(Tag)

        scripts_path = dir_path / 'RegistrationElastix' / 'RegistrationScripts'
        generate_config_file(self.cfg.paths.elastix_binaries, scripts_path)
        eng = matlab.engine.start_matlab()
        eng.cd(str(scripts_path), nargout=0)
        s = eng.genpath('0_NIfTI_IO')
        eng.addpath(s, nargout=0)
        eng.python_call(nargout=0)
       
    def __superglue_alignment(self):
        """
        Perform image alignment using SuperGlue.
        """
        invreg_dir = self.current_path_alignment / "invReg"
        invreg_dir.mkdir(parents=True, exist_ok=True)
        
        mask = cv2.imread(str(self.current_path_alignment / 'mask' / 'mask.png'), cv2.IMREAD_GRAYSCALE)
        for folder in self.all_folders:
            pair_dir = self.current_path_alignment / folder.stem
            pair_dir.mkdir(parents=True, exist_ok=True)

            shutil.copy(self.current_path_alignment / (self.path_folder.stem + '_ref_align.png'), pair_dir / f"fixed.png")
            shutil.copy(self.current_path_alignment / (folder.stem + '.png'), pair_dir / f"moving.png")
            
            cmd = [
                    'python', str(self.cfg.paths.superglue / 'demo_superglue.py'),
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
            with open(invreg_dir / f"{folder}_angle.txt", "w") as f:
                f.write(str(theta))
            
            aligned_images = align_with_sitk(fixed_arr, mask, matching_points)
            aligned_mask = aligned_images[0]
            mask_path = invreg_dir / f"mask_PrpgTo_{folder.stem}.png"
            cv2.imwrite(mask_path, aligned_mask)
    
    def __propagate_roi(self):
        """
        Propagate selected ROIs to all folders and collect statistics.
        Saves results as Excel files.
        """
        all_ROIs = [f.name for f in self.path_folder_50x50.iterdir() if f.is_dir()]
        all_masks, all_angles, all_MMs, all_intensity_images, propagated_masks, all_pixels_masks = {}, {}, {}, {}, {}, {}
        path_parameter_files = self.current_path_alignment / "invReg"

        # Load masks, angles, MM data, and intensity images for all folders
        for folder in self.all_folders:
            mask = get_masks(folder)

            all_masks[folder] = {'WM': mask == 255, 'GM': mask == 128}
            if self.alignment_method == 'superglue':
                with open(path_parameter_files / f"{folder}_angle.txt", "r") as f:
                    all_angles[folder] = float(f.read())
            elif self.alignment_method == 'elastix':
                all_angles[folder] = get_angle(path_parameter_files / f"{folder.stem}_AffineElastic_TransformParameters_0.txt")

            path_polarimetry_wavelength = folder / self.cfg.default_paths.polarimetry
            all_MMs[folder] = load_data_mm(path_polarimetry_wavelength / 'MM.npz', angle=all_angles[folder])
            all_pixels_masks[folder] = np.logical_and(all_MMs[folder]['Msk'], all_MMs[folder]['dilated_mask'])
            all_intensity_images[folder] = cv2.imread(path_polarimetry_wavelength / 'Intensity_img.png', cv2.IMREAD_GRAYSCALE)

            if self.alignment_method == 'elastix':
                propagated_masks[folder] = cv2.imread(
                    path_parameter_files / f"mask_PrpgTo_{folder.stem}_AffineElastic_TransformParameters_0.png",
                    cv2.IMREAD_GRAYSCALE
                )
            elif self.alignment_method == 'superglue':
                propagated_masks[folder] = cv2.imread(
                    path_parameter_files / f"mask_PrpgTo_{folder.stem}.png",
                    cv2.IMREAD_GRAYSCALE
                )
        
        statistics = {}

        base_folder = self.path_folder.name
        for ROI in tqdm(all_ROIs, desc="Processing ROIs"):
            statistics[ROI] = {}
            value_in_mask = self.link_folder_value[ROI]
            matter = "WM" if "WM" in ROI else "GM"
            statitic_folder = {}

            # Statistics for base folder
            for param_name in self.cfg.settings.polarimetric_parameters:
                mask_px = np.logical_and(self.mask_pixels, self.mask_to_propagate == value_in_mask)
                values_parameter = self.MM[param_name][mask_px]
                stats = get_statistics(
                    values_parameter,
                    self.histogram_parameters[param_name],
                    param_name
                )
                statitic_folder[param_name] = stats
            statistics[ROI][base_folder] = statitic_folder

            create_masked_image(
                np.array(self.intensity_image),
                self.mask_to_propagate == value_in_mask,
                self.path_folder_50x50 / ROI / f"{base_folder}_selected.png"
            )

            # Statistics for propagated folders
            for folder in self.all_folders:
                mask = propagated_masks[folder] == value_in_mask
                mask_px = np.logical_and(all_pixels_masks[folder], propagated_masks[folder] == value_in_mask)
                statitic_folder = {}
                if np.sum(mask) == 0:
                    for param_name in self.cfg.settings.polarimetric_parameters:
                        statitic_folder[param_name] = [math.nan] * 4
                else:
                    valid_points = np.logical_and(all_masks[folder][matter], mask, mask_px)
                    all_sum = np.sum(mask)
                    proportion = np.sum(valid_points) / all_sum
                    if proportion < 0.90 or all_sum < self.pixels_per_ROI * 0.9 if self.instrument == 'IMPV1' else all_sum < self.pixels_per_ROI * 0.01:
                        for param_name in self.cfg.settings.polarimetric_parameters:
                            statitic_folder[param_name] = [math.nan] * 4
                    else:
                        for param_name in self.cfg.settings.polarimetric_parameters:
                            values_parameter = all_MMs[folder][param_name][valid_points]
                            stats = get_statistics(
                                values_parameter,
                                self.histogram_parameters[param_name],
                                param_name
                            )
                            statitic_folder[param_name] = stats
                statistics[ROI][folder.stem] = statitic_folder
                create_masked_image(
                    all_intensity_images[folder],
                    mask,
                    self.path_folder_50x50 / ROI / f"{folder.stem}_selected.png"
                )
            statistics[ROI] = sort_stats_dict(statistics[ROI])

        # Convert statistics to pandas DataFrames and save as Excel
        pandas_stats = create_pandas_stats(statistics)
        for ROI, df in pandas_stats.items():
            df.to_excel(self.path_folder_50x50 / ROI / 'combined.xlsx')
            
    def compare_parameters(self):
        """
        Compare parameters across all ROIs and save combined statistics.
        """
        self.all_ROIs = []
        for base_dir in self.base_dirs:
            self.path_folder_50x50 = base_dir / self.cfg.default_paths._50x50_images

            roi_files = [
                f for f in self.path_folder_50x50.iterdir() if not '.png' in f.name and f.is_dir()
            ]
            self.all_ROIs += roi_files
        
        self.__load_all_values()
        self.all_values_cv = get_all_values_cv(self.all_values)
        self.__export_results()
        
    def __load_all_values(self):
        """
        Load all values from combined Excel files for comparison.
        """
        all_values = {}
        for tissue_type in self.tissue_types:
            all_values[tissue_type] = {}
            for parameter in self.cfg.settings.polarimetric_parameters:
                all_values[tissue_type][parameter] = []

        for ROI in self.all_ROIs:
            df = pd.read_excel(ROI / 'combined.xlsx', index_col = 0)
            tissue_type = os.path.basename(ROI).split('_')[0]
            for parameter in self.cfg.settings.polarimetric_parameters:
                if parameter == 'azimuth':
                    values = list(df[df['parameter'] == parameter]['mean'])
                else:
                    values = list(df[df['parameter'] == parameter][self.metric])
                all_values[tissue_type][parameter].append(values)

        for tissue, values in all_values.items():
            for param, val in values.items():
                all_values[tissue][param] = pd.DataFrame(val).T
                
        self.all_values = all_values
        
    def __export_results(self):
        """
        Export combined statistics and coefficient of variation to Excel files.
        Uses padding to ensure consistent DataFrame sizes.
        """
        logger.info(f"Exporting combined statistics to Excel files in {self.output_path}")
        measurement_per_case = self.param_ROIs['max_number_of_random_squares'] * len(self.base_dirs)

        for parameter in self.cfg.settings.polarimetric_parameters:
            df = pd.concat(
                [
                    pad_dataframe_with_nans(self.all_values['GM'][parameter], measurement_per_case),
                    pad_dataframe_with_nans(self.all_values['WM'][parameter], measurement_per_case),
                ],
                axis=1
            )
            df.to_excel(self.output_path / f"{parameter}_prism.xlsx")

            df = pd.concat(
                [
                    pad_dataframe_with_nans(self.all_values_cv['GM'][parameter], measurement_per_case),
                    pad_dataframe_with_nans(self.all_values_cv['WM'][parameter], measurement_per_case),
                ],
                axis=1
            )
            df.to_excel(self.output_path / f"{parameter}_prism_cv.xlsx")