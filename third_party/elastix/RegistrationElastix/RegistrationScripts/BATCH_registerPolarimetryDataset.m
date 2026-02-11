function BATCH_registerPolarimetryDataset(varargin)%

OPTs = getInputs(varargin);

% Check Help FLAG
if OPTs.helpFlag
    fprintf(OPTs.helpMsg); % Display help and stop execution
    return;
end

if OPTs.proceedBatch
    if OPTs.diaryFlag
        diary(OPTs.diaryFileName);
    end
    
    displayInputs(OPTs);
    
    if ~OPTs.propagateIMGFlag
        Dataset = initialiseDataset(OPTs.DatasetFolderPath,...
                                    OPTs.FixPattern,...
                                    OPTs.outputFolderName,...
                                    []);
    else
        Dataset = initialiseDataset(OPTs.DatasetFolderPath,...
                                    OPTs.FixPattern,...
                                    OPTs.outputFolderName,...
                                    OPTs.propagateIMGFolderPattern);
    end
    
    processDataset(Dataset,...
                   OPTs.paramFileName,...
                   OPTs.Tag,...
                   OPTs.verboseFlag,...
                   OPTs.inverseFlag,...
                   OPTs.propagateIMGmode);
    
    disp(' ');
    disp(' *** BATCH: Processing COMPLETED');
    disp(' ');
    
    if OPTs.diaryFlag
        diary('off');
    end
    
else
    disp(' <!> Missing or Inconsistent Inputs! -- Abort.');
end

function OPTs = getInputs(Inputs)

OPTs = chkHelp(Inputs);
if OPTs.helpFlag
    return; % skip the rest of OPTs configuration
end

OPTs = configTagsFilePaths(OPTs,getConfigTagsFilePaths);

OPTs.DatasetFolderPath = []; % Input DATASET FolderPath
OPTs.FixPattern = []; % Input FIXED PATTERN string
OPTs.paramFileName = {}; % Registration Parameters (ELASTIX)
OPTs.Tag = 'MISSING-TAG'; % e.g. Rigid, Affine, Elastic (as string tag)
OPTs.outputFolderName = 'Registration/';

OPTs.inverseFlag = false; % swap Mapping between FIXED and MOVING
OPTs.propagateIMGFlag = false;
OPTs.propagateIMGFolderPattern = 'mask/';
OPTs.propagateIMGmode = 1; % 0 = bool , (1 = float) , 2 = integer
OPTs.verboseFlag = false;
OPTs.diaryFlag = true;
OPTs.proceedBatch = false;

if ~isempty(Inputs)
    for jj = 1 : 2 : length(Inputs)
        switch upper(Inputs{jj})
            case 'DATASET'
                OPTs.DatasetFolderPath = chkFolder(char(Inputs{jj+1}));
            case 'FIXPATTERN'
                OPTs.FixPattern = chkPattern(char(Inputs{jj+1}));
            case 'P'
                if isempty(OPTs.paramFileName)
                    OPTs.paramFileName = Inputs(jj+1);
                else
                    OPTs.paramFileName = cat(1,OPTs.paramFileName,...
                                               Inputs(jj+1));
                end
            case 'TAG'
                OPTs.Tag = Inputs{jj+1};
            case 'INVERSE'
                OPTs.inverseFlag = getNumericArg(Inputs{jj+1},'BOOL','SCALAR');
            case 'PROPIMG'
                OPTs.propagateIMGFlag = getNumericArg(Inputs{jj+1},'BOOL','SCALAR');
            case 'PROPIMGFOLDERPATTERN'
                OPTs.propagateIMGFolderPattern = chkFolder(char(Inputs{jj+1}));
            case 'PROPMODE'
                OPTs.propagateIMGmode = getNumericArg(Inputs{jj+1},'ABS','ROUND','SCALAR');
            case 'VERBOSE'
                OPTs.verboseFlag = getNumericArg(Inputs{jj+1},'BOOL','SCALAR');
            case 'DIARY'
                OPTs.diaryFlag = getNumericArg(Inputs{jj+1},'BOOL','SCALAR');
            case 'OUTPUTFOLDER'
                OPTs.outputFolderName = chkFolder(char(Inputs{jj+1}));
            otherwise
                disp([' * BATCH_registerPolarimetry -- Unrecognised Parsed Parameter: ',...
                      Inputs{jj},' -- Default Applied.']);
        end
    end
