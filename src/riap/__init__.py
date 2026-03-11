"""RIAP package public interface."""

__version__ = "1.0.0"
__author__ = "Éléa Gros"
__email__ = "elearomy.gros@unibe.ch"

__all__ = [
	"Riap",
	"load_config",
	"get_default_config_path",
	"ProcessingConfig",
	"plot_parameter_comparison",
]


def __getattr__(name):
	if name in {"Riap", "load_config", "get_default_config_path"}:
		from riap.api import Riap, load_config, get_default_config_path

		mapping = {
			"Riap": Riap,
			"load_config": load_config,
			"get_default_config_path": get_default_config_path,
		}
		return mapping[name]

	if name == "ProcessingConfig":
		from riap.config import ProcessingConfig

		return ProcessingConfig

	if name == "plot_parameter_comparison":
		from riap.visualization import plot_parameter_comparison

		return plot_parameter_comparison

	raise AttributeError(f"module 'riap' has no attribute '{name}'")
