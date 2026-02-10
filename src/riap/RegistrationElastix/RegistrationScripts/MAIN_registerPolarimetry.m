function successFlag = MAIN_registerPolarimetry(varargin)

successFlag = false;

OPTs = getInputs(varargin);

% Check Help FLAG
if OPTs.helpFlag
    fprintf(OPTs.helpMsg); % Display help and stop execution
    return;
end

if OPTs.proceedRegistration
    if ~OPTs.embedFlag
        disp(' ');
        disp(' *** Pairwise Alignment for 2D Polarimetry Scans ***');
        disp(' ');
    end
    try
        displayInputs(OPTs);
        tic;
        
        if OPTs.inverseFlag % SWAP between FIXED and MOVING!
            successFlag = API_pairwiseRegistrationElastix(OPTs.EXE_Elastix,...
                                                          OPTs.movingFileName,...
                                                          OPTs.fixedFileName,...    
                                                          OPTs.paramFileName,...
                                                          OPTs.tempOutputFolderPath,...
                                                          'VERBOSE',OPTs.verboseFlag);
        else
            successFlag = API_pairwiseRegistrationElastix(OPTs.EXE_Elastix,...
                                                          OPTs.fixedFileName,...
                                                          OPTs.movingFileName,...
                                                          OPTs.paramFileName,...
                                                          OPTs.tempOutputFolderPath,...
                                                          'VERBOSE',OPTs.verboseFlag);
        end

        if successFlag
            fprintf('\b\b\b\bDONE!\n');
            if ~isempty(OPTs.propagateIMG)
                OPTs.transformParameters = getTransformParameters(OPTs.tempOutputFolderPath,false);
                for pp = 1 : length(OPTs.propagateIMG)
                    API_warpImageTransformix(OPTs.EXE_Transformix,...
                                             OPTs.propagateIMG(pp).FileName,...
                                             OPTs.transformParameters,...
                                             OPTs.tempOutputFolderPath,...
                                             'REF',OPTs.movingFileName,...
                                             'TAG',OPTs.regTag,...
                                             'INTERPMODE',OPTs.propagateMode);
                end
            end
            
            convertWarpedNII2PNG(OPTs.tempOutputFolderPath,...
                           OPTs.movingFileName,...
                           OPTs.regTag,...
                           OPTs.warpedMovingBinaryFlag);
            
            cleanupFolderPath(OPTs.tempOutputFolderPath,...
                              OPTs.movingFileName,...
                              OPTs.regTag,...
                              OPTs.outputFolderPath);
            
            elps_Time = toc;
            if ~OPTs.embedFlag
                disp(' ');
                disp([' *** Registration Succesfully Completed - Elapsed Time: ',...
                      num2str(elps_Time,'%.2f'),' s']);
                disp(' ');
            else
                disp([' * Registration Completed - Elapsed Time: ',...
                      num2str(elps_Time,'%.2f'),' s']);
                disp(' ');
            end
        else
            disp(' <!> Something went wrong with the Registration - Please Check Manually!');
            disp(' ');
        end
    catch
        disp(' <!> ERROR occurred while Registering 2D Polarimetry Scans! - Please check Manually!');
        disp(' ');
    end
else
    disp(' <!> Missing or Inconsistent Inputs! -- Abort.');
    disp(' ');
end

function OPTs = getInputs(Inputs)

OPTs = chkHelp(Inputs);
if OPTs.helpFlag
    return; % skip the rest of OPTs configuration
end

if ~exist('load_nii') %#ok<EXIST>
    disp(' [wrn] NIFTI I/O Library may not be Loaded -- Possible Unexpected Behaviours');
end

OPTs = configTagsFilePaths(OPTs,getConfigTagsFilePaths);

OPTs.fixedFileName = []; % Input FIXED
OPTs.movingFileName = []; % Input MOVING
OPTs.paramFileName = {}; % Registration Parameters (ELASTIX)
OPTs.outputFolderPath = []; % Output FOLDER

