from pathlib import Path
import riap

# 1. using a config gfile
cfg = riap.load_config("IMPv2.yaml")  # current options include "IMPV1.yaml" and "IMPV2.yaml"
alignment_method = "MatchAnything_opencv"  # current options include "elastix", "superglue", "MatchAnything_opencv", "MatchAnything_imageJ"

# 2. overriding specific parameters
base_folder = Path("/home/elea/Documents/HORAO/DATABASES/7_FIXATION_METHODS/measurements")
all_results_paths = {}

for measurement_folder in ["Solution1", "Solution2", "Solution3"]:
    app = riap.Riap(
        cfg,
        data_path = base_folder / measurement_folder,
        calib_path = Path("/home/elea/Documents/HORAO/DATABASES/7_FIXATION_METHODS/calibration"),
        path_output = base_folder / "results" / measurement_folder,
        alignment_method = alignment_method
    )
    # app.align_and_propagate()
    app.compare_parameters()
    app.plot_results()
    all_results_paths[measurement_folder] = base_folder / "results" / measurement_folder / alignment_method

# 3. comparing multiple solutions on the same figure
app.plot_results_multi_solution(solutions_paths=all_results_paths)