end
% Loading Input DATASET FolderPath (manual GUI prompt)
if isempty(OPTs.DatasetFolderPath)
    disp(' >>> [Prompt] Select Input DATASET Folder containing the Polarimetric Acquisitions: ...');
    OPTs.DatasetFolderPath = uigetdir(pwd,'Select Input DATASET Folder containing the Polarymetric Acquisitions');
    OPTs.DatasetFolderPath = chkFolder(char(OPTs.DatasetFolderPath));
end
if isempty(OPTs.FixPattern)
    answer = inputdlg('Enter FIXED PATTERN string (e.g. _P-T0_FX_):','Image Filename Matching Pattern');
    if ~isempty(answer)
        OPTs.FixPattern = chkPattern(char(answer{1}));
    end
end
% Loading Input Registration PARAMETERS (manual GUI prompt)
if isempty(OPTs.paramFileName)
    disp(' >>> [Prompt] Select Input Registration PARAMETERS File: ...');
    [PAR_FileName,...
     PAR_FilePath,...
     PAR_FilterIndex] = uigetfile('*.txt*','Select Input Registration PARAMETERS File',...
                                  'MultiSelect','on');
    if PAR_FilterIndex
        if iscell(PAR_FileName)
            for pp = 1 : length(PAR_FileName)
                OPTs.paramFileName{pp,1} = strcat(PAR_FilePath,...
                                                  PAR_FileName{pp});
            end
        else
            OPTs.paramFileName = {strcat(PAR_FilePath,PAR_FileName)};
        end
    end
end
% Assert Correct Necessary Inputs
if ~isempty(OPTs.DatasetFolderPath) && exist(OPTs.DatasetFolderPath,'file') &&...
   ~isempty(OPTs.FixPattern) && ~strcmp(OPTs.FixPattern,'') && ...
   ~isempty(OPTs.paramFileName)
    OPTs.proceedBatch = true;
    OPTs.diaryFileName = [OPTs.DatasetFolderPath,'BATCH_Reg2DPolarimDataset_',...
                      char(datetime('now','Format','yyyyMMdd_HHmmss')),'.txt'];
    
end

function strOUT = chkPattern(strIN)
% Remove any '*' from the input string
strOUT = strrep(strIN,'*','');

function folderOUT = chkFolder(folderIN)
if ~isempty(folderIN)
    if ~strcmp(folderIN(end),'/')
        folderOUT = [folderIN,'/'];
    else
        folderOUT = folderIN;
    end
end

function OPTs = chkHelp(Inputs)
OPTs.helpFlag = false;
OPTs.helpMsg = makeHelpMsg;
for jj = 1 : length(Inputs)
    if~iscell(Inputs{jj})
        if strcmpi(Inputs{jj},'HELP') || strcmpi(Inputs{jj},'-HELP') || ...
                strcmpi(Inputs{jj},'--HELP') || strcmpi(Inputs{jj},'- HELP') || ...
                strcmpi(Inputs{jj},'-- HELP') || strcmpi(Inputs{jj},'H') ||...
                strcmpi(Inputs{jj},'-H') || strcmpi(Inputs{jj},'--H') || ...
                strcmpi(Inputs{jj},'- H') || strcmpi(Inputs{jj},'-- H')
            OPTs.helpFlag = true;
            return;
        end
    end
end