OPTs.warpedMovingBinaryFlag = false; % Flag to consider the warped MOVING as BINARY
OPTs.inverseFlag = false; % Enable this flag to swap between FIXED and MOVING
OPTs.propagateIMG = []; % Input MASK(s) to be propagated together with MOVING
OPTs.propagateMode = 1; % 0 = bool , (1 = float) , 2 = integer
OPTs.verboseFlag = false;
OPTs.embedFlag = false; % Use this flag for batch processing (changes text display)
OPTs.regTag = 'MISSING-TAG'; % e.g. Rigid, Affine, Elastic (as string tag)
OPTs.proceedRegistration = false;

if ~isempty(Inputs)
    for jj = 1 : 2 : length(Inputs)
        switch upper(Inputs{jj})
            case 'F'
                OPTs.fixedFileName = Inputs{jj+1};
            case 'M'
                OPTs.movingFileName = Inputs{jj+1};
            case 'O'
                OPTs.outputFolderPath = chkFolder(char(Inputs{jj+1}));
            case 'P'
                if isempty(OPTs.paramFileName)
                    if iscell(Inputs{jj+1})
                        OPTs.paramFileName = reshape(Inputs{jj+1},[numel(Inputs{jj+1}),1]);
                    else
                        OPTs.paramFileName = Inputs(jj+1);
                    end
                else
                    if iscell(Inputs{jj+1})
                        OPTs.paramFileName = cat(1,OPTs.paramFileName,...
                                                   Inputs{jj+1});
                    else
                        OPTs.paramFileName = cat(1,OPTs.paramFileName,...
                                                   reshape(Inputs{jj+1},[numel(Inputs{jj+1}),1]));
                    end
                end
            case 'INVERSE'
                OPTs.inverseFlag = getNumericArg(Inputs{jj+1},'BOOL','SCALAR');
            case 'PROPIMG'
                OPTs.propagateIMG = Inputs{jj+1};
            case 'PROPMODE'
                OPTs.propagateMode = getNumericArg(Inputs{jj+1},'ABS','ROUND','SCALAR');
            case 'VERBOSE'
                OPTs.verboseFlag = getNumericArg(Inputs{jj+1},'BOOL','SCALAR');
            case 'TAG'
                OPTs.regTag = Inputs{jj+1};
            case 'EMBED'
                OPTs.embedFlag = getNumericArg(Inputs{jj+1},'BOOL','SCALAR');
            otherwise
                disp([' * MAIN_registerPolarimetry -- Unrecognised Parsed Parameter: ',...
                      Inputs{jj},' -- Default Applied.']);
        end
    end
end
% Loading Input FIXED (manual GUI prompt)
if isempty(OPTs.fixedFileName)
    disp(' >>> [Prompt] Select Input FIXED Polarymetric 2D Scan: ...');
    [FIX_FileName,...
     FIX_FilePath,...
     FIX_FilterIndex] = uigetfile('*.png*','Select Input FIXED Polarymetric 2D Scan');
    if FIX_FilterIndex
        OPTs.fixedFileName = strcat(FIX_FilePath,...
                                    FIX_FileName);
    end
end
% Loading Input MOVING (manual GUI prompt)
if isempty(OPTs.movingFileName)
    disp(' >>> [Prompt] Select Input MOVING Polarymetric 2D Scan: ...');
    [MOV_FileName,...
     MOV_FilePath,...
     MOV_FilterIndex] = uigetfile('*.png*','Select Input MOVING Polarymetric 2D Scan');
    if MOV_FilterIndex
        OPTs.movingFileName = strcat(MOV_FilePath,...
                                     MOV_FileName);
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
% Loading OUTPUT Folder (manual GUI prompt)
if isempty(OPTs.outputFolderPath)
    disp(' >>> [Prompt] Select Output FOLDER for Polarymetric Registration: ...');
    OPTs.outputFolderPath = uigetdir(pwd,'Select Output FOLDER for Polarymetric Registration');
    OPTs.outputFolderPath = chkFolder(OPTs.outputFolderPath);
