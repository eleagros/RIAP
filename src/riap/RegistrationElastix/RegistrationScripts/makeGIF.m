function makeGIF(varargin)

OPTs = getInputs(varargin);

if OPTs.proceed
    disp([' * Loading Images (*.',OPTs.imgEXT,') from: ',OPTs.inputFolderPath]);
    IMGs = dir(strcat(OPTs.inputFolderPath,'*.',OPTs.imgEXT));
    if ~isempty(IMGs)
        disp([' * Exporting GIF to: ',OPTs.outputGIF]);
        try
            for img = 1 : length(IMGs)
                tempimg = imread(strcat(IMGs(img).folder,'/',...
                                        IMGs(img).name      )  );
                                   
                if length(size(tempimg))>2
                    tempimg = rgb2gray(tempimg);
                end
                                   
                if img == 1
                    imwrite(tempimg,OPTs.outputGIF,'gif','Loopcount',inf);
                else
                    imwrite(tempimg,OPTs.outputGIF,'gif','WriteMode','append');
                end
            end
            disp(' * Exporting GIF: DONE! :)');
        catch
            disp(' <!> Some Error Occurred While Exporting to GIF! - Please check manually!');
        end
    else
        disp([' <!> No images (*.',OPTs.imgEXT,') were found in the input Folder! - Abort.']);
    end
else
    disp(' <!> Missing or Inconsistent Inputs! -- Abort.');
end

function OPTs = getInputs(Inputs)
OPTs.inputFolderPath = [];
OPTs.imgEXT = 'png';
OPTs.outputGIF = [];
OPTs.proceed = false;
if ~isempty(Inputs)
    for jj = 1 : 2 : length(Inputs)
        switch upper(Inputs{jj})
            case 'FOLDER'
                OPTs.inputFolderPath = chkFolder(char(Inputs{jj+1}));
            case 'EXT'
                OPTs.imgEXT = Inputs{jj+1};
            case 'OUTPUT'
                OPTs.outputGIF = Inputs{jj+1};
            otherwise
                disp([' * makeGIF: Unrecognised Parsed Parameter: ',...
                      Inputs{jj},' - Default Applied.']);
        end
    end
end
if isempty(OPTs.inputFolderPath)
    disp(' >>> [Prompt] Select Input FOLDER containing image frames for GIF: ...');
    OPTs.inputFolderPath = uigetdir(pwd,'Select Input FOLDER containing image frames for GIF');
    OPTs.inputFolderPath = chkFolder(OPTs.inputFolderPath);
end
if isempty(OPTs.outputGIF)
    disp(' >>> [Prompt] Select Output GIF file to export: ...');
    [outputGIFFileName,...
     outputGIFFolderPath,...
     outputGIFFilterIndex] = uiputfile('*.gif','Select Output GIF file to export');
    if outputGIFFilterIndex
        OPTs.outputGIF = strcat(outputGIFFolderPath,outputGIFFileName);
    end
end
if ~isempty(OPTs.inputFolderPath) && ...
   ~isempty(OPTs.outputGIF)
    OPTs.proceed = true;
end

function folderOUT = chkFolder(folderIN)
if ~isempty(folderIN)
    if ~strcmp(folderIN(end),'/')
        folderOUT = [folderIN,'/'];
    else
        folderOUT = folderIN;
    end
end