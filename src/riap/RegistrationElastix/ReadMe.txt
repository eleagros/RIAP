***** HORAO - 2D Polarimetric Image Registration *****

June 2022
 Developed by: Stefano Moriconi -- stefano.nicola.moriconi@gmail.com

*** Insallation

Requirements:
- MATLAB (with 'Image Processing Toolbox')
- Elastix (from: https://elastix.lumc.nl/)

Unzip the main folder containing:

	~/RegistrationScripts
	~/RegistrationParameters
	~/test_Dataset 

Configure the PATHS to the external executables (elastix) in the 'configFilePaths.cfg'


*** Usage

--- Setting-Up ---

1) Launch MATLAB

	~/my_MATLAB_Path/matlab

2) Set as current directory ~/RegistrationScripts 

	>> cd('~/RegistrationScripts');

3) Include the folder ~/RegistrationScripts/0_NIfTI_IO

	>> addpath('~/RegistrationScripts/0_NIfTI_IO');



--- Individual Alignment ---

This function is meant for an individual alignment process.

1) Run the function 'MAIN_registerPolarimetry.m' in ~/RegistrationScripts

	>> MAIN_registerPolarimetry('HELP');

Instruction will be provided for aligning a MOVING image to a FIXED reference one. 
An interactive GUI will be prompted only for *mandatory* inputs.

More Registration infos at: https://elastix.lumc.nl/download/elastix-5.0.1-manual.pdf


--- Batch Alignment ---

This function is meant for automatically processing a dataset of images.

1) Run the function 'BATCH_registerPolarimetryDataset.m' in ~/RegistrationScripts

	>> BATCH_registerPolarimetryDataset('HELP');

Instruction will be provided for aligning a dataset containing several folders, each containing a set of MOVING images to be aligned to a FIXED reference. 

The dataset is assumed having the following folder structure:

	~/myDatasetPath/myAcquisitionFolder01/imgFIXED.png
										 /imgMOVING_01.png
										 /imgMOVING_02.png
										 /...

				   /myAcquisitionFolder02/imgFIXED.png
				   						 /imgMOVING_01.png
				   						 /imgMOVING_02.png
				   						 /...
				   ...	

Optionally other sub-folders can be considered for propagating images or masks of a dataset.
By default, these are assumed to be in:

~/myDatasetPath/myAcquisitionFolder01/mask/mskFIXED.png

			   /myAcquisitionFolder02/mask/mskFIXED.png

			   ...

An interactive GUI will be prompted only for *mandatory* inputs.

