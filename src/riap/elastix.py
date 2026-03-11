import platform


def generate_config_file(binaries_path, scripts_path):
    """
    Generate a configuration file with paths to Elastix executables and libraries for MATLAB engine.
    """
    if platform.system() == 'Windows':
        raise NotImplementedError(f"Please change the paths in the file {str(scripts_path / 'configFilePaths.cfg')} manually for Windows OS, as the current implementation is for Linux.")
    elastix_exe = binaries_path / "bin" / "elastix"
    transformix_exe = binaries_path / "bin" / "transformix"
    elastix_lib = binaries_path / "lib"
    
    shared_libs = r'# /lib/x86_64-linux-gnu/'

    original_file = [
        r'% This is a configuration file with paths to external wrapped executables,',
        r'% or auxiliary configuration data employed in the compiled package.',
        r'% Please specify the local FilePaths - leave blank otherwise.',
        r'% All Entries follow the pattern: #ExecutableTAG \n strExecutableFILEPATH',
        '% Header lines starting with \'%\' will be treated as comments and ignored.',
        r'#EXE_Elastix',
        elastix_exe,
        r'% Path HERE!',
        r'#EXE_Transformix',
        transformix_exe,
        r'% Path HERE!',
        r'#LIB_SystemSharedLibs',
        shared_libs,
        '% Find the above path by running \'ldd <#EXE_Elastix>\' in the UNIX terminal',
        r'#LIB_Elastix',
        elastix_lib,
        r'% Path HERE!'
    ]
    path = scripts_path / 'configFilePaths.cfg'
    with open(path, 'w') as fp:
        for item in original_file:
            fp.write("%s\n" % item)