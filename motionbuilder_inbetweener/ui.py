from . import pose_inbetween

import os

import pyfbsdk as fb
import pyfbsdk_additions as fb_additions

try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from shiboken6 import wrapInstance, getCppPointer
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from shiboken2 import wrapInstance, getCppPointer


TOOL_NAME = "In-betweener"

STYLESHEET_FILE = os.path.join(os.path.dirname(__file__), "style.qss")


class Slider(QtWidgets.QSlider):
    SLIDER_RESOLUTION = 1000

    def __init__(self, parent: QtWidgets.QWidget):
        super().__init__(parent)
        self.setOrientation(QtCore.Qt.Horizontal)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.bIsEditing = False

        self.last_value = 0
        self.last_mouse_pos_x = None

        self.setTickInterval(250)

        self.setMinimum(int(-1.5 * self.SLIDER_RESOLUTION))
        self.setMaximum(int(1.5 * self.SLIDER_RESOLUTION))

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        super().mousePressEvent(event)
        self.bIsEditing = True
        if event.modifiers() & QtCore.Qt.ShiftModifier:
            self.setValue(0)

        if event.modifiers() & QtCore.Qt.ControlModifier:
            self.snap(event)

        self.last_mouse_pos_x = event.pos().x()
        self.last_value = self.value()

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        super().mouseReleaseEvent(event)
        self.bIsEditing = False
        self.last_mouse_pos_x = None
        self.last_value = 0

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        if self.bIsEditing and self.last_mouse_pos_x is not None:

            # Snap if control is pressed
            if event.modifiers() & QtCore.Qt.ControlModifier:
                self.snap(event)
                return

            delta = event.pos().x() - self.last_mouse_pos_x

            # Use more precise delta if shift is pressed
            if event.modifiers() & QtCore.Qt.ShiftModifier:
                delta *= 0.1

            self.last_value = self.last_value + (delta / self.width()) * (self.maximum() - self.minimum())
            self.setValue(self.last_value)

            self.last_mouse_pos_x = event.pos().x()

    def snap(self, event: QtGui.QMouseEvent):
        value = (self.maximum() - self.minimum()) * event.pos().x() / self.width() + self.minimum()
        self.last_value = round(value / self.tickInterval()) * self.tickInterval()
        self.setValue(self.last_value)
        self.last_mouse_pos_x = event.pos().x()

class TRSOption(QtWidgets.QWidget):
    """
    Widget containing 3 buttons to toggle translation, rotation and scaling
    """

    def __init__(self, parent: QtWidgets.QWidget):
        super().__init__(parent)

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(4, 0, 0, 0)
        layout.setSpacing(2)

        self.settings = QtCore.QSettings("MotionBuilder", "InBetweener")

        self.translation_btn = QtWidgets.QPushButton("T")
        self.rotation_btn = QtWidgets.QPushButton("R")
        self.scale_btn = QtWidgets.QPushButton("S")

        for btn, default_value in ((self.translation_btn, True),
                                   (self.rotation_btn, True),
                                   (self.scale_btn, False)):
            btn.setCursor(QtCore.Qt.PointingHandCursor)
            btn.setCheckable(True)
            btn.setChecked(self.settings.value(btn.text(), default_value, type=bool))
            layout.addWidget(btn)

        self.setLayout(layout)

        self.translation_btn.clicked.connect(self.on_button_clicked)
        self.rotation_btn.clicked.connect(self.on_button_clicked)
        self.scale_btn.clicked.connect(self.on_button_clicked)

    def on_button_clicked(self):
        # If Ctrl is pressed, set the clicked button as the only checked button
        modifiers = QtGui.QGuiApplication.keyboardModifiers()
        sender = self.sender()
        if modifiers == QtCore.Qt.ControlModifier:
            self.translation_btn.setChecked(sender == self.translation_btn)
            self.rotation_btn.setChecked(sender == self.rotation_btn)
            self.scale_btn.setChecked(sender == self.scale_btn)

        self.settings.setValue(sender.text(), sender.isChecked())

    @property
    def translation(self) -> bool:
        return self.translation_btn.isChecked()

    @property
    def rotation(self) -> bool:
        return self.rotation_btn.isChecked()

    @property
    def scale(self) -> bool:
        return self.scale_btn.isChecked()


