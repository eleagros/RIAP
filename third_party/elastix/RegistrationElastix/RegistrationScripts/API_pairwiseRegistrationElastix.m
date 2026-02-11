function successFlag = API_pairwiseRegistrationElastix(elastixFileName,fixedFileName,movingFileName,paramFileName,outputFolderPath,varargin)

successFlag = false;

OPTs = getInputs(varargin);

disp(elastixFileName)
if exist(elastixFileName,'file') && exist(fixedFileName,'file') && ...
   exist(movingFileName,'file') && exist(outputFolderPath,'file')
   
    % constructing the command string (with multiple parameters as composition)
    cmd = [ elastixFileName,...
            ' -f ', fixedFileName, ...
            ' -m ', movingFileName, ...
            ' -out ', outputFolderPath ];
    
    for pp = 1 : numel(paramFileName)
        cmd = cat(2,cmd,' -p ', paramFileName{pp});
    end
     
    if OPTs.VerboseFlag
        status = system( cmd , '-echo' );
    else
        [status,~] = system( cmd );
    end
    
    successFlag = status == 0;
else
    disp(' <!> API_pairwiseRegistrationElastix: Incorrect Inputs - Abort.');
end

function OPTs = getInputs(Inputs)
OPTs.VerboseFlag = false;
if ~isempty(Inputs)
    for jj = 1 : 2 : length(Inputs)
        switch upper(Inputs{jj})
            case 'VERBOSE'
                OPTs.VerboseFlag = logical(Inputs{jj+1}(1));
            otherwise
                disp([' * API_pairwiseRegistrationElastix -- Unrecognised Parsed Parameter: ',...
                      Inputs{jj},' -- Default Applied.']);
        end
    end
end