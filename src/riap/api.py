from pathlib import Path
import omegaconf
from tqdm import tqdm
from loguru import logger
import sys
from omegaconf import OmegaConf

try:    
    import matlab.engine
except ImportError:
    print(" [warning] MATLAB engine for Python is not installed. Elastix alignment will not work.")

from riap.riap import process
from riap.compare_parameters import run_compare_pipeline
from riap.plotter import plot_parameter_comparison
from riap.config import ProcessingConfig

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
        wavelength: str = None,
        force_recompute: bool = False
    ):
        self.cfg = cfg

        if isinstance(data_path, str) or isinstance(data_path, Path):
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

        if isinstance(output_alignement_folder, str) or isinstance(output_alignement_folder, Path):
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
        if not isinstance(self.cfg.settings.alignment_method, str) or self.cfg.settings.alignment_method not in ['elastix', 'superglue', 'MatchAnything_opencv', 'MatchAnything_imageJ']:
            raise ValueError("alignment_method must be either 'elastix', 'superglue', or 'MatchAnything_opencv'/'MatchAnything_imageJ'.")
        self.alignment_method = self.cfg.settings.alignment_method

        if isinstance(path_output, str) or isinstance(path_output, Path):
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

        if isinstance(force_recompute, bool):
            self.cfg.settings.force_recompute = force_recompute
            logger.info(f"Force recompute set to: {self.cfg.settings.force_recompute}")
        if not isinstance(force_recompute, bool):
            raise TypeError("force_recompute must be a boolean.")
        self.force_recompute = self.cfg.settings.force_recompute
        
        logger.info("Input parameters validated successfully")
        logger.info("Riap instance initiated successfully\n")
        
        # Load configuration and setup folders/masks
        self.__load_parameters()
        self.__create_alignment_folder()
        logger.info(f"Alignment folders will be available in: {self.cfg.paths.output_alignement_folder}")
        
        self.__get_the_base_dirs()
        logger.info(f"Base directories identified: {[str(dir) for dir in self.base_dirs]}")
        
        if str(cfg.paths.match_anything_path) not in sys.path:
            sys.path.append(str(cfg.paths.match_anything_path))
        
        # self.__create_the_masks()
        # logger.info("Tissue masks generated successfully")
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
            
    def align_and_propagate(self):
        config = ProcessingConfig(
            cfg=self.cfg,
            base_dirs=self.base_dirs,
            data_path=self.data_path,
            path_to_align=self.path_to_align,
            path_aligned=self.path_aligned,
            instrument=self.instrument,
            time_base=self.time_base,
            tissue_types=self.tissue_types,
            param_ROIs=self.param_ROIs,
            alignment_method=self.alignment_method,
            force_recompute=self.force_recompute,
            histogram_parameters=self.histogram_parameters,
            pixels_per_ROI=self.pixels_per_ROI
        )
        process(config)
            
    def compare_parameters(self):
        """
        Compare parameters across all ROIs and save combined statistics.
        """
        output_path = self.cfg.paths.output_path / self.alignment_method
        output_path.mkdir(parents=True, exist_ok=True)
        run_compare_pipeline(self.cfg, self.base_dirs, output_path, self.param_ROIs)
        
    def plot_results(self):
        """
        Plot the results of the parameter comparison.
        """
        output_path_xlsx = self.cfg.paths.output_path / self.alignment_method
        output_path_plots = self.cfg.paths.output_path / self.alignment_method / "plots"
        output_path_plots.mkdir(parents=True, exist_ok=True)

        for file in output_path_xlsx.iterdir():
            if file.suffix == ".xlsx":
                plot_parameter_comparison(output_path_xlsx, output_path_plots, self.cfg.time_points, file.name)