"""
For the Thorlabs camera SDK software to work, they need visibility of the directory containing the Thorlabs TSI
Native DLLs. This setup script changes the path (just for the current process, not the system
path) by adding the directory containing the DLLs. This script is written specifically to work on Windows,
but can be adjusted to work with custom programs. The following methods can also be used:

- Use the os module to adjust the program's current directory to be the directory containing the DLLs.
- Manually copy the DLLs into the working directory of your application.
- Manually add the path to the directory containing the DLLs to the system PATH environment variable.

"""
import os
import sys

def configure_path():
    is_64bits = sys.maxsize > 2**32

    full_path_current_directory = os.path.abspath(os.curdir)
    current_directory = full_path_current_directory.split(os.sep)[-1]
    
    relative_path_to_dlls = '..' + os.sep + current_directory + os.sep + 'dlls' + os.sep

    if is_64bits:
        relative_path_to_dlls += '64_lib'
    else:
        relative_path_to_dlls += '32_lib'

    absolute_path_to_file_directory = os.path.dirname(os.path.abspath(__file__))

    absolute_path_to_dlls = os.path.abspath(absolute_path_to_file_directory + os.sep + relative_path_to_dlls)

    os.environ['PATH'] = absolute_path_to_dlls + os.pathsep + os.environ['PATH']

    try:
        # Python 3.8 introduces a new method to specify dll directory
        os.add_dll_directory(absolute_path_to_dlls)
    except AttributeError:
        pass