function msgHelp = makeHelpMsg()
msgHelp = cat(2,...
'\n * HELP: BATCH_registerPolarimetryDataset\n',...
'\n',...
' Use this function to perform a BATCH pairwise registration over a Dataset\n',...
' of multiple acquisitions of 2D Polarimetry Scans.\n',...
'\n',...
' This SW builds on a wrapper for Elastix registration.\n',...
'\n',...
' * Configuration *\n',...
' This function requires: \n',...
'\t Elastix (latest version) correctly compiled or installed and configured\n',...
'\t -> See configPath.cfg\n',...
'\t NB: This SW requires also the NIFTI I/O library [only for Matlab code]\n',...
'\n',...
' Inputs:\n',...
'\n',...
'\t ''Dataset'': Folder path string containing the acquisitions (i.e. each\n',...
'\t            sub-folder is an independent set of images).\n',...
'\t ''FixPattern'': Unique string pattern identifying the FIXED scan in each set of\n',...
'\t               images. E.g. all images containing ''_P-T0_FX_'' in the\n',...
'\t               file name will be treated as FIXED, whereas the remaining\n',...
'\t               ones will be regarded as MOVING images to be aligned.\n',...
'\t ''P'': Filepath string of the PARAMETERS File for the Registration (*.txt)\n',...
'\t [''Tag'']: User-identifier string for registration type - e.g. ''Rigid''\n',...
'\t          (default: ''MISSING-TAG'') - it is *recommended* to use a Tag for\n',...
'\t          multiple different registrations of the same Dataset to\n',...
'\t          *avoid undesired overwriting* of results.\n',...
'\t [''OutputFolder'']: Local folder string with custom path (default: ''Registration/'')\n',...
'\t [''Inverse'']: Scalar Boolean for inverse MAPPING [swap FIXED with MOVING] (default: 0)\n',...\n',...
'\t [''PropImg'']: Scalar Boolean for enabling automatic propagation of another \n',...
'\t              image [in the MOVING space], e.g. a ROI mask (*.png)\n',...
'\t [''PropImgFolderPattern'']: Unique SUB-folder pattern identifying the\n',...
'\t                           directory in each set, containing the image to \n',...
'\t                           propagate, e.g. a mask. (default: ''mask/'')\n',...
'\t [''PropBinary'']: Scalar Boolean for considering the propagating image\n',...
'\t                 as Binary [interpolation is affected] (default: 0)\n',...
'\t [''Verbose'']: Scalar Boolean for verbose output (default: 0)\n',...
'\t [''Diary'']: Scalar Boolean for BATCH log exported in Dataset (default: 1)\n',...
'\n',...
'\t NB: a GUI will be prompted when the mandatory arguments are not parsed.\n',...
'\t     Optional Inputs will not be prompted with a GUI.\n',...
'\n',...
' Automatic Outputs (within the OUTPUT Folder):\n',...
'\n',...
' For each folder in ''Dataset'' (i.e. for each acquisition set) a new\n',...
' directory will be created, as specified in [''OutputFolder'']',...
'\n',...
' e.g. /myDatasetPath/Acquisition01/Registration/ ',...
'\n',...
' the [''OutputFolder''] folder will contain the following files, as generated by\n',...
' the function MAIN_registerPolarimetry (see help for more information).\n',...
'\n',...
'\t MOVINGfilename_<TAG>_elastix.log: Log file of the Registration (Elastix) \n',...
'\t MOVINGfilename_<TAG>_TransformParameters_*.txt: Estimated Transformation Parameter Files\n',...
'\t MOVINGfilename_<TAG>_TransformParameters_*.png: Aligned and Warped MOVING Scan after Registration\n',...
'\n',...
'\n',...
' Function Call:\n',...
'\n',...
'\t BATCH_registerPolarimetry(''Dataset'',''~/myDatasetPath/'',''FixPattern'',''my_FIX_Pattern'',''P'',''~/myPath/RegParameters.txt'');\n',...
'\n',...
' e.g.: call with a BINARY IMAGE (MASK) to PROPAGATE:\n',...
'\t NB: the MASK is in the *FIXED* space -> INVERSE is set to: true\n',...
'\t     the MASK (*.png) is assumed in ''mask/'' directory\n',...
'\t     the OutputFolder is changed to ''invReg/'' directory\n',...
'\t     a GUI will be prompted for the missing mandatory arguments.\n',...
'\n',...
'\t BATCH_registerPolarimetryDataset(''Inverse'',1,''OutputFolder'',''invReg/'',''PropImg'',1,''PropBinary'',1);\n',...
'\n',...
' Version: 1.0 - June 2022\n',... % Same Everywhere
' Developed by: Stefano Moriconi -- stefano.nicola.moriconi@gmail.com\n',... % Same Everywhere
'\n',...
' See also:\n',...
'\t MAIN_registerPolarimetry(''HELP'');\n',...
'\t https://elastix.lumc.nl/\n',...
'\n');

function outArg = getNumericArg(inArg,varargin)
if ~isnumeric(inArg)
    if strcmpi(inArg,'TRUE')
        outArg = true;
    elseif strcmpi(inArg,'FALSE')
        outArg = false;
    else
        outArg = str2double(inArg);
    end
else
    if ~isfinite(inArg)
        outArg = [];
    else
        outArg = inArg;
    end
