path_alignment_batch = cell2mat(importdata('../temp/path_alignment_batch.txt'));
FixPattern = cell2mat(importdata('../temp/FixPattern.txt'));
Tag = cell2mat(importdata('../temp/Tag.txt'));
addpath('0_NIfTI_IO') 
affine_path = '../RegistrationParameters/01_Affine_params.txt';
elastic_path = '../RegistrationParameters/02_Elastic_params.txt';

BATCH_registerPolarimetryDataset('Dataset', path_alignment_batch, 'FixPattern', FixPattern, 'P', affine_path, 'P', elastic_path, 'Tag', Tag, ...
    'Inverse', 1, 'PropImg', 1, 'PROPMODE', 2, 'OutputFolder','invReg/')