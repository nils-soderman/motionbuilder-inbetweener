from __future__ import annotations

from . import pose_inbetween

import os

import pyfbsdk as fb
import pyfbsdk_additions as fb_additions

try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from shiboken6 import wrapInstance, getCppPointer
except ModuleNotFoundError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from shiboken2 import wrapInstance, getCppPointer


TOOL_NAME = "In-betweener"

STYLESHEET_FILE = os.path.join(os.path.dirname(__file__), "style.qss")


class Slider(QtWidgets.QSlider):
    SLIDER_RESOLUTION = 1000
    SETTING_ID_BLEND_CURRENT_POSE = "BlendCurrentPose"
    SETTING_ID_OVERSHOOT = "Overshoot"

    beginEditing = QtCore.Signal()
    endEditing = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget, settings: QtCore.QSettings):
        super().__init__(parent)
        self.settings = settings

        self.setOrientation(QtCore.Qt.Orientation.Horizontal)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setTickInterval(250)

        self.__blend_from_current_pose = bool(self.settings.value(self.SETTING_ID_BLEND_CURRENT_POSE, True, type=bool))

        overshoot_value = self.settings.value(self.SETTING_ID_OVERSHOOT, 0.5, type=float)
        if isinstance(overshoot_value, float):
            self._overshoot = overshoot_value
        else:
            self.overshoot = 0.5

        self.last_mouse_pos_x = None
        self.is_editing = False
        self.last_value = 0

        self.__handle_pressed = False

        self.buttons: list[tuple[QtWidgets.QPushButton, float]] = []
        for x in (-1, -0.5, 0.5, 1):
            button = QtWidgets.QPushButton(self)

            height = 8 if isinstance(x, int) else 6
            button.setFixedSize(5, height)

            button.setVisible(True)
            button.setAccessibleName("sliderButton")
            button.setStyleSheet(self.styleSheet())

            button.mousePressEvent = lambda e, x=x: self.btn_press_event(x)
            button.mouseReleaseEvent = self.mouseReleaseEvent

            self.buttons.append((button, x))

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
                align = QtCore.Qt.AlignmentFlag.AlignLeft
            else:
                align = QtCore.Qt.AlignmentFlag.AlignRight

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

    def handle_rect(self):
        opt = QtWidgets.QStyleOptionSlider()
        self.initStyleOption(opt)
        handle_rect = self.style().subControlRect(QtWidgets.QStyle.ComplexControl.CC_Slider, opt, QtWidgets.QStyle.SubControl.SC_SliderHandle, self)
        return handle_rect

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        self.last_mouse_pos_x = event.pos().x()

        # Right click context menu
        if event.button() == QtCore.Qt.MouseButton.RightButton:
            self.show_context_menu_options(event.pos())
            return

        # Double click handle to edit value with input
        if event.type() == QtCore.QEvent.Type.MouseButtonDblClick and event.button() == QtCore.Qt.MouseButton.LeftButton:
            handle_rect = self.handle_rect()
            if handle_rect.contains(event.pos()):
                self.show_context_menu_value_input(event.pos())
            return

        # To allow double clicking the handle without starting editing
        # `mousePressEvent` will instead be called again from `mouseMoveEvent`
        handle_rect = self.handle_rect()
        if not self.__handle_pressed and handle_rect.contains(event.pos()):
            self.__handle_pressed = True
            return

        super().mousePressEvent(event)

        self.__beginEditing()

        if event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
            self.snap(event)
        elif event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
            if self.blend_from_current_pose:
                self.set_value_no_signal(0)
            else:
                self.setValue(0)
        else:
            self.valueChanged.emit(self.value())

        self.last_value = self.value()

    def mouseReleaseEvent(self, e: QtGui.QMouseEvent):
        self.__endEditing()
        super().mouseReleaseEvent(e)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        # If the user clicked the handle, and starts dragging, call mousePressEvent again to start the editing process
        if self.__handle_pressed and not self.is_editing:
            self.mousePressEvent(event)

        if self.is_editing and self.last_mouse_pos_x is not None:
            # Snap if control is pressed
            if event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
                self.snap(event)
                self.last_mouse_pos_x = event.pos().x()
                return

            delta = event.pos().x() - self.last_mouse_pos_x

            # Use more precise delta if shift is pressed
            if event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
                delta *= 0.1

            self.last_value = self.last_value + (delta / self.width()) * (self.maximum() - self.minimum())
            self.setValue(self.last_value)

            self.last_mouse_pos_x = event.pos().x()

    def snap(self, event: QtGui.QMouseEvent):
        value = (self.maximum() - self.minimum()) * event.pos().x() / self.width() + self.minimum()
        self.last_value = round(value / self.tickInterval()) * self.tickInterval()
        self.setValue(self.last_value)

    def set_value_no_signal(self, value: int):
        self.blockSignals(True)
        self.setValue(value)
        self.blockSignals(False)

    def show_context_menu_options(self, pos: QtCore.QPoint):
        """ 
        Show a context menu with options
        """
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
        overshoot_input.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        overshoot_input.setFixedWidth(50)
        overshoot_input.editingFinished.connect(lambda: (setattr(self, "overshoot", overshoot_input.value()), menu.close()))

        overshoot_layout = QtWidgets.QHBoxLayout()
        overshoot_layout.setSpacing(0)
        overshoot_layout.setContentsMargins(6, 1, 0, 0)
        overshoot_layout.addWidget(overshoot_label)
        overshoot_layout.addWidget(overshoot_input)

        overshoot_widget = QtWidgets.QWidget()
        overshoot_widget.setLayout(overshoot_layout)

        overshoot_action = QtWidgets.QWidgetAction(self)
        overshoot_action.setDefaultWidget(overshoot_widget)
        menu.addAction(overshoot_action)

        menu.exec_(self.mapToGlobal(pos))

    def show_context_menu_value_input(self, pos: QtCore.QPoint):
        """ 
        Show a context menu where the user can input which value to set the slider to
        """
        menu = QtWidgets.QMenu(self)

        value_input = QtWidgets.QDoubleSpinBox()
        value_input.setMinimum(-float("inf"))
        value_input.setMaximum(float("inf"))
        value_input.setSingleStep(0.1)
        value_input.setFixedWidth(40)
        value_input.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)

        value_layout = QtWidgets.QHBoxLayout()
        value_layout.setSpacing(0)
        value_layout.setContentsMargins(0, 0, 0, 0)
        value_layout.addWidget(value_input)

        value_widget = QtWidgets.QWidget()
        value_widget.setLayout(value_layout)

        value_action = QtWidgets.QWidgetAction(self)
        value_action.setDefaultWidget(value_widget)
        menu.addAction(value_action)

        # focus the input field
        value_input.setFocus()
        value_input.selectAll()

        value_input.editingFinished.connect(menu.close)
        value_input.valueChanged.connect(lambda value: self.setValue(value * self.SLIDER_RESOLUTION))

        self.__beginEditing()
        menu.exec_(self.mapToGlobal(pos))
        self.__endEditing()

        self.set_value_no_signal(0)

    def __beginEditing(self):
        self.is_editing = True
        self.beginEditing.emit()

    def __endEditing(self):
        self.is_editing = False
        self.__handle_pressed = False
        self.last_mouse_pos_x = None
        self.last_value = 0
        self.set_value_no_signal(0)
        self.endEditing.emit()

    @property
    def blend_from_current_pose(self) -> bool:
        return self.__blend_from_current_pose

    @blend_from_current_pose.setter
    def blend_from_current_pose(self, value):
        self.__blend_from_current_pose = value
        self.settings.setValue(self.SETTING_ID_BLEND_CURRENT_POSE, value)

    @property
    def overshoot(self) -> float:
        return self._overshoot

    @overshoot.setter
    def overshoot(self, value: float):
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
            btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
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
        if modifiers == QtCore.Qt.KeyboardModifier.ControlModifier:
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
        self.slider.beginEditing.connect(self.on_begin_editing)
        self.slider.sliderReleased.connect(self.on_end_editing)

        layout.addWidget(self.trs_option)
        layout.addWidget(self.slider)

        self.setLayout(layout)

    def on_begin_editing(self):
        self.update_stored_poses()

        self.undo_manager.TransactionBegin("Inbetween Pose")
        for model in self.models:
            self.undo_manager.TransactionAddModelTRS(model)

    def on_end_editing(self):
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

    def update_stored_poses(self):
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
