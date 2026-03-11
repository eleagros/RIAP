"""Typed configuration objects used by the RIAP processing pipeline."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Any

@dataclass
class ProcessingConfig:
    """Configuration for RIAP processing pipeline."""
    
    # Core configuration
    cfg: Any  # Your existing config object
    
    # Paths
    base_dirs: List[Path]
    data_path: Path
    path_to_align: Path
    path_aligned: Path
    
    # Instrument settings
    instrument: str  # 'IMPV1' or other
    time_base: str
    
    # Tissue analysis
    tissue_types: List[str] = field(default_factory=lambda: ['WM', 'GM'])
    
    # ROI parameters
    param_ROIs: Dict[str, Any] = field(default_factory=dict)
    # Example: {'number_of_random_squares': 10, 'square_size': 50}
    
    # Alignment settings
    alignment_method: str = 'MatchAnything'  # 'elastix', 'superglue', or 'MatchAnything'
    force_recompute: bool = False
    
    # Statistics parameters
    histogram_parameters: Dict[str, Any] = field(default_factory=dict)
    pixels_per_ROI: int = 2500
    
    def validate(self):
        """Validate configuration parameters."""
        if self.alignment_method not in ['elastix', 'superglue', 'MatchAnything_opencv', 'MatchAnything_imageJ']:
            raise ValueError(f"Unsupported alignment method: {self.alignment_method}")
        
        if self.instrument not in ['IMPV1', 'IMPV2']:
            raise ValueError(f"Unsupported instrument: {self.instrument}")
        
        for path in [self.data_path, self.path_to_align, self.path_aligned]:
            if not isinstance(path, Path):
                raise TypeError(f"Path must be pathlib.Path, got {type(path)}")
        
        return True
