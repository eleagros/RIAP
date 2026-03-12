# Region-based Image Analysis Platform (RIAP)
by Éléa Gros

The present repository contains the code used to generate the results presented in the manuscript "Brain Tissue Polarimetry Under Simulated Intraoperative Conditions: Effects of Edema and Temperature" [doi: 10.1142/S1793545826500045](https://doi.org/10.1142/S1793545826500045).

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

---

## Software installation

It is recommended to use a Python virtual environment to manage dependencies and avoid conflicts with other projects.

1. **Download the repository:**
    ```sh
    git clone https://github.com/eleagros/riap.git
    cd riap
    ```

2. **Install the required dependencies:**

    ```sh
    bash install.sh
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

### Elastix

Currently, this repository offers two ways of registering images. One is based on [SuperGlue](https://github.com/magicleap/SuperGluePretrainedNetwork), the other on Elastix [elastix](https://elastix.dev/).

To use the version based on elastix, you will need to install MATLAB Engine API for Python, following instructions available on [https://www.mathworks.com/help/matlab/matlab_external/install-the-matlab-engine-for-python.html](https://www.mathworks.com/help/matlab/matlab_external/install-the-matlab-engine-for-python.html).

After having successfully installed, you should download elastix binaries [here](https://elastix.dev/download.php), and place them in a subfolder `third_party/elastix/elastix-5.2.0-linux` (replace linux by your OS, if not linux).

If you are a Windows user (sorry for you), you will need to modify the paths present in `third_party/elastix/RegistrationElastix/RegistrationScripts/configFilePaths.cfg` to match with your local installation.

And... you should be good to go!

### MatchAnything

The repositories support the use of MatchAnything for feature matching, although the custom functions used as a wrapper for the software are not made available at the moment.

### Additional requirement: Fiji

To use the image alignment and processing features, you need to download [Fiji](https://imagej.net/software/fiji/downloads) (a distribution of ImageJ).  
After downloading, **extract the `Fiji.app` folder and place it inside the `third_party/` directory** of this repository:

```
third_party/Fiji.app/
```

This ensures all Fiji/ImageJ-based scripts will work correctly.


NB: This repository has been tested for MATLAB R2025b, python 3.9, elastix 5.2.0, and ImageJ 2.16.0.

---


## Data

An example set of measurements can be downloaded from
[Download here](https://drive.usercontent.google.com/download?id=1LboN453l3KMtwRyoRMZcH1emT_0calYI&export=download&authuser=1&confirm=t&uuid=3de9bc63-bd9d-45ea-965a-ba9f4dad182c&at=APcXIO1Pw5GxrMZR06Vytsh7lZdB:1770690395492).

After downloading, place the file `measurements.zip` in the `riap/data/IMPv1/measurements/` folder and unzip it there.  

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

---

## Citation
If you use this code or data, please cite the associated manuscript:

    Gros et al., "Brain Tissue Polarimetry Under Simulated Intraoperative Conditions: Effects of Edema and Temperature", Journal of Innovative Optical Health Sciences, 2026 (doi.org/10.1142/S1793545826500045).

---

## Acknowledgments

Many thanks to Stefano Moriconi [https://github.com/stefanomoriconi](https://github.com/stefanomoriconi) for his help in the development of this tool.

