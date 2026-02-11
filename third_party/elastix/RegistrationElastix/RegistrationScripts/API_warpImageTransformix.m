function successFlag = API_warpImageTransformix(transformixFileName,imageFileName,transformParamsFileName,outputFolderPath,varargin)

successFlag = false;

OPTs = getInputs(varargin);

if exist(transformixFileName,'file') && exist(imageFileName,'file') && ...
   ~isempty(transformParamsFileName) && exist(outputFolderPath,'file')

    successFlags = false([size(transformParamsFileName,1),1]);
    for pp = 1 : size(transformParamsFileName,1)
        
        if OPTs.interpMode ~= 1
            % Create a temporary transform parameter where the resampling
            % is Nearest Neighbour
            nnTPFileName = gen_nnTP(transformParamsFileName{pp});
            
            % constructing the command string (with multiple parameters as composition)
            cmd = [ transformixFileName,...
                    ' -in ', imageFileName, ...
                    ' -out ', outputFolderPath,...
                    ' -tp ', nnTPFileName ];
        else
            % constructing the command string (with multiple parameters as composition)
            cmd = [ transformixFileName,...
                    ' -in ', imageFileName, ...
                    ' -out ', outputFolderPath,...
                    ' -tp ', transformParamsFileName{pp} ];
        end
        
        if OPTs.VerboseFlag
            status = system( cmd , '-echo' );
        else
            [status,~] = system( cmd );
        end
        
        if OPTs.interpMode ~= 1
            % Remove the temporary transform parameter where the resampling
            % is Nearest Neighbour
            delete(nnTPFileName);
        end

        successFlags(pp) = status == 0;
        
        if status ~= 0
            disp(' <!> API_warpImageTransformix: Some Error Occurred while warping an Image - Please Check Manually!');
        else
            % Renaming Routine
            NIIext = '.nii.gz';
            PNGext = '.png';
            warpedNII = dir([outputFolderPath,'result',NIIext]);
            if ~isempty(warpedNII)
                inWarpedNIIFileName = strcat(warpedNII.folder,'/',warpedNII.name);
                [~,trgIMGName,~] = fileparts(imageFileName);
                [~,trgTPName,~] = fileparts(transformParamsFileName{pp});
                trgTPName = strrep(trgTPName,'.','_');
                
                outPNGwarpedFileName = strcat(outputFolderPath,...
                                                  trgIMGName,'_');
                                              
                if ~strcmp(OPTs.refFileName,'') % Append REF
                    outPNGwarpedFileName = strcat(outPNGwarpedFileName,...
                                                  'PrpgTo_',...
                                                  OPTs.refFileName,'_');
                end
                
                if ~strcmp(OPTs.regTag,'') % Append TAG
                     outPNGwarpedFileName = strcat(outPNGwarpedFileName,...
                                                   OPTs.regTag,'_');
                end
                
                % Append TransformParameters Name and Extension
                outPNGwarpedFileName = strcat(outPNGwarpedFileName,...
                                              trgTPName,PNGext);
                
                convertNIItoPNG( inWarpedNIIFileName,...
                                 outPNGwarpedFileName,...
                                 OPTs.interpMode );
                            
                delete(inWarpedNIIFileName);% Remove the Warped NII   
            end
        end
        
    end

    successFlag = all(successFlags);
else
    disp(' <!> API_pairwiseRegistrationElastix: Incorrect Inputs - Abort.');
end

function OPTs = getInputs(Inputs)
OPTs.VerboseFlag = false;
OPTs.interpMode = 1; % 0 = bool , (1 = float) , 2 = integer
OPTs.regTag = 'MISSING-TAG';
OPTs.refFileName = 'MISSING-REF';
if ~isempty(Inputs)
    for jj = 1 : 2 : length(Inputs)
        switch upper(Inputs{jj})
            case 'VERBOSE'
                OPTs.VerboseFlag = logical(Inputs{jj+1}(1));
            case 'INTERPMODE'
                OPTs.interpMode = abs(round(Inputs{jj+1}(1)));
            case 'TAG'
                OPTs.regTag = char(Inputs{jj+1});
            case 'REF'
                OPTs.refFileName = char(Inputs{jj+1});
            otherwise
                disp([' * API_warpImageTransformix -- Unrecognised Parsed Parameter: ',...
                      Inputs{jj},' -- Default Applied.']);
        end
    end
end

if ~strcmp(OPTs.refFileName,'')
    OPTs.refFileName = removeFileNameExtension(OPTs.refFileName);
end

function outFileName = removeFileNameExtension(inFileName)
[~,FileName,~] = fileparts(inFileName);
dotpos = strfind(FileName,'.');
if ~isempty(dotpos)
    outFileName = FileName(1:dotpos(1)-1); % removes all string after the FIRST DOT (included)!
else
    outFileName = FileName;
end

function nnTPFileName = gen_nnTP(transformParamsFileName)
[folderPath,fileName,fileExt] = fileparts(transformParamsFileName);
nnTPFileName = strcat(folderPath,'/',fileName,'_nn',fileExt);
FIDr = fopen(transformParamsFileName,'r');
FIDw = fopen(nnTPFileName,'w');
rline = fgetl(FIDr);
ptrn0 = '(FinalBSplineInterpolationOrder ';
ptrn1 = ')';
BSplineValue = '0'; % Nearest Neighbours
while ischar(rline)
    if strcmp(computer,'PCWIN64')
        rline = strrep(rline,'\','/');
    end
    if contains(rline,ptrn0) && contains(rline,ptrn1)
        rline = [rline(1:length(ptrn0)),BSplineValue,rline(end-length(ptrn1)+1:end)];
    end
    fprintf(FIDw,[rline,'\n']);
    rline = fgetl(FIDr);
end
fclose(FIDr);
fclose(FIDw);