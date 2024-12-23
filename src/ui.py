from . import pose_inbetween

import pyfbsdk as fb
import pyfbsdk_additions as fb_additions

try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from shiboken6 import wrapInstance, getCppPointer
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from shiboken2 import wrapInstance, getCppPointer

# from importlib import reload
# reload(pose_inbetween)


TOOL_NAME = "In-betweener"

class PoseInbetween(QtWidgets.QWidget):
    SLIDER_RESOLUTION = 1000

    def __init__(self, parent: QtWidgets.QWidget):
        super().__init__(parent)

        self.initUI()

        self.editing = False

        self.models = set()
        self.next_pose = None
        self.prev_pose = None
        self.current_pose = None

    def initUI(self):
        self.setWindowTitle("Pose Inbetween")
        self.setGeometry(100, 100, 300, 150)
        layout = QtWidgets.QHBoxLayout()

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.setSpacing(2)
        self.translation_toggle = QtWidgets.QPushButton("T")
        self.translation_toggle.setCheckable(True)
        self.translation_toggle.setChecked(True)
        self.rotation_toggle = QtWidgets.QPushButton("R")
        self.rotation_toggle.setCheckable(True)
        self.rotation_toggle.setChecked(True)
        self.scale_toggle = QtWidgets.QPushButton("S")
        self.scale_toggle.setCheckable(True)

        button_layout.addWidget(self.translation_toggle)
        button_layout.addWidget(self.rotation_toggle)
        button_layout.addWidget(self.scale_toggle)

        slider_layout = QtWidgets.QHBoxLayout()
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setMinimum(int(-1.5 * self.SLIDER_RESOLUTION))
        self.slider.setMaximum(int(1.5 * self.SLIDER_RESOLUTION))
        self.slider.setTickPosition(QtWidgets.QSlider.TicksBelow)
        self.slider.setTickInterval(250)

        self.slider_label = QtWidgets.QLabel("0 %")
        self.slider_label.setFixedWidth(30)
        self.slider.valueChanged.connect(self.slider_value_changed)
        self.slider.sliderPressed.connect(self.slider_pressed)
        self.slider.sliderReleased.connect(self.slider_released)

        slider_layout.addWidget(self.slider)

        layout.addLayout(button_layout)
        layout.addLayout(slider_layout)

        self.setLayout(layout)

        self.returnPressedShortcut = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Return), self)
        self.returnPressedShortcut.activated.connect(self.close)

    def update_label(self, value: int):
        self.slider_label.setText(str(value) + " %")

    def slider_pressed(self):
        self.update_pose()
        self.editing = True

    def slider_released(self):
        self.editing = False

        self.slider.blockSignals(True)
        self.slider.setValue(0)
        self.slider.blockSignals(False)

    def slider_value_changed(self, value: int):
        if not self.editing:
            return

        ratio = value / self.SLIDER_RESOLUTION

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
                                            use_translation=self.translation_toggle.isChecked(), 
                                            use_rotation=self.rotation_toggle.isChecked(), 
                                            use_scaling=self.scale_toggle.isChecked())

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
    def WidgetCreate(self, parent_cpp_ptr: int):
        self.native_widget = PoseInbetween(wrapInstance(parent_cpp_ptr, QtWidgets.QWidget))
        return getCppPointer(self.native_widget)[0]


class NativeQtWidgetTool(fb.FBTool):
    def __init__(self, name: str):
        super().__init__(name, True)
        self.native_holder = NativeWidgetHolder()
        self.BuildLayout()

        self.SetPossibleDockPosition(fb.FBToolPossibleDockPosition.kFBToolPossibleDockPosNone)

        self.StartSizeX = 400
        self.StartSizeY = 80

        cursor_pos = QtGui.QCursor.pos()
        self.StartPosX = int(cursor_pos.x() - self.StartSizeX / 2)
        self.StartPosY = cursor_pos.y() - 50

    def BuildLayout(self):
        x = fb.FBAddRegionParam(0, fb.FBAttachType.kFBAttachLeft, "")
        y = fb.FBAddRegionParam(0, fb.FBAttachType.kFBAttachTop, "")
        w = fb.FBAddRegionParam(0, fb.FBAttachType.kFBAttachRight, "")
        h = fb.FBAddRegionParam(0, fb.FBAttachType.kFBAttachBottom, "")

        region_name = "main"
        self.AddRegion(region_name, region_name, x, y, w, h)
        self.SetControl(region_name, self.native_holder)


def main():
    fb_additions.FBDestroyToolByName(TOOL_NAME)

    if TOOL_NAME in fb_additions.FBToolList:
        tool = fb_additions.FBToolList[TOOL_NAME]
    else:
        tool = NativeQtWidgetTool(TOOL_NAME)

    fb.ShowTool(tool)


if __name__ == "__main__" or "builtin" in __name__:
    main()