class PoseInbetween(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget, stylesheet: str | None = None):
        super().__init__(parent)

        self.undo_manager = fb.FBUndoManager()

        if stylesheet is not None:
            self.setStyleSheet(stylesheet)
        else:
            with open(STYLESHEET_FILE, "r") as f:
                self.setStyleSheet(f.read())

        self.editing = False

        self.models = set()
        self.next_pose = None
        self.prev_pose = None
        self.current_pose = None

        self.init_ui()

    def init_ui(self):
        layout = QtWidgets.QHBoxLayout()
        layout.setSpacing(5)
        layout.setContentsMargins(1, 1, 1, 1)

        self.trs_option = TRSOption(self)

        self.slider = Slider(self)

        self.label = QtWidgets.QLabel("0.00")
        self.label.setFixedWidth(30)
        self.slider.valueChanged.connect(self.slider_value_changed)
        self.slider.sliderPressed.connect(self.slider_pressed)
        self.slider.sliderReleased.connect(self.slider_released)

        layout.addWidget(self.trs_option)
        layout.addWidget(self.slider)
        layout.addWidget(self.label)

        self.setLayout(layout)

        self.returnPressedShortcut = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Return), self)
        self.returnPressedShortcut.activated.connect(self.close)

    def slider_pressed(self):
        self.update_pose()

        self.undo_manager.TransactionBegin("Inbetween Pose")
        for model in self.models:
            self.undo_manager.TransactionAddModelTRS(model)

        self.editing = True
        self.slider_value_changed(self.slider.value())

    def slider_released(self):
        self.editing = False
        self.label.setText("0.00")

        self.slider.blockSignals(True)
        self.slider.setValue(0)
        self.slider.blockSignals(False)

        self.undo_manager.TransactionEnd()

    def slider_value_changed(self, value: int):
        if not self.editing:
            return

        self.label.setText(f"{value / 1000:.2f}")

        ratio = value / Slider.SLIDER_RESOLUTION

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
                                            use_translation=self.trs_option.translation,
                                            use_rotation=self.trs_option.rotation,
                                            use_scaling=self.trs_option.scale)

    def update_pose(self):
        self.models = pose_inbetween.get_models()

        self.current_time = fb.FBSystem().LocalTime
        self.prev_pose_time, self.next_pose_time = pose_inbetween.get_closest_keyframes(self.models)

        fb.FBSystem().Scene.Evaluate()
        self.current_pose = pose_inbetween.get_pose(self.models)

        with pose_inbetween.set_time_ctx(self.prev_pose_time, eval=True):
            self.prev_pose = pose_inbetween.get_pose(self.models)

        with pose_inbetween.set_time_ctx(self.next_pose_time, eval=True):
            self.next_pose = pose_inbetween.get_pose(self.models)

        pose_inbetween.apply_pose(self.models, self.current_pose)


class NativeWidgetHolder(fb.FBWidgetHolder):
    def __init__(self, stylesheet: str | None = None):
        super().__init__()

        self.stylesheet = stylesheet

    def WidgetCreate(self, parent_cpp_ptr: int):
        self.native_widget = PoseInbetween(wrapInstance(parent_cpp_ptr, QtWidgets.QWidget), self.stylesheet)
        return getCppPointer(self.native_widget)[0]


class NativeQtWidgetTool(fb.FBTool):
    def __init__(self, name: str, stylesheet: str | None = None):
        super().__init__(name, True)
        self.native_holder = NativeWidgetHolder(stylesheet)
        self.BuildLayout()

        self.MinSizeY = 20

        self.StartSizeX = 350
        self.StartSizeY = 60

    def BuildLayout(self):
        x = fb.FBAddRegionParam(0, fb.FBAttachType.kFBAttachLeft, "")
        y = fb.FBAddRegionParam(0, fb.FBAttachType.kFBAttachTop, "")
        w = fb.FBAddRegionParam(0, fb.FBAttachType.kFBAttachRight, "")
        h = fb.FBAddRegionParam(0, fb.FBAttachType.kFBAttachBottom, "")

        region_name = "main"
        self.AddRegion(region_name, region_name, x, y, w, h)
        self.SetControl(region_name, self.native_holder)


def show_tool(stylesheet: str | None = None) -> fb.FBTool:
    fb_additions.FBDestroyToolByName(TOOL_NAME)

    if TOOL_NAME in fb_additions.FBToolList:
        tool = fb_additions.FBToolList[TOOL_NAME]
    else:
        tool = NativeQtWidgetTool(TOOL_NAME, stylesheet)

    return fb.ShowTool(tool)


if __name__ == "__main__" or "builtin" in __name__:
    show_tool()
