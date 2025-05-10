import motionbuilder_inbetweener.actionscript as actionscript

try:
    from PySide6 import QtCore
except ModuleNotFoundError:
    from PySide2 import QtCore

actionscript.activate(
    toggle_translation_key = QtCore.Qt.Key.Key_W,
    toggle_rotation_key = QtCore.Qt.Key.Key_E,
    toggle_scale_key = QtCore.Qt.Key.Key_U
)
