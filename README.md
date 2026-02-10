# Region-based Image Analysis Platform (RIAP)
by
Éléa Gros

The present repository contains the code used to generate the results presented in the manuscript "Brain Tissue Polarimetry Under Simulated Intraoperative Conditions: Effects of Edema and Temperature" [doi: TBD](doi.org/TBD).

The study aimed to quantify the effect of simulated edema on the polarimetric parameters of brain tissue. 

## Abstract

In neurosurgical oncology, maximizing tumor resection while preserving neurological function remains a critical challenge, particularly in glioma surgery where tumor borders are difficult to distinguish intraoperatively.
Polarimetry-based imaging has emerged as a promising technique for visualizing white matter fiber tracts and differentiating healthy from neoplastic brain tissue.
This study evaluates whether brain edema and temperature variations influence polarimetric parameters, potentially introducing noise and complicating intraoperative imaging. 
To model edema, fresh ex vivo calf brain samples were immersed in distilled water.
Polarimetric parameters including depolarization, linear retardance, and the azimuth of the optical axis, were measured at multiple time points over three hours and a half using a wide-field imaging Mueller polarimetric setup.
Results show that water absorption affects all polarimetric parameters and complicates fiber tract visualization. We also investigated whether temperature changes influenced polarimetric markers, but found no significant effect.
These findings demonstrate that brain edema might alter polarimetric markers and act as a confounding factor in intraoperative
imaging, potentially affecting tumor border visualization.
The in vivo impact of brain edema remains unclear, and further studies are needed to refine polarimetric imaging for surgical guidance in glioma resection.


## Software installation

It is recommended to use a Python virtual environment to manage dependencies and avoid conflicts with other projects.

1. **Download the repository:**
    ```sh
    git clone https://github.com/eleagros/riap.git
    cd riap
    ```

2. **Create a virtual environment (replace `venv` with your preferred name):**

    ```sh
    python3 -m venv venv
    ```

3. **Activate the virtual environment:**

    - On Linux/macOS:
        ```sh
        source venv/bin/activate
        ```
    - On Windows:
        ```sh
        venv\Scripts\activate
        ```

4. **Install PyTorch (to ensure cuda compatibility):**

    Follow the instructions for your system and CUDA version at [https://pytorch.org/get-started/locally/](https://pytorch.org/get-started/locally/).  
    For example, for Linux with pip and CUDA 12.6 (tested):

    ```sh
    pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu126
    ```

5. **Install the required dependencies:**

    ```sh
    pip install -e .
    ```
    NB: -e is not strictly required, but allows to modify the source code of this repository directly without needing to reinstall RIAP,

## Third-party dependencies and licensing

Some third-party code is provided in `third_party/` is under different licenses (MIT, Apache 2.0, or academic/non-commercial).

**Important notice: SuperGlue** (by Magic Leap, Inc.) is under a restrictive academic/non-commercial license.  

### How to obtain and use SuperGlue

1. **Download the original SuperGlue code**  
   Get a clean, unmodified copy from the official repository: [https://github.com/magicleap/SuperGluePretrainedNetwork](https://github.com/magicleap/SuperGluePretrainedNetwork). Rename the folder that you extract to superglue and place it in the `third_party/` folder:  
   

2. **Apply the patch provided**  
   If this repository provides a patch file (e.g., `superglue.patch`), save it in the root directory of the original SuperGlue code and run:

   ```sh
   patch third_party/superglue/demo_superglue.py < third_party/demo_superglue.patch
   ```
    **Windows users:** You can use the `patch` command by installing [Git Bash](https://gitforwindows.org/), which provides a Unix-like terminal and tools.

**Note:**  
- Only the patch file and instructions are provided here, not the SuperGlue code itself.
- This approach respects the license and allows reproducibility.

---


## Data

An example set of measurements can be downloaded from
[Download here](https://drive.usercontent.google.com/download?id=1LboN453l3KMtwRyoRMZcH1emT_0calYI&export=download&authuser=1&confirm=t&uuid=3de9bc63-bd9d-45ea-965a-ba9f4dad182c&at=APcXIO1Pw5GxrMZR06Vytsh7lZdB:1770690395492).

After downloading, place the file `measurements.zip` in the `riap/data/measurements/` folder and unzip it there.  

---

## Running the notebooks

All notebooks are in the `notebooks/` folder. Navigate to this folder and launch Jupyter Notebook:

```sh
cd notebooks
jupyter notebook
```

### Notebook purposes
| Notebook | Purpose |
|----------|---------|
| `1. Time-series analysis.ipynb` | Apply time-series analysis to your set of samples |
| `2. Signal recovery video.ipynb` | Create the supplementary video |
| `3. Compare weights.ipynb` | Compare the weights of the measured samples |
| `4. Generate Supp Materials.ipynb` | Create supplementary materials |

---


## License
All source code is made available under a BSD license. See `LICENSE` for the full license text.

## Citation
If you use this code or data, please cite the associated manuscript "Brain Tissue Polarimetry Under Simulated Intraoperative Conditions: Effects of Edema and Temperature" [doi: TBD](doi.org/TBD).

## Acknowledgments
Many thanks to Stefano Moriconi [https://github.com/stefanomoriconi](https://github.com/stefanomoriconi) for their help in the development of this tool.