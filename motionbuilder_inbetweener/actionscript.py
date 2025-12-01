from __future__ import annotations

try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from shiboken6 import wrapInstance
except ModuleNotFoundError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from shiboken2 import wrapInstance

import pyfbsdk as fb

from . import pose_inbetween

STYLESHEET = """
QWidget {
    background-color: rgba(0, 0, 0, 0.65);
    font-size: 14px;
    color: white;
}

QLabel, QDoubleSpinBox {
    background-color: rgba(0, 0, 0, 0);
}

QLabel:disabled {
    color: rgba(255, 255, 255, 0.5);
}
"""

CTRL_SNAP_INCREMENT = 0.1


def get_main_window() -> QtWidgets.QMainWindow:
    return wrapInstance(fb.FBGetMainWindow(), QtWidgets.QMainWindow)


class InbetweenerOverlay(QtWidgets.QWidget):
    def __init__(self,
                 parent: QtWidgets.QWidget,
                 models: set[fb.FBModel],
                 fullbody: set[fb.FBModel],
                 toggle_translation_key: QtCore.Qt.Key = QtCore.Qt.Key.Key_W,
                 toggle_rotation_key: QtCore.Qt.Key = QtCore.Qt.Key.Key_E,
                 toggle_scale_key: QtCore.Qt.Key = QtCore.Qt.Key.Key_R):
        super().__init__(parent)

        self.setWindowFlags(QtCore.Qt.WindowType.FramelessWindowHint | QtCore.Qt.WindowType.Window | QtCore.Qt.WindowType.Tool)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.settings = QtCore.QSettings("MotionBuilder", "InBetweenerActionScript")
        self.undo_manager = fb.FBUndoManager()

        self.prev_pose_time = None
        self.next_pose_time = None

        self.blend_from_current_pose = True
        self.models = models
        self.fullbody = fullbody
        self.value = 0.0
        self._value_accumulator = 0.0

        self.toggle_translation_key = toggle_translation_key
        self.toggle_rotation_key = toggle_rotation_key
        self.toggle_scale_key = toggle_scale_key

        self.setGeometry(parent.geometry())
        self.setFixedSize(parent.geometry().size())

        self.setStyleSheet("background-color: rgba(0, 0, 0, 0.01);")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QtWidgets.QLabel(""))  # Layout cannot be empty, else it'll collapse to 0 size

        # Label displaying the value
        self.display_widget = QtWidgets.QWidget(self)
        self.display_widget.setStyleSheet(STYLESHEET)
        self.display_widget.setFixedSize(110, 25)
        self.display_widget.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        display_layout = QtWidgets.QHBoxLayout(self.display_widget)
        display_layout.setContentsMargins(0, 0, 0, 0)

        self.label_translation = QtWidgets.QLabel("T", self.display_widget)
        self.label_rotation = QtWidgets.QLabel("R", self.display_widget)
        self.label_scale = QtWidgets.QLabel("S", self.display_widget)
        for label, default in ((self.label_translation, True),
                               (self.label_rotation, True),
                               (self.label_scale, False)):
            label.setEnabled(bool(self.settings.value(label.text(), default, type=bool)))
            label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            label.setFixedSize(10, 20)
            display_layout.addWidget(label)

        self.value_label = QtWidgets.QLabel("0.00", self.display_widget)
        self.value_label.setFixedSize(40, 20)
        display_layout.addWidget(self.value_label)

        QtWidgets.QApplication.changeOverrideCursor(QtCore.Qt.CursorShape.SizeHorCursor)
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.SizeHorCursor)

        mouse_pos = self.mapFromGlobal(QtGui.QCursor.pos())
        self.display_widget.setGeometry(mouse_pos.x() - 20, mouse_pos.y() - 20, 200, 50)

        self.current_pose = pose_inbetween.get_pose(self.fullbody)

        self.start_editing()
        self.show()

        app = QtWidgets.QApplication.instance()
        if app:
            app.installEventFilter(self)

    @property
    def translation(self) -> bool:
        return self.label_translation.isEnabled()

    @property
    def rotation(self) -> bool:
        return self.label_rotation.isEnabled()

    @property
    def scale(self) -> bool:
        return self.label_scale.isEnabled()

    @translation.setter
    def translation(self, value: bool):
        self.label_translation.setEnabled(value)
        self.settings.setValue(self.label_translation.text(), value)
        self.on_trs_changed()

    @rotation.setter
    def rotation(self, value: bool):
        self.label_rotation.setEnabled(value)
        self.settings.setValue(self.label_rotation.text(), value)
        self.on_trs_changed()

    @scale.setter
    def scale(self, value: bool):
        self.label_scale.setEnabled(value)
        self.settings.setValue(self.label_scale.text(), value)
        self.on_trs_changed()

    def show(self):
        self.update_stylesheet()
        super().show()

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent):
        if event.type() is QtCore.QEvent.Type.MouseMove:
            self.mouseMoveEvent(event)
            return True
        if event.type() is QtCore.QEvent.Type.KeyPress:
            self.keyPressEvent(event)
            return True

        return super().eventFilter(watched, event)

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        if event.key() == QtCore.Qt.Key.Key_Escape:
            self.cancel()
        elif event.key() == self.toggle_translation_key:
            self.translation = not self.translation
            event.accept()
        elif event.key() == self.toggle_rotation_key:
            self.rotation = not self.rotation
            event.accept()
        elif event.key() == self.toggle_scale_key:
            self.scale = not self.scale
            event.accept()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.close()
        elif event.button() == QtCore.Qt.MouseButton.RightButton:
            self.cancel()

        event.accept()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        mouse_pos = event.pos()
        modifiers = event.modifiers()

        delta = (mouse_pos.x() - self.__mouse_pos) / 150
        self.__mouse_pos = mouse_pos.x()

        if modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier:
            delta *= 0.1

        self._value_accumulator += delta

        if modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
            snapped_value = round(self._value_accumulator / CTRL_SNAP_INCREMENT) * CTRL_SNAP_INCREMENT
            self.update_value(snapped_value)
        else:
            self.update_value(self._value_accumulator)

        event.accept()

    def close(self):
        self.deleteLater()
        self.end_editing()

        QtWidgets.QApplication.restoreOverrideCursor()

        app = QtWidgets.QApplication.instance()
        if app:
            app.removeEventFilter(self)

        return super().close()

    def cancel(self):
        pose_inbetween.apply_pose(self.models, self.current_pose)
        self.close()

    def start_editing(self):
        self.cache_nearest_poses()
        self.__mouse_pos = self.mapFromGlobal(QtGui.QCursor.pos()).x()
        self.value = 0.0
        self._value_accumulator = 0.0

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
        self.value_label.setStyleSheet(f"color: {color};")

    def on_trs_changed(self):
        self.cache_nearest_poses()
        self.apply_inbetween(self.value)

    def cache_nearest_poses(self):
        """ 
        Check for the nearest neighboring poses and store them
        """
        new_prev_pose_time, new_next_pose_time = pose_inbetween.find_nearest_keyframes(
            self.models,
            self.translation,
            self.rotation,
            self.scale
        )

        if new_prev_pose_time != self.prev_pose_time or new_next_pose_time != self.next_pose_time:
            self.prev_pose_time = new_prev_pose_time
            self.next_pose_time = new_next_pose_time

            with pose_inbetween.SetTimeCtx(self.prev_pose_time, eval=True):
                self.prev_pose = pose_inbetween.get_pose(self.models)

            with pose_inbetween.SetTimeCtx(self.next_pose_time, eval=True):
                self.next_pose = pose_inbetween.get_pose(self.models)

        pose_inbetween.apply_pose(self.fullbody, self.current_pose)

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


def activate(
    toggle_translation_key=QtCore.Qt.Key.Key_W,
    toggle_rotation_key=QtCore.Qt.Key.Key_E,
    toggle_scale_key=QtCore.Qt.Key.Key_R
):
    models, fullbody = pose_inbetween.get_active_keying_group_models()
    if not models:
        return

    InbetweenerOverlay(get_main_window(),
                       models,
                       fullbody,
                       toggle_translation_key=toggle_translation_key,
                       toggle_rotation_key=toggle_rotation_key,
                       toggle_scale_key=toggle_scale_key)


if __name__ == "__main__" or "builtin" in __name__:
    activate()
