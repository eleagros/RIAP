"""Comparison and Excel export utilities for ROI-derived RIAP parameter summaries."""

import pandas as pd
import os
import copy
from loguru import logger
from openpyxl.utils import get_column_letter

from riap.analysis import subtract_angle, pad_dataframe_with_nans

def run_compare_pipeline(cfg, base_dirs, output_path, param_ROIs):
    all_ROIs = []
    for base_dir in base_dirs:
        path_folder_50x50 = base_dir / cfg.default_paths._50x50_images

        roi_files = [
            f for f in path_folder_50x50.iterdir() if not '.png' in f.name and f.is_dir()
        ]
        all_ROIs += roi_files
        
    all_values = load_all_values(cfg, cfg.settings.tissue_types, all_ROIs, cfg.settings.metric)
    all_values_cv = get_all_values_cv(all_values)
    export_results(cfg, base_dirs, all_values, all_values_cv, output_path, param_ROIs)
    logger.success(f"Comparison of parameters completed and results exported to {output_path}")

def load_all_values(cfg, tissue_types, all_ROIs, metric):
    """
    Load all values from combined Excel files for comparison.
    """
    all_values = {}
    for tissue_type in tissue_types:
        all_values[tissue_type] = {}
        for parameter in cfg.settings.polarimetric_parameters:
            all_values[tissue_type][parameter] = []

    for ROI in all_ROIs:
        df = pd.read_excel(ROI / 'combined.xlsx', index_col = 0)
        tissue_type = os.path.basename(ROI).split('_')[0]

        for parameter in cfg.settings.polarimetric_parameters:
            if parameter == 'azimuth':
                values_and_folder = df[df['parameter'] == parameter][['mean', 'folder']]
            else:
                values_and_folder = df[df['parameter'] == parameter][[metric, 'folder']]

            if cfg.settings.instrument == "IMPV1":
                values_and_folder["folder"] = values_and_folder["folder"].str.split("_").str[-3]
            elif cfg.settings.instrument == "IMPV2":
                values_and_folder["folder"] = values_and_folder["folder"].str.split("_").str[-1]
            else:
                logger.warning(f"Unknown instrument {cfg.settings.instrument}, folder names will not be processed.")
            values_and_folder = values_and_folder.set_index("folder")
            all_values[tissue_type][parameter].append(values_and_folder)

    for tissue, values in all_values.items():
        for param, val in values.items():
            all_values[tissue][param] = pd.concat(val, axis=1)

    return all_values
        
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


def _autosize_columns(ws):
    """
    Auto-adjust Excel column widths based on max content length.
    """
    for column_cells in ws.columns:
        max_length = 0
        column_letter = get_column_letter(column_cells[0].column)

        for cell in column_cells:
            try:
                if cell.value is not None:
                    max_length = max(max_length, len(str(cell.value)))
            except Exception:
                pass

        adjusted_width = max_length + 2
        ws.column_dimensions[column_letter].width = adjusted_width


def export_results(cfg, base_dirs, all_values, all_values_cv, output_path, param_ROIs):
    """
    Export combined statistics and coefficient of variation to Excel files.
    Columns are automatically resized to fit content.
    """
    logger.info(f"Exporting combined statistics to Excel files in {output_path}")
    measurement_per_case = (
        param_ROIs['max_number_of_random_squares'] * len(base_dirs)
    )

    for parameter in cfg.settings.polarimetric_parameters:

        # ---- Statistics ----
        df_stats = pd.concat(
            [
                pad_dataframe_with_nans(
                    all_values['GM'][parameter], measurement_per_case
                ),
                pad_dataframe_with_nans(
                    all_values['WM'][parameter], measurement_per_case
                ),
            ],
            axis=1,
        )

        file_stats = output_path / f"{parameter}_prism.xlsx"

        with pd.ExcelWriter(file_stats, engine="openpyxl") as writer:
            df_stats.to_excel(writer)
            _autosize_columns(writer.sheets['Sheet1'])

        # ---- CV ----
        df_cv = pd.concat(
            [
                pad_dataframe_with_nans(
                    all_values_cv['GM'][parameter], measurement_per_case
                ),
                pad_dataframe_with_nans(
                    all_values_cv['WM'][parameter], measurement_per_case
                ),
            ],
            axis=1,
        )

        file_cv = output_path / f"{parameter}_prism_cv.xlsx"

        with pd.ExcelWriter(file_cv, engine="openpyxl") as writer:
            df_cv.to_excel(writer)
            _autosize_columns(writer.sheets['Sheet1'])