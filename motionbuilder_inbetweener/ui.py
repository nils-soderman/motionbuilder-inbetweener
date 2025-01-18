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
    SETTING_ID_BLEND_CURRENT_POSE = "BlendCurrentPose"
    SETTING_ID_OVERSHOOT = "Overshoot"

    def __init__(self, parent: QtWidgets.QWidget, settings: QtCore.QSettings):
        super().__init__(parent)
        self.settings = settings

        self.setOrientation(QtCore.Qt.Horizontal)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setTickInterval(250)

        self._blend_from_current_pose = bool(self.settings.value(self.SETTING_ID_BLEND_CURRENT_POSE, True, type=bool))
        self._overshoot = self.settings.value(self.SETTING_ID_OVERSHOOT, 0.5, type=float)

        self.last_mouse_pos_x = None
        self.is_editing = False
        self.last_value = 0

        self.buttons: list[tuple[QtWidgets.QPushButton, float]] = []
        for x in (-1, -0.5, 0.5, 1):
            button = QtWidgets.QPushButton(self)
            if isinstance(x, int):
                button.setFixedSize(5, 8)
            else:
                button.setFixedSize(5, 6)
            button.setVisible(True)
            button.mousePressEvent = lambda event, x=x: self.btn_press_event(x)
            button.mouseReleaseEvent = self.mouseReleaseEvent
            self.buttons.append((button, x))

            button.setAccessibleName("sliderButton")
            button.setStyleSheet(self.styleSheet())

        self._update_min_max()

    def paintEvent(self, event: QtGui.QPaintEvent):
        super().paintEvent(event)

        if self.is_editing:
            painter = QtGui.QPainter(self)
            rect = self.rect()
            rect.adjust(10, 0, -10, 0)

            painter.setOpacity(0.5)
            value = self.value()

            if value > 0:
                align = QtCore.Qt.AlignLeft
            else:
                align = QtCore.Qt.AlignRight

            painter.drawText(rect, align, f"{value / self.SLIDER_RESOLUTION:.2f}")

    def resizeEvent(self, event: QtGui.QResizeEvent):
        self.update_button_positions()

    def update_button_positions(self):
        rect = self.rect()
        slider_range = self.maximum() - self.minimum()
        for button, x in self.buttons:
            # Check if button is within slider range
            if x * self.SLIDER_RESOLUTION <= self.minimum() or x * self.SLIDER_RESOLUTION >= self.maximum():
                button.setHidden(True)
                continue

            pos_1 = (x * self.SLIDER_RESOLUTION - self.minimum()) * rect.width() / slider_range
            pos_1 -= (x * self.SLIDER_RESOLUTION / self.maximum()) * 4

            button.move(int(pos_1 - button.width() / 2), rect.bottom() - button.height() + 2)
            button.setHidden(False)

    def btn_press_event(self, value) -> None:
        self.last_value = value * self.SLIDER_RESOLUTION
        self.setValue(self.last_value)
        self.is_editing = True

        current_mouse_pos = QtGui.QCursor().pos()
        self.last_mouse_pos_x = self.mapFromGlobal(current_mouse_pos).x()

    def _update_min_max(self):
        value = int((1 + self.overshoot) * self.SLIDER_RESOLUTION)
        self.setMinimum(-value)
        self.setMaximum(value)

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        super().mousePressEvent(event)
        if event.button() == QtCore.Qt.RightButton:
            self.show_context_menu(event.pos())
            return

        self.is_editing = True

        if event.modifiers() & QtCore.Qt.ControlModifier:
            self.snap(event)
        elif event.modifiers() & QtCore.Qt.ShiftModifier:
            if self.blend_from_current_pose:
                self.set_value_no_signal(0)
            else:
                self.setValue(0)
        else:
            self.valueChanged.emit(self.value())

        self.last_mouse_pos_x = event.pos().x()
        self.last_value = self.value()

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        self.is_editing = False
        super().mouseReleaseEvent(event)
        self.last_mouse_pos_x = None
        self.last_value = 0
        self.set_value_no_signal(0)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        if self.is_editing and self.last_mouse_pos_x is not None:
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

    def set_value_no_signal(self, value: int):
        self.blockSignals(True)
        self.setValue(value)
        self.blockSignals(False)

    def show_context_menu(self, pos):
        menu = QtWidgets.QMenu(self)

        action_blend_current = QtGui.QAction("Blend from current pose", self)
        action_blend_current.setCheckable(True)
        action_blend_current.setChecked(self.blend_from_current_pose)
        action_blend_current.triggered.connect(lambda checked: setattr(self, "blend_from_current_pose", checked))
        menu.addAction(action_blend_current)

        # Overshoot float input
        overshoot_label = QtWidgets.QLabel("Overshoot:")
        overshoot_input = QtWidgets.QDoubleSpinBox()
        overshoot_input.setValue(self.overshoot)
        overshoot_input.setSingleStep(0.1)
        overshoot_input.setMaximum(10)
        overshoot_input.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        overshoot_input.setFixedWidth(50)
        overshoot_input.editingFinished.connect(lambda: (setattr(self, "overshoot", overshoot_input.value()), menu.close()))

        overshoot_widget = QtWidgets.QWidget()
        overshoot_layout = QtWidgets.QHBoxLayout()
        overshoot_layout.setSpacing(0)
        overshoot_layout.setContentsMargins(6, 1, 0, 0)
        overshoot_layout.addWidget(overshoot_label)
        overshoot_layout.addWidget(overshoot_input)
        overshoot_widget.setLayout(overshoot_layout)

        overshoot_action = QtWidgets.QWidgetAction(self)
        overshoot_action.setDefaultWidget(overshoot_widget)
        menu.addAction(overshoot_action)

        menu.exec_(self.mapToGlobal(pos))

    @property
    def blend_from_current_pose(self) -> bool:
        return self._blend_from_current_pose

    @blend_from_current_pose.setter
    def blend_from_current_pose(self, value):
        self._blend_from_current_pose = value
        self.settings.setValue(self.SETTING_ID_BLEND_CURRENT_POSE, value)

    @property
    def overshoot(self) -> float:
        return self._overshoot

    @overshoot.setter
    def overshoot(self, value):
        self._overshoot = value
        self.settings.setValue(self.SETTING_ID_OVERSHOOT, value)
        self._update_min_max()
        self.update_button_positions()


