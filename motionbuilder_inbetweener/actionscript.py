from PySide6 import QtWidgets, QtCore, QtGui
from shiboken6 import wrapInstance

import pyfbsdk as fb

from . import pose_inbetween


def get_main_window() -> QtWidgets.QMainWindow:
    return wrapInstance(fb.FBGetMainWindow(), QtWidgets.QMainWindow)


class InbetweenerOverlay(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget, models: set[fb.FBModel]):
        super().__init__(parent)
        self.setWindowFlags(QtCore.Qt.WindowType.FramelessWindowHint | QtCore.Qt.WindowType.Window | QtCore.Qt.WindowType.Tool)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 0.01);")

        self.setMouseTracking(True)
        self.setGeometry(parent.geometry())

        self.value = 0.0

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        # We need to add something just so the layout doesn't collapse to 0 size
        placeholder = QtWidgets.QLabel("", self)
        placeholder.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(placeholder)

        # Label displaying the value
        self.value_label = QtWidgets.QLabel("0.00", self)

        self.value_label.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.value_label.setFixedSize(50, 20)

        self.undo_manager = fb.FBUndoManager()

        self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor)

        mouse_pos = self.mapFromGlobal(QtGui.QCursor.pos())
        self.value_label.setGeometry(mouse_pos.x() - 20, mouse_pos.y() - 20, 200, 50)
        self.update_stylesheet()

        self.translation = True
        self.rotation = True
        self.scale = False
        self.blend_from_current_pose = True

        self.show()

        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.activateWindow()
        self.setFocus()

        self.start_editing()

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        if event.key() == QtCore.Qt.Key.Key_Escape:
            self.cancel()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        event.accept()
        self.close()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        mouse_pos = event.pos()

        delta = (mouse_pos.x() - self.__mouse_pos)
        self.__mouse_pos = mouse_pos.x()

        if event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
            delta *= 0.1

        self.update_value(self.value + (delta / 150))

        event.accept()

    def close(self):
        self.deleteLater()
        self.end_editing()
        return super().close()

    def cancel(self):
        self.close()

    def start_editing(self):
        self.cache_nearest_poses()
        self.__mouse_pos = self.mapFromGlobal(QtGui.QCursor.pos()).x()
        self.value = 0.0

        self.undo_manager.TransactionBegin("Inbetween")
        for model in self.models:
            self.undo_manager.TransactionAddModelTRS(model)

    def end_editing(self):
        self.undo_manager.TransactionEnd()

    def update_value(self, value: float):
        self.value = value
        self.value_label.setText(f"{self.value:.2f}")
        self.update_stylesheet()
        self.apply_inbetween(self.value)

    def update_stylesheet(self):
        color = "orange" if abs(self.value) > 1 else "white"
        self.value_label.setStyleSheet(f"color: {color}; font-size: 14px; background-color: rgba(0, 0, 0, 0.7);")

    def cache_nearest_poses(self):
        """ 
        Check for the nearest neighboring poses and store them
        """
        self.models = pose_inbetween.get_models()

        self.prev_pose_time, self.next_pose_time = pose_inbetween.get_closest_keyframes(
            self.models,
            self.translation,
            self.rotation,
            self.scale
        )

        fb.FBSystem().Scene.Evaluate()
        self.current_pose = pose_inbetween.get_pose(self.models)

        with pose_inbetween.set_time_ctx(self.prev_pose_time, eval=True):
            self.prev_pose = pose_inbetween.get_pose(self.models)

        with pose_inbetween.set_time_ctx(self.next_pose_time, eval=True):
            self.next_pose = pose_inbetween.get_pose(self.models)

        pose_inbetween.apply_pose(self.models, self.current_pose)

    def apply_inbetween(self, value: float):
        ratio = value

        if self.blend_from_current_pose:
            if ratio > 0:
                other_pose = self.next_pose
            else:
                other_pose = self.prev_pose
                ratio = -ratio

            if self.current_pose is None or other_pose is None:
                return

            pose_inbetween.apply_inbetween_pose(self.models,
                                                self.current_pose,
                                                other_pose,
                                                ratio,
                                                use_translation=self.translation,
                                                use_rotation=self.rotation,
                                                use_scaling=self.scale)

        elif self.prev_pose is not None and self.next_pose is not None:
            ratio = (ratio + 1) / 2

            pose_inbetween.apply_inbetween_pose(self.models,
                                                self.prev_pose,
                                                self.next_pose,
                                                ratio,
                                                use_translation=self.translation,
                                                use_rotation=self.rotation,
                                                use_scaling=self.scale)


def main():
    models = pose_inbetween.get_models()
    if not models:
        return

    InbetweenerOverlay(get_main_window(), models)


if __name__ == "__main__" or "builtin" in __name__:
    main()
