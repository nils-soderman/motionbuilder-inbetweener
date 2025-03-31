"""
Drag and drop this script into the MotionBuilder viewport and select "Execute" to add this tool as a menu entry under the Animation menu.
"""
from __future__ import annotations

import shutil
import site
import sys
import os

try:
    import pyfbsdk as fb
except ImportError:
    print("This script must be run inside MotionBuilder, please drag and drop it into the MotionBuilder window.")
    sys.exit(1)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))


def get_python_user_startup_dir() -> str | None:
    """ 
    Get the directory of the user startup scripts
    """
    PythonConfig = fb.FBConfigFile("@Application.txt")
    return PythonConfig.Get("Python", "PythonStartup")


def get_source_dir() -> str:
    """
    Get the src directory for the inbetweener
    """
    return os.path.normpath(os.path.join(CURRENT_DIR, "..", "motionbuilder_inbetweener"))


def get_startup_script() -> str:
    return os.path.join(CURRENT_DIR, "register_inbetweener.py")


def main() -> bool:
    startup_dir = get_python_user_startup_dir()
    if not startup_dir:
        fb.FBMessageBox("Setup Error", "Could not find the Python startup directory.\nPlease check: \nSettings > Preferences > Python > Python startup folder", "OK")
        return False

    source_dir = get_source_dir()
    if not os.path.isdir(source_dir):
        fb.FBMessageBox("Setup Error", f"Could not find the source directory at:\n{source_dir}", "OK")
        return False

    startup_script = get_startup_script()
    if not os.path.isfile(startup_script):
        fb.FBMessageBox("Setup Error", f"Could not find the startup script at:\n{startup_script}", "OK")
        return False

    os.makedirs(startup_dir, exist_ok=True)

    startup_script_target = os.path.join(startup_dir, os.path.basename(startup_script))

    shutil.copy(startup_script, startup_script_target)

    # Copy the entire source directory to the startup directory
    target_dir = os.path.join(site.getusersitepackages(), os.path.basename(source_dir))
    requires_reload = os.path.exists(target_dir)  # Check if we're re-installing the tool
    if requires_reload:
        shutil.rmtree(target_dir)
    shutil.copytree(source_dir, target_dir)

    import register_inbetweener
    if not register_inbetweener.does_menu_exist():
        register_inbetweener.main()

    import motionbuilder_inbetweener
    if requires_reload:
        import importlib
        importlib.reload(motionbuilder_inbetweener)

    motionbuilder_inbetweener.show_tool()

    fb.FBMessageBox("Setup Complete", f"Inbetweener has been installed successfully.\nThe Inbetweener tool can be found in the {register_inbetweener.PARENT_MENU} menu.", "OK")
    return True


if __name__ == "builtins":
    main()
