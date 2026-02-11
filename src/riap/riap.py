import os
import shutil
import pickle
import numpy as np
from tqdm import tqdm
from PIL import Image
import cv2
import uuid
import math
import pandas as pd
try:    
    import matlab.engine
except ImportError:
    print(" [warning] MATLAB engine for Python is not installed. Elastix alignment will not work.")
import subprocess
from riap.helpers import (
    create_masked_image, get_masks, load_parameters_ROIs, load_data_mm,
    create_pandas_stats, get_square_coordinates, sort_stats_dict, get_all_folders,
    move_computed_folders, get_angle, get_statistics,
    load_histogram_parameters, get_all_values_cv, pad_dataframe_with_nans,
    get_superglue_path, align_with_sitk
)

class Riap:
    """
    The Riap class validates and stores configuration parameters for data processing.
    Handles ROI selection, mask creation, alignment, and propagation.
    """
    def __init__(
        self,
        data_path: str,
        path_output: str,
        time_base: str,
        PDDN: bool = False,
        metric: str = 'median',
        output_alignement_folder: str = None,
        tissue_types: list = ['WM', 'GM'],
        polarimetric_parameters: list = ['linR', 'totD', 'azimuth_local_var', 'totP', 'azimuth'],
        alignment_method: str = 'elastix',
        instrument: str = 'IMPV1'
    ):
        # Validate input parameters
        if not os.path.exists(data_path):
            raise ValueError(f"The path '{data_path}' does not exist.")
        self.data_path = data_path
        
        if not isinstance(time_base, str):
            raise TypeError("time_base must be a string.")
        self.time_base = time_base

        if not isinstance(path_output, str):
            raise TypeError("path_output must be a string.")
        self.path_output = path_output
        os.makedirs(self.path_output, exist_ok=True)
        
        if not isinstance(PDDN, bool):
            raise TypeError("PDDN must be a boolean.")
        self.PDDN = PDDN
        
        if not isinstance(metric, str) or metric not in ['mean', 'max', 'median']:
            raise ValueError("metric must be one of 'mean', 'max', or 'median'.")
        self.metric = metric
        
        if not isinstance(output_alignement_folder, (str, type(None))):
            raise TypeError("output_alignement_folder must be a string or None.")
        self.output_alignement_folder = output_alignement_folder
        
        if not isinstance(tissue_types, list) or not all(isinstance(t, str) for t in tissue_types):
            raise TypeError("tissue_types must be a list of strings.")
        self.tissue_types = tissue_types
        
        if not isinstance(polarimetric_parameters, list) or not all(isinstance(p, str) for p in polarimetric_parameters):
            raise TypeError("polarimetric_parameters must be a list of strings.")
        self.polarimetric_param_names = polarimetric_parameters
        
        if not isinstance(alignment_method, str) or alignment_method not in ['elastix', 'superglue']:
            raise ValueError("alignment_method must be either 'elastix' or 'superglue'.")
        self.alignment_method = alignment_method
        
        if not isinstance(instrument, str) or instrument not in ['IMPV1', 'IMPV2']:
            raise ValueError("instrument must be either 'IMPV1' or 'IMPV2'.")
        self.instrument = instrument
        print(" [info] Input parameters validated successfully")
        print(" [info] Riap instance initiated successfully\n")
        
        # Load configuration and setup folders/masks
        self.__load_parameters()
        self.__create_alignment_folder()
        print(f" [info] Alignment folders will be available in: {self.path_alignment}")
        
        self.__get_the_base_dirs()
        print(" [info] Base directories identified: ", self.base_dirs)
        
        self.__create_the_masks()
        print(" [info] Tissue masks generated successfully")
        print(" [info] Riap instance created successfully\n")

    def __load_parameters(self):
        """Load ROI, polarimetric, and histogram parameters from pre-determined text files."""
        self.param_ROIs = load_parameters_ROIs(self.instrument)
        self.histogram_parameters = load_histogram_parameters()
        self.pixels_per_ROI = self.param_ROIs['square_size'] ** 2
        
    def __create_alignment_folder(self):
        """Create alignment and temporary folders for processing."""
        # Determine base directory for temporary files (either user-defined or default)
        if self.output_alignement_folder:
            dir_path = self.output_alignement_folder
        else:
            dir_path = os.path.dirname(os.path.realpath(__file__)).split(f'src{os.sep}riap')[0]
        self.path_temp = os.path.join(dir_path, 'temp')
        os.makedirs(self.path_temp, exist_ok=True)
        
        # Create alignment folders
        self.path_alignment = os.path.join(self.path_temp, 'alignment')
        os.makedirs(self.path_alignment, exist_ok=True)
        
        self.path_to_align = os.path.join(self.path_alignment, 'to_align')
        shutil.rmtree(self.path_to_align, ignore_errors=True)
        os.makedirs(self.path_to_align, exist_ok=True)
                
        self.path_aligned = os.path.join(self.path_alignment, 'aligned')
        os.makedirs(self.path_aligned, exist_ok=True)
        os.makedirs(os.path.join(self.path_aligned, 'logbooks'), exist_ok=True)
        
    def __get_the_base_dirs(self):
        """Identify base directories i.e., those containing the time_base string, for processing."""
        base_dirs = []
        for folder in os.listdir(self.data_path):
            path_folder = os.path.join(self.data_path, folder)
            if self.time_base in folder:
                base_dirs.append(path_folder)
        self.base_dirs = base_dirs
        
    def __create_the_masks(self):
        """Create masks for all folders in the data path."""
        self.all_folders = os.listdir(self.data_path)
        self.all_masks = {}
        for folder_of_interest in tqdm(self.all_folders, desc="Creating masks for folders"):
            self.all_masks[folder_of_interest] = get_masks(os.path.join(self.data_path, folder_of_interest))
            
    def process(self):
        """Main processing loop for all base directories."""
        for idx_folder, self.path_folder in enumerate(self.base_dirs):
            
            # Remove previously acquired data
            if self.instrument == 'IMPV1':
                path_results = os.path.join(self.path_folder, 'polarimetry/550nm/50x50_images')
            else:
                path_results = os.path.join(self.path_folder, 'RIAP_results')
            shutil.rmtree(path_results, ignore_errors=True)
            os.makedirs(path_results, exist_ok=True)
                
            print(f" [info] Processing {self.path_folder}: {idx_folder}/{len(self.base_dirs)}\n")
            propagation_lists = {}
            self.link_folder_value = {}
            
            if self.instrument == 'IMPV1':
                self.path_polarimetry_wavelength = os.path.join(self.path_folder, 'polarimetry', self.param_ROIs["wavelength"])
                self.path_folder_50x50 = os.path.join(self.path_polarimetry_wavelength, '50x50_images')
            else:
                self.path_polarimetry_wavelength = os.path.join(self.path_folder, 'polarimetry', "630_Image_Number_LQ", self.param_ROIs["wavelength"])
                self.path_folder_50x50 = os.path.join(self.path_folder, 'RIAP_results')

            self.MM = load_data_mm(os.path.join(self.path_polarimetry_wavelength, 'MM.npz'), angle = 0)
            if self.instrument == 'IMPV1':
                self.mask_pixels = np.logical_and(self.MM['Msk'], ~self.MM['dilated_mask'])
            else:
                self.mask_pixels = np.logical_and(self.MM['Msk'], self.MM['dilated_mask'] == 1)

            self.mask = self.all_masks[os.path.basename(self.path_folder)]
            self.intensity_image = Image.open(os.path.join(self.path_polarimetry_wavelength, 'Intensity_img.png'))
            
            self.base_name = os.path.basename(self.path_folder)
            parent_dir = os.path.dirname(self.path_folder)
            self.all_folders = get_all_folders(parent_dir, self.base_name, self.time_base, instrument=self.instrument)
            self.mask_to_propagate = np.zeros(self.mask.shape)

            print(f" [info] Found {len(self.all_folders)} folders to propagate to: {self.all_folders}")
            
            print(" [info] Selecting ROIs")
            # Select ROIs for each tissue type
            for self.tissue_type in self.tissue_types:
                self.intensity_image_masked = cv2.imread(
                    os.path.join(self.path_polarimetry_wavelength, 'Intensity_img.png'), cv2.IMREAD_GRAYSCALE
                )
                WM = self.tissue_type == 'WM'
                self.matter_mask = self.mask == 255 if WM else self.mask == 128
                self.grid = np.zeros(self.matter_mask.shape)
                propagation_lists[self.tissue_type] = self.__square_selection()
            
            # Prepare alignment folders and run alignment
            self.__create_folder_to_align()  
            self.__do_alignment()
            print(" [info] Alignment completed")
            
            move_computed_folders(self.path_to_align, self.path_aligned)
            
            # change the current path variable
            self.current_path_alignment = self.current_path_alignment.replace(
                f"{os.sep}to_align{os.sep}", f"{os.sep}aligned{os.sep}"
            )
            
            print(" [info] Propagating ROIs and collecting statistics")
            self.__propagate_roi()
            print(f" [info] Results saved in {self.path_folder_50x50}\n")
        
    
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
            path_output = os.path.join(self.path_folder_50x50, new_folder_name)
                
            try:
                coordinates_long, self.grid = get_square_coordinates(
                    self.matter_mask, self.mask_pixels, self.param_ROIs['square_size'],
                    self.grid, treshold_valid_pixels=0.95 if self.instrument == 'IMPV1' else 0.01
                )
                if coordinates_long is None:
                    exit_error = True
                    print(f" [warning] Could not find more squares for {self.tissue_type}")
                    break
            except Exception as e:
                exit_error = True
                print(f" [warning] Could not find more squares for {self.tissue_type}")
                break
            
            os.makedirs(path_output, exist_ok=True)
            square_counter += 1
                        
            # Write the coordinates to a txt file for reuse
            with open(os.path.join(path_output, 'coordinates.txt'), 'w') as textfile:
                for element in coordinates_long:
                    textfile.write(str(element) + "\n")

            # Update intensity and mask images
            self.intensity_image_masked[coordinates_long[2]: coordinates_long[3], coordinates_long[0]:coordinates_long[1]] = 0 if self.tissue_type == 'WM' else 255
            self.mask_to_propagate[coordinates_long[2]: coordinates_long[3], coordinates_long[0]:coordinates_long[1]] = square_counter + self.param_ROIs["number_of_random_squares"] if self.tissue_type == 'WM' else square_counter
            self.link_folder_value[new_folder_name] = square_counter + self.param_ROIs["number_of_random_squares"] if self.tissue_type == 'WM' else square_counter
            
        print(f" [info] Selected {square_counter} ROIs for {self.tissue_type}.")
        # Save the masked intensity image
        Image.fromarray(self.intensity_image_masked).save(os.path.join(self.path_folder_50x50, f'{self.tissue_type}_selection.png'))
        
        return propagation_list


    def __create_folder_to_align(self):
        """
        Create a unique folder for alignment and copy necessary files.
        """
        unique_id = str(uuid.uuid4())
        dt_string = os.path.basename(self.path_folder) + '__' + unique_id
        self.current_path_alignment = os.path.join(self.path_to_align, dt_string)
        os.makedirs(self.current_path_alignment, exist_ok=True)
        os.makedirs(os.path.join(self.current_path_alignment, 'mask'), exist_ok=True)
        Image.fromarray(self.mask_to_propagate.astype(np.uint8)).save(os.path.join(self.current_path_alignment, 'mask', 'mask.png'))
        shutil.copy(
            os.path.join(self.path_polarimetry_wavelength, 'Intensity_img.png'),
            os.path.join(self.current_path_alignment, os.path.basename(self.path_folder) + '_ref_align.png')
        )
        for folder in self.all_folders:
            if self.instrument == 'IMPV1':
                path_polarimetry_wavelength = os.path.join(self.data_path, folder, 'polarimetry', self.param_ROIs["wavelength"],)
            else:
                path_polarimetry_wavelength = os.path.join(self.data_path, folder, 'polarimetry', "630_Image_Number_LQ", self.param_ROIs["wavelength"])
        
            shutil.copy(
                os.path.join(path_polarimetry_wavelength, 'Intensity_img.png'),
                os.path.join(self.current_path_alignment, folder + '.png')
            )
         
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
        dir_path = os.path.dirname(os.path.realpath(__file__))
        os.makedirs(os.path.join(dir_path, 'RegistrationElastix/temp'), exist_ok=True)
        with open(os.path.join(dir_path, 'RegistrationElastix/temp/path_alignment_batch.txt'), 'w') as f:
            f.write(self.path_to_align)
        FixPattern = '_ref_align'
        with open(os.path.join(dir_path, 'RegistrationElastix/temp/FixPattern.txt'), 'w') as f:
            f.write(FixPattern)
        Tag = 'AffineElastic'
        with open(os.path.join(dir_path, 'RegistrationElastix/temp/Tag.txt'), 'w') as f:
            f.write(Tag)
        # generate_config_file(dir_path)
        eng = matlab.engine.start_matlab()
        path = os.path.join(dir_path, r'RegistrationElastix/RegistrationScripts')
        eng.cd(path, nargout=0)
        s = eng.genpath('0_NIfTI_IO')
        eng.addpath(s, nargout=0)
        eng.python_call(nargout=0)
       
    def __superglue_alignment(self):
        """
        Perform image alignment using SuperGlue.
        """
        invreg_dir = os.path.join(self.current_path_alignment, "invReg")
        os.makedirs(invreg_dir, exist_ok=True)
        
        mask = cv2.imread(os.path.join(self.current_path_alignment, 'mask', 'mask.png'), cv2.IMREAD_GRAYSCALE)
        for folder in self.all_folders:
            pair_dir = os.path.join(self.current_path_alignment, folder)
            os.makedirs(pair_dir, exist_ok=True)
            shutil.copy(os.path.join(self.current_path_alignment, self.base_name + '_ref_align.png'),
                        os.path.join(pair_dir, f"fixed.png"))
            shutil.copy(os.path.join(self.current_path_alignment, folder + '.png'),
                        os.path.join(pair_dir, f"moving.png"))
            cmd = [
                    'python', os.path.join(get_superglue_path(), 'demo_superglue.py'),
                    '--input', pair_dir,
                    '--output_dir', pair_dir,
                    "--resize", "-1",
                    "--match_threshold", "0.2",
                    '--no_display'
                ]
            subprocess.run(cmd)
            
            fixed_arr = cv2.imread(os.path.join(pair_dir, f"fixed.png"), cv2.IMREAD_GRAYSCALE)
            with open(os.path.join(pair_dir, f"matches_000000_000001.pickle"), "rb") as f:
                matching_points = pickle.load(f)
                
            M, _ = cv2.estimateAffine2D(matching_points[0], matching_points[1], method=cv2.RANSAC)
            U, _, Vt = np.linalg.svd(M[:, :2])
            R = U @ Vt
            theta = np.arctan2(R[1,0], R[0,0]) * 180/np.pi
            with open(os.path.join(invreg_dir, f"{folder}_angle.txt"), "w") as f:
                f.write(str(theta))
            
            aligned_images = align_with_sitk(fixed_arr, mask, matching_points)
            aligned_mask = aligned_images[0]
            mask_path = os.path.join(invreg_dir, f"mask_PrpgTo_{folder}.png")
            cv2.imwrite(mask_path, aligned_mask)
    
    def __propagate_roi(self):
        """
        Propagate selected ROIs to all folders and collect statistics.
        Saves results as Excel files.
        """
        all_ROIs = [
            f for f in os.listdir(self.path_folder_50x50)
            if os.path.isdir(os.path.join(self.path_folder_50x50, f))
        ]
        all_masks, all_angles, all_MMs, all_intensity_images, propagated_masks, all_pixels_masks = {}, {}, {}, {}, {}, {}
        path_parameter_files = os.path.join(self.current_path_alignment, 'invReg')

        # Load masks, angles, MM data, and intensity images for all folders
        for folder in self.all_folders:
            mask = get_masks(os.path.join(self.data_path, folder))
            all_masks[folder] = {'WM': mask == 255, 'GM': mask == 128}
            if self.alignment_method == 'superglue':
                with open(os.path.join(path_parameter_files, f"{folder}_angle.txt"), "r") as f:
                    all_angles[folder] = float(f.read())
            elif self.alignment_method == 'elastix':
                all_angles[folder] = get_angle(
                    os.path.join(path_parameter_files, f"{folder}_AffineElastic_TransformParameters_0.txt")
                )
            if self.instrument == 'IMPV1':
                path_polarimetry_wavelength = os.path.join(self.data_path, folder, 'polarimetry', self.param_ROIs["wavelength"],)
            else:
                path_polarimetry_wavelength = os.path.join(self.data_path, folder, 'polarimetry', "630_Image_Number_LQ", self.param_ROIs["wavelength"])
            all_MMs[folder] = load_data_mm(
                os.path.join(path_polarimetry_wavelength, 'MM.npz'),
                angle=all_angles[folder]
            )
            all_pixels_masks[folder] = np.logical_and(all_MMs[folder]['Msk'], all_MMs[folder]['dilated_mask'])
            all_intensity_images[folder] = cv2.imread(
                os.path.join(path_polarimetry_wavelength, 'Intensity_img.png'),
                cv2.IMREAD_GRAYSCALE
            )
            if self.alignment_method == 'elastix':
                propagated_masks[folder] = cv2.imread(
                    os.path.join(path_parameter_files, f"mask_PrpgTo_{folder}_AffineElastic_TransformParameters_0.png"),
                    cv2.IMREAD_GRAYSCALE
                )
            elif self.alignment_method == 'superglue':
                propagated_masks[folder] = cv2.imread(
                    os.path.join(path_parameter_files, f"mask_PrpgTo_{folder}.png"),
                    cv2.IMREAD_GRAYSCALE
                )
        
        statistics = {}
        for ROI in tqdm(all_ROIs, desc="Processing ROIs"):
            statistics[ROI] = {}
            value_in_mask = self.link_folder_value[ROI]
            matter = "WM" if "WM" in ROI else "GM"
            statitic_folder = {}
            base_folder = os.path.basename(self.path_folder)

            # Statistics for base folder
            for param_name in self.polarimetric_param_names:
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
                os.path.join(self.path_folder_50x50, ROI, f"{base_folder}_selected.png")
            )

            # Statistics for propagated folders
            for folder in self.all_folders:
                mask = propagated_masks[folder] == value_in_mask
                mask_px = np.logical_and(all_pixels_masks[folder], propagated_masks[folder] == value_in_mask)
                statitic_folder = {}
                if np.sum(mask) == 0:
                    for param_name in self.polarimetric_param_names:
                        statitic_folder[param_name] = [math.nan] * 4
                else:
                    valid_points = np.logical_and(all_masks[folder][matter], mask, mask_px)
                    all_sum = np.sum(mask)
                    proportion = np.sum(valid_points) / all_sum
                    if proportion < 0.90 or all_sum < self.pixels_per_ROI * 0.9 if self.instrument == 'IMPV1' else all_sum < self.pixels_per_ROI * 0.01:
                        for param_name in self.polarimetric_param_names:
                            statitic_folder[param_name] = [math.nan] * 4
                    else:
                        for param_name in self.polarimetric_param_names:
                            values_parameter = all_MMs[folder][param_name][valid_points]
                            stats = get_statistics(
                                values_parameter,
                                self.histogram_parameters[param_name],
                                param_name
                            )
                            statitic_folder[param_name] = stats
                statistics[ROI][folder] = statitic_folder
                create_masked_image(
                    all_intensity_images[folder],
                    mask,
                    os.path.join(self.path_folder_50x50, ROI, f"{folder}_selected.png")
                )
            statistics[ROI] = sort_stats_dict(statistics[ROI])

        # Convert statistics to pandas DataFrames and save as Excel
        pandas_stats = create_pandas_stats(statistics)
        for ROI, df in pandas_stats.items():
            df.to_excel(os.path.join(self.path_folder_50x50, ROI, 'combined.xlsx'))
            
    def compare_parameters(self):
        """
        Compare parameters across all ROIs and save combined statistics.
        """
        self.all_ROIs = []
        for base_dir in self.base_dirs:
            if self.instrument == 'IMPV1':
                path_polarimetry_wavelength = os.path.join(base_dir, 'polarimetry', self.param_ROIs["wavelength"])
                self.path_folder_50x50 = os.path.join(path_polarimetry_wavelength, '50x50_images')
            else:
                self.path_folder_50x50 = os.path.join(base_dir, 'RIAP_results')

            roi_files = [
                os.path.join(self.path_folder_50x50, f) for f in os.listdir(self.path_folder_50x50) if not '.png' in f
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
            for parameter in self.polarimetric_param_names:
                all_values[tissue_type][parameter] = []

        for ROI in self.all_ROIs:
            df = pd.read_excel(ROI + '/combined.xlsx', index_col = 0)
            tissue_type = os.path.basename(ROI).split('_')[0]
            for parameter in self.polarimetric_param_names:
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
        print(f" [info] Exporting combined statistics to Excel files in {self.path_output}")
        measurement_per_case = self.param_ROIs['max_number_of_random_squares'] * len(self.base_dirs)

        for parameter in self.polarimetric_param_names:
            df = pd.concat(
                [
                    pad_dataframe_with_nans(self.all_values['GM'][parameter], measurement_per_case),
                    pad_dataframe_with_nans(self.all_values['WM'][parameter], measurement_per_case),
                ],
                axis=1
            )
            df.to_excel(os.path.join(self.path_output, f"{parameter}_prism.xlsx"))

            df = pd.concat(
                [
                    pad_dataframe_with_nans(self.all_values_cv['GM'][parameter], measurement_per_case),
                    pad_dataframe_with_nans(self.all_values_cv['WM'][parameter], measurement_per_case),
                ],
                axis=1
            )
            df.to_excel(os.path.join(self.path_output, f"{parameter}_prism_cv.xlsx"))