end
% Assert Correct Necessary Inputs
if ~isempty(OPTs.fixedFileName) && ...
   ~isempty(OPTs.movingFileName) && ...
   ~isempty(OPTs.paramFileName) && ...
   ~isempty(OPTs.outputFolderPath)
    OPTs.proceedRegistration = true;
    
    % create a temporary folder for intermediate outputs which will be
    % eventually removed (avoiding conflicting overwriting)
    
    OPTs.tempOutputFolderPath = [OPTs.outputFolderPath,'temp_',...
                                 char(datetime('now','Format','yyyyMMdd_HHmmss')),'/'];
    if ~exist(OPTs.tempOutputFolderPath,'file')
        mkdir(OPTs.tempOutputFolderPath);
    end
end

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
'\n * HELP: MAIN_registerPolarimetry\n',...
'\n',...
' Use this Function to *REGISTER* a pair of Polarymetric 2D Scans.\n',...
' The software is a wrapper of ELASTIX and requires few mandatory inputs.\n',...
'\n',...
' * Configuration *\n',...
' This function requires: \n',...
'\t Elastix (latest version) correctly compiled or installed and configured\n',...
'\t -> See configPath.cfg\n',...
'\t NB: This SW requires also the NIFTI I/O library [only for Matlab code]\n',...
'\n',...
' Inputs:\n',...
'\n',...
'\t ''F'': Filepath string of the FIXED Polarymetric 2D Scan (*.png)\n',...
'\t ''M'': Filepath string of the MOVING Polarymetric 2D Scan (*.png)\n',...
'\t ''O'': Filepath string of the OUTPUT Folder for the Registration\n',...
'\t ''P'': Filepath string of the PARAMETERS File for the Registration (*.txt)\n',...
'\t [''Tag'']: User-Identifier String for Registration Type - e.g. ''Rigid'' (default: '''')\n',...
'\t [''Inverse'']: Scalar Boolean for inverse MAPPING [swap FIXED with MOVING] (default: 0)\n',...
'\t [''PropImg'']: Filepath string of another image [in the MOVING space]\n',...
'\t              to be propagated after the registration, e.g. a ROI mask (*.png)\n',...
'\t [''PropBinary'']: Scalar Boolean for considering ''PropImg'' as Binary (default: 0)\n',...
'\t [''Verbose'']: Scalar Boolean for verbose output (default: 0)\n',...
'\t [''Embed'']: Scalar Boolean for verbose in a Batch processing (default: 0)\n',...
'\n',...
'\t NB: a GUI is propmted when inputs are not provided.\n',...
'\t     Optional Inputs will not be prompted with a GUI.\n',...
'\n',...
' Automatic Outputs (within the OUTPUT Folder):\n',...
'\n',...
'\t *_<TAG>_elastix.log: Log file of the Registration (Elastix)\n',...
'\t *_<TAG>_TransformParameters_*.txt: Estimated Transformation Parameter Files \n',...
'\t *_<TAG>_TransformParameters_*.png: Aligned and Warped MOVING Scan after Registration\n',...
'\n',...
'\n',...
' Function Call:\n',...
'\n',...
'\t MAIN_registerPolarimetry(''F'',''~/myPath/fixedIMG.png'',''M'',''~/myPath/movingIMG.png'',''O'',''~/myOutputPath/'',''P'',''~/myPath/paramRegistration.txt'');\n',...
'\n',...
' Version: 1.0 - June 2022\n',... % Same Everywhere
' Developed by: Stefano Moriconi -- stefano.nicola.moriconi@gmail.com\n',... % Same Everywhere
'\n',...
' See also:\n',...
'\t https://elastix.lumc.nl/\n',...
'\n');

function outArg = getNumericArg(inArg,varargin)
if ~isnumeric(inArg)
    if strcmpi(inArg,'TRUE')
        outArg = true;
    elseif strcmpi(inArg,'FALSE')
        outArg = false;
    elseif islogical(inArg) % ADD this line!
        outArg = inArg; % Add this line!
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

function convertWarpedNII2PNG(folderPath,refFileName,tagLabel,binaryFlag)
NIIlist = dir([folderPath,'/*.nii*']);
transformParameters = getTransformParameters(folderPath,true);

if ~isempty(NIIlist)
    refFileName = removeFileNameExtension(refFileName);
    PNGext = '.png';
    
    % Finding the matching between NII and Transform Parameters
    NIImatchTPidx = getMatchingNIIandTP(NIIlist,transformParameters);
    
    for jj = 1 : length(NIIlist)
        
        if ~isequal(NIImatchTPidx(jj),0)
            
            inNIIFileName = strcat(NIIlist(jj).folder,'/',NIIlist(jj).name);
            
            [~,trgTPName,~] = fileparts(transformParameters{NIImatchTPidx(jj)});
            trgTPName = strrep(trgTPName,'.','_');
            
            % Generating FileNames for Conversion
            if ~strcmp(tagLabel,'')
                outPNGFileName = strcat(folderPath,'/',...
                    refFileName,'_',...
                    tagLabel,'_',...
                    trgTPName,PNGext);
            else
                outPNGFileName = strcat(folderPath,'/',...
                    refFileName,'_',...
                    trgTPName,PNGext);
            end
            
            convertNIItoPNG( inNIIFileName,...
                outPNGFileName,...
                binaryFlag );
            
            delete( inNIIFileName );
            
        else
            disp(' <!> Matching Not Found between NIFTI and Transform Parameters! - BUG and Unexpected Behaviour!');
        end
    end
end

function NIImatchTPidx = getMatchingNIIandTP(NIIlist,transformParameters)
NIImatchTPidx = zeros(length(NIIlist),1);
for nii = 1 : length(NIIlist)
    NIItagNum = regexp(NIIlist(nii).name,'\d*','Match');
    if ~isempty(NIItagNum)
        NIItagNum = str2double(NIItagNum{1});
    else
        NIItagNum = [];
    end
    for tp = 1 : size(transformParameters,1)
        TPtagNum = regexp(transformParameters{tp},'\d*','Match');
        if ~isempty(TPtagNum)
            TPtagNum = str2double(TPtagNum{1});
        else
            TPtagNum = NaN;
        end
        if isequal(NIItagNum,TPtagNum)
            NIImatchTPidx(nii) = tp;
            break;
        end
    end
end

function outFileName = removeFileNameExtension(inFileName)
[~,FileName,~] = fileparts(inFileName);
dotpos = strfind(FileName,'.');
if ~isempty(dotpos)
    outFileName = FileName(1:dotpos(1)-1); % removes all string after the FIRST DOT (included)!
else
    outFileName = FileName;
end

function cleanupFolderPath(tempFolderPath,refFileName,tagLabel,finalFolderPath)
NIIlist = dir([tempFolderPath,'*.nii*']);
IIlist = dir([tempFolderPath,'IterationInfo*.txt']);
LOGlist = dir([tempFolderPath,'elastix.log']);
TPlist = dir([tempFolderPath,'TransformParameters*.txt']);
PNGlist = dir([tempFolderPath,'*.png']);
% Deleting all NIFTIs
if ~isempty(NIIlist)
    for jj = 1 : length(NIIlist)
        delete(strcat(NIIlist(jj).folder,'/',NIIlist(jj).name));
    end
end
% Deleting all intermediary IterationInfo*.txt
if ~isempty(IIlist)
    for jj = 1 : length(IIlist)
        delete(strcat(IIlist(jj).folder,'/',IIlist(jj).name));
    end
end
% Extracting MOVING reference FileName
refFileName = removeFileNameExtension(refFileName);
% Renaming LOG file(s)
if ~isempty(LOGlist)
    for jj = 1 : length(LOGlist)
        if length(LOGlist) > 1
            maxLeadingZeros = num2str(floor(log10(length(LOGlist))) + 1,'%d');
            if strcmp(tagLabel,'')
                movefile(strcat(LOGlist(jj).folder,'/',LOGlist(jj).name),...
                         strcat(LOGlist(jj).folder,'/',refFileName,'_',...
                                num2str(jj,['%0',maxLeadingZeros,'d']),'_',...
                                LOGlist(jj).name));
            else
                movefile(strcat(LOGlist(jj).folder,'/',LOGlist(jj).name),...
                         strcat(finalFolderPath,refFileName,'_',...
                                tagLabel,'_',...
                                num2str(jj,['%0',maxLeadingZeros,'d']),'_',...
                                LOGlist(jj).name));
            end
        else
            if strcmp(tagLabel,'')
                movefile(strcat(LOGlist(jj).folder,'/',LOGlist(jj).name),...
                         strcat(finalFolderPath,refFileName,'_',LOGlist(jj).name));
            else
                movefile(strcat(LOGlist(jj).folder,'/',LOGlist(jj).name),...
                         strcat(finalFolderPath,refFileName,'_',tagLabel,'_',LOGlist(jj).name));
            end
        end
    end
end
% Renaming Estimated Transformation Parameters
if ~isempty(TPlist)
    for jj = 1 : length(TPlist)
        [~,outTPname,outTPext] = fileparts(TPlist(jj).name); 
        outTPname = strrep(outTPname,'.','_');
        if strcmp(tagLabel,'')
            movefile(strcat(TPlist(jj).folder,'/',TPlist(jj).name),...
                     strcat(finalFolderPath,refFileName,'_',...
                            outTPname,outTPext));
        else
            movefile(strcat(TPlist(jj).folder,'/',TPlist(jj).name),...
                     strcat(finalFolderPath,refFileName,'_',...
                            tagLabel,'_',...
                            outTPname,outTPext));
        end
    end
end
% Moving the PNGs
if ~isempty(PNGlist)
    for jj = 1 : length(PNGlist)
        movefile(strcat(PNGlist(jj).folder,'/',PNGlist(jj).name),...
                 strcat(finalFolderPath,PNGlist(jj).name));
    end
end
% Finally Delete the temporary folder
rmdir(tempFolderPath,'s');

function displayInputs(OPTs)
disp([' * EXECUTABLE: ',OPTs.EXE_Elastix]);
disp([' * FIXED: ',OPTs.fixedFileName]);
disp([' * MOVING: ',OPTs.movingFileName]);
for pp = 1 : size(OPTs.paramFileName,1)
    if pp == 1
        disp([' * PARAMETERS: ',OPTs.paramFileName{pp}]);
    else
        disp(['               ',OPTs.paramFileName{pp}]);
    end
end
disp([' * OUTPUT FOLDER: ',OPTs.outputFolderPath]);
if ~isempty(OPTs.regTag)
    disp([' * TAG: ',OPTs.regTag]);
end
if OPTs.inverseFlag
    disp(' * INVERSE MAPPING: Enabled');
end

if ~isempty(OPTs.propagateIMG) % Changed for MULTI-MASKS
    for pp = 1 : length(OPTs.propagateIMG)
        if pp == 1
            disp([' * PROPAGATE IMAGE: ',OPTs.propagateIMG(pp).FileName]);
        else
            disp(['                    ',OPTs.propagateIMG(pp).FileName]);
        end
    end
    if OPTs.propagateMode == 0
        disp('            BINARY: enabled - (logical masks)');
    elseif OPTs.propagateMode == 1
        disp('            FLOAT: enabled - (grayscale intensities)');
    else % OPTs.propagateMode == 2
        disp('            INTEGERS: enabled - (annotation labels)');
    end
end
disp('');
disp(' * Registration: ...');

function transformParameters = getTransformParameters(outputFolderPath,NameOnlyFlag)
TPlist = dir([outputFolderPath,'TransformParameters.*.txt']);
transformParameters = {};
if ~isempty(TPlist)
    for tp = 1 : length(TPlist)
        if NameOnlyFlag
            if isempty(transformParameters)
                transformParameters = {TPlist(tp).name};
            else
                transformParameters = cat(1,transformParameters,...
                    {TPlist(tp).name});
            end
        else
            if isempty(transformParameters)
                transformParameters = {strcat(TPlist(tp).folder,'/',...
                    TPlist(tp).name)};
            else
                transformParameters = cat(1,transformParameters,...
                    {strcat(TPlist(tp).folder,'/',...
                    TPlist(tp).name)});
            end
        end
    end
end