class TRSOption(QtWidgets.QWidget):
    """
    Widget containing 3 buttons to toggle translation, rotation and scaling
    """

    def __init__(self, parent: QtWidgets.QWidget, settings: QtCore.QSettings):
        super().__init__(parent)
        self.settings = settings

        self.setFixedHeight(22)

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(4, 0, 0, 0)
        layout.setSpacing(2)

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


def sign(value):
    return 1 if value >= 0 else -1


class PoseInbetween(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget, stylesheet: str | None = None):
        super().__init__(parent)

        self.undo_manager = fb.FBUndoManager()
        self.settings = QtCore.QSettings("MotionBuilder", "InBetweener")

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
        layout.setContentsMargins(1, 1, 6, 1)

        self.trs_option = TRSOption(self, self.settings)

        self.slider = Slider(self, self.settings)

        self.slider.valueChanged.connect(self.slider_value_changed)
        self.slider.sliderPressed.connect(self.slider_pressed)
        self.slider.sliderReleased.connect(self.slider_released)

        layout.addWidget(self.trs_option)
        layout.addWidget(self.slider)

        self.setLayout(layout)

        self.returnPressedShortcut = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Return), self)
        self.returnPressedShortcut.activated.connect(self.close)

    def slider_pressed(self):
        self.update_pose()

        self.undo_manager.TransactionBegin("Inbetween Pose")
        for model in self.models:
            self.undo_manager.TransactionAddModelTRS(model)

    def slider_released(self):
        self.slider.set_value_no_signal(0)

        self.undo_manager.TransactionEnd()

    def slider_value_changed(self, value: int):
        if not self.slider.is_editing:
            return

        ratio = value / Slider.SLIDER_RESOLUTION

        if self.slider.blend_from_current_pose:
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

        elif self.prev_pose is not None and self.next_pose is not None:
            ratio = (ratio + 1) / 2

            pose_inbetween.apply_inbetween_pose(self.models,
                                                self.prev_pose,
                                                self.next_pose,
                                                ratio,
                                                use_translation=self.trs_option.translation,
                                                use_rotation=self.trs_option.rotation,
                                                use_scaling=self.trs_option.scale)

    def update_pose(self):
        self.models = pose_inbetween.get_models()

        self.current_time = fb.FBSystem().LocalTime
        self.prev_pose_time, self.next_pose_time = pose_inbetween.get_closest_keyframes(
            self.models,
            self.trs_option.translation,
            self.trs_option.rotation,
            self.trs_option.scale
        )

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