end
if ~isempty(varargin) && ~isempty(outArg)
    for jj = 1 : length(varargin)
        switch upper(varargin{jj})
            case 'BOOL'
                outArg = logical(outArg);
            case 'ABS'
                outArg = abs(outArg);
            case 'ROUND'
                outArg = round(outArg);
            case 'SCALAR'
                outArg = outArg(1);
            otherwise
                disp(' <!> Unrecognised Argument Flag! - Possible (?) Unexpected Behaviours');
        end
    end
end

function TagsFilePaths = getConfigTagsFilePaths()
FilePathsCFG = dir('*.cfg'); % local directory of the main SW
if ~isempty(FilePathsCFG)    
    % consider the first file (if multiple)
    TagsFilePaths = readTagsFilePaths(strcat(FilePathsCFG(1).folder,'/',...
                                             FilePathsCFG(1).name));
else
    TagsFilePaths = [];
    disp(' <!> configFilePaths.cfg NOT Found! -- [wrn] Possible Unexpected Behaviours');
end

function OPTs = configTagsFilePaths(OPTs,TagsFilePaths)
if ~isempty(TagsFilePaths)
    %% External LIBRARIES Dependencies
    if any(contains({TagsFilePaths(:).Tag},'LIB'))
        % LIBS: set the environment
        LIBidx = find(contains({TagsFilePaths(:).Tag},'LIB'));
        plsPATHs = '';
        delimUNIX = ':';
        delimPCWIN = ';';
        for ii = 1 : length(LIBidx)
            if ~strcmp(TagsFilePaths(LIBidx(ii)).FilePath,'')
                plsPATHs = cat(2,plsPATHs,TagsFilePaths(LIBidx(ii)).FilePath);
                if ii < length(LIBidx)
                    if strcmp(computer,'')
                        plsPATHs = cat(2,plsPATHs,delimPCWIN);
                    else
                        plsPATHs = cat(2,plsPATHs,delimUNIX);
                    end
                end
            end
        end
        OPTs = setfield(OPTs,'LD_LIBRARY_PATH', plsPATHs);%#ok
        % Add the provided libraries to the shared libraries
        switch computer
            case 'GLNXA64'
                setenv('LD_LIBRARY_PATH',[plsPATHs,delimUNIX,getenv('LD_LIBRARY_PATH')]);
            case 'MACI64'
                setenv('DYLD_LIBRARY_PATH',[plsPATHs,delimUNIX,getenv('DYLD_LIBRARY_PATH')]);
            case 'PCWIN64'
                setenv('PATH',[plsPATHs,delimPCWIN,getenv('PATH')]);
            otherwise
                disp(' <!> Unknown Computer Architecture: ADDING SHARED LIBRARY PATH: Failed!');
        end
    end
    %% External Executables
    if any(contains({TagsFilePaths(:).Tag},'EXE'))
        EXEidx = find(contains({TagsFilePaths(:).Tag},'EXE'));
        for ii = 1 : length(EXEidx)
            OPTs = setfield( OPTs,...
                             TagsFilePaths(EXEidx(ii)).Tag ,...
                             TagsFilePaths(EXEidx(ii)).FilePath ); %#ok<SFLD>
        end
    end
    %% External Workspace Variables
    if any(contains({TagsFilePaths(:).Tag},'MAT'))
        MATidx = find(contains({TagsFilePaths(:).Tag},'MAT'));
        for ii = 1 : length(MATidx)
            OPTs = setfield( OPTs,...
                             TagsFilePaths(MATidx(ii)).Tag ,...
                             TagsFilePaths(MATidx(ii)).FilePath ); %#ok<SFLD>
        end
    end
end

function TagsFilePaths = readTagsFilePaths(filename, dataLines)
%% Input handling
% If dataLines is not specified, define defaults
if nargin < 2
    dataLines = [1, Inf];
end
%% Set up the Import Options and import the data
opts = delimitedTextImportOptions("NumVariables", 1);

% Specify range and delimiter
opts.DataLines = dataLines;
opts.Delimiter = "";

% Specify column names and types
opts.VariableNames = "Rows";
opts.VariableTypes = "string";

% Specify file level properties
opts.ExtraColumnsRule = "ignore";
opts.EmptyLineRule = "read";

% Specify variable properties
opts = setvaropts(opts, "Rows", "WhitespaceRule", "preserve");
opts = setvaropts(opts, "Rows", "EmptyFieldRule", "auto");

% Import the data
tbl = readtable(filename, opts);

%% Convert to output type
TagsFilePaths = [];
strTagsFilePaths = tbl.Rows;
ss = 0;
while ss < size(strTagsFilePaths,1)
    ss = ss + 1;
    strTag = char(strTagsFilePaths(ss));
    if strcmp(strTag(1),'#')
        if isempty(TagsFilePaths) 
            % Put first entry
            TagsFilePaths = struct('Tag',[],'FilePath',[]);
            TagsFilePaths.Tag = strTag(2:end); % remove the '#' character
            if ss+1 <= size(strTagsFilePaths,1)
                strTag = char(strTagsFilePaths(ss+1));
                if ~strcmp(strTag(1),'%') && ...
                   ~strcmp(strTag(1),'#')
                    TagsFilePaths.FilePath = strTag; % filepath in subsequent line
                else
                    % Invalid FilePath (either a Comment or another Tag
                    TagsFilePaths.FilePath = '';
                    ss = ss - 1; % Compensate for command on ll. 89
                end
            else
                TagsFilePaths.FilePath = '';
            end
        else
            % Append other entries
            TagsFilePaths(end+1).Tag = strTag(2:end); %#ok<AGROW> % remove the '#' character
            if ss+1 <= size(strTagsFilePaths,1)
                strTag = char(strTagsFilePaths(ss+1));
                if ~strcmp(strTag(1),'%') && ...
                   ~strcmp(strTag(1),'#')
                    TagsFilePaths(end).FilePath = strTag; % filepath in subsequent line
                else
                    % Invalid FilePath (either a Comment or another Tag
                    TagsFilePaths(end).FilePath = '';
                    ss = ss - 1; % Compensate for command on ll. 89
                end
            else
                TagsFilePaths(end).FilePath = '';
            end
        end
        ss = ss + 1; % Increment counter considering also follwing line
    end
end

function Dataset = initialiseDataset(DatasetFolderPath,FIXpattern,outputFolderName,propIMGFolderPattern)
% Include here MASK Propagation options! WIP
Dataset = [];
if exist(DatasetFolderPath,'file')
    SETs = dir(DatasetFolderPath); % List contents of DatasetFolderPath
    if ~isempty(SETs)
        for ii = 1 : length(SETs)
            if SETs(ii).isdir && ~strcmpi(SETs(ii).name(1),'.')
                directoryFileName = strcat(SETs(ii).folder,'/',SETs(ii).name,'/');
                
                [Data,validFlag] = genDataSet(directoryFileName,...
                                              FIXpattern,...
                                              outputFolderName,...
                                              propIMGFolderPattern);
                if validFlag
                    if isempty(Dataset)
                        Dataset = Data;
                    else
                        Dataset = cat(2,Dataset,Data);
                    end
                end
            end
        end
    end
else
    disp(' <!> Parsed Dataset Folder Path does not exist!');
end

function [Data,validFlag] = genDataSet(directoryFileName,FIXpattern,outputFolderName,propIMGFolderPattern)
Data = getVoidData;
validFlag = false;

FIXEDfoundFlag = false;
PNGs = dir([directoryFileName,'*.png']);

% Assignment of the Directory
Data.directory.FileName = directoryFileName;
Data.output.FileName = strcat(directoryFileName,outputFolderName);

if ~isempty(PNGs)
    for ii = 1 : length(PNGs)
        if ~FIXEDfoundFlag % FIXED not yet found
            if isempty(strfind(PNGs(ii).name,FIXpattern))
                if isempty(Data.moving(1).FileName)
                    Data.moving(1).FileName = strcat(PNGs(ii).folder,'/',PNGs(ii).name);
                else
                    Data.moving(end+1).FileName = strcat(PNGs(ii).folder,'/',PNGs(ii).name);
                end
            else
                Data.fixed.FileName = strcat(PNGs(ii).folder,'/',PNGs(ii).name);
                FIXEDfoundFlag = true;
            end
        else % set all the remaining images to moving (the FIXED has been already found)
            if isempty(Data.moving(1).FileName)
                Data.moving(1).FileName = strcat(PNGs(ii).folder,'/',PNGs(ii).name);
            else
                Data.moving(end+1).FileName = strcat(PNGs(ii).folder,'/',PNGs(ii).name);
            end
        end
    end
end

% Image to propagate
if ~isempty(propIMGFolderPattern)
    disp(directoryFileName);
    propPNGs = dir([directoryFileName,propIMGFolderPattern,'*.png']);
    if ~isempty(propPNGs)
        for ii = 1 : length(propPNGs)
            if isempty(Data.propagate(1).FileName)
                Data.propagate(1).FileName = strcat( propPNGs(ii).folder,'/',...
                                                     propPNGs(ii).name );
            else
                Data.propagate(end+1).FileName = strcat( propPNGs(ii).folder,'/',...
                                                         propPNGs(ii).name );
            end
        end
    end
end

if ~FIXEDfoundFlag
    disp(' ');
    disp([' <!> Set: ',directoryFileName]);
    disp([' <!> FIXED image NOT FOUND using PATTERN: ',FIXpattern,' - Skipping!']);
    disp(' ');
end

if ~isempty(Data.fixed.FileName) && ...
   length(Data.moving)>=1 && ~isempty(Data.moving(1).FileName) && ...
   FIXEDfoundFlag
    
    validFlag = true;
    if ~exist(Data.output.FileName,'file')
        mkdir(Data.output.FileName);
    end
end

function Data = getVoidData()
Data.directory.FileName = [];
Data.fixed.FileName = [];
Data.moving.FileName = [];
Data.output.FileName = [];
Data.propagate.FileName = [];

function processDataset(Dataset,paramFileName,Tag,verboseFlag,inverseFlag,propMode)
for ii = 1 : length(Dataset)
    disp([' *** Processing Set (',...
          num2str(ii,'%d'),'/',num2str(length(Dataset),'%d'),')']);
    disp([' * Set: ',Dataset(ii).directory.FileName]);
    disp(' ');

    for jj = 1 : length(Dataset(ii).moving)
        disp([' * Registration (',...
              num2str(jj,'%d'),'/',num2str(length(Dataset(ii).moving),'%d'),...
              ') ------------------------------']);
        if isempty(Dataset(ii).propagate(1).FileName)
            % No other Image to Propagate

            MAIN_registerPolarimetry('F',Dataset(ii).fixed.FileName,...
                                     'M',Dataset(ii).moving(jj).FileName,...
                                     'P',paramFileName,...
                                     'O',Dataset(ii).output.FileName,...
                                     'TAG',Tag,...
                                     'VERBOSE',verboseFlag,...
                                     'EMBED',1,...
                                     'INVERSE',inverseFlag);
        else % Extra Image to propagate after Registration (e.g. mask)
            MAIN_registerPolarimetry('F',Dataset(ii).fixed.FileName,...
                                     'M',Dataset(ii).moving(jj).FileName,...
                                     'P',paramFileName,...
                                     'O',Dataset(ii).output.FileName,...
                                     'TAG',Tag,...
                                     'VERBOSE',verboseFlag,...
                                     'EMBED',1,...
                                     'INVERSE',inverseFlag,...
                                     'PROPIMG',Dataset(ii).propagate,... MULTIPLE IMAGEs or MASKs ALLOWED
                                     'PROPMODE',propMode);
        end
    end
end

function displayInputs(OPTs)
disp(' ');
disp(' *** BATCH: Pairwise Alignment for 2D Polarimetry Scans Dataset ***');
disp([' ',datestr(datetime),' @ ', computer]);
disp(' ');
disp([' >> INPUT DATASET FOLDER: ',OPTs.DatasetFolderPath]);
disp([' >> PARSED FIXED PATTERN: ',OPTs.FixPattern]);
if OPTs.inverseFlag
    disp(' >> INVERSE MAPPING: Enabled');
end
if OPTs.propagateIMGFlag
    disp(' * PROPAGATE IMG: Enabled');
    disp([' * PROPAGATE IMG FOLDER PATTERN: ~/',OPTs.propagateIMGFolderPattern]);
    if OPTs.propagateIMGmode == 0
        disp(' * PROPAGATE IMG(s) as: BINARY (logical masks)');
    elseif OPTs.propagateIMGmode == 1
        disp(' * PROPAGATE IMG(s) as: FLOAT (grayscale intensities)');
    else % OPTs.propagateIMGmode == 2
        disp(' * PROPAGATE IMG(s) as: INTEGERS (annotation labels)');
    end
end
disp(' ');