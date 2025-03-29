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


class DotDoubleSpinbox(QtWidgets.QDoubleSpinBox):
    """
    QDoubleSpinBox that accepts dots (.) as commas (,) for decimal separator
    """

    def validate(self, text: str, pos: int):
        text = text.replace(".", ",")
        return super().validate(text, pos)


class Slider(QtWidgets.QSlider):
    SLIDER_RESOLUTION: int = 1000
    SETTING_ID_BLEND_CURRENT_POSE = "BlendCurrentPose"
    SETTING_ID_OVERSHOOT = "Overshoot"

    COLOR_HANDLE_EDITING = "#668CB3"
    COLOR_HANDLE_OVERSHOOT = "#b38966"
    COLOR_HANDLE_DEFAULT = "#646464"

    beginEditing = QtCore.Signal()
    editingValueChanged = QtCore.Signal(float)
    endEditing = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget, settings: QtCore.QSettings):
        super().__init__(parent)
        self.settings = settings

        self.setOrientation(QtCore.Qt.Orientation.Horizontal)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setMinimum(-self.SLIDER_RESOLUTION)
        self.setMaximum(self.SLIDER_RESOLUTION)
        self.setTickInterval(int(0.25 * self.SLIDER_RESOLUTION))

        self.__inbetween_value = 0

        self.__blend_from_current_pose = bool(self.settings.value(self.SETTING_ID_BLEND_CURRENT_POSE, True, type=bool))
        self.__overshoot_allowed = bool(self.settings.value(self.SETTING_ID_OVERSHOOT, True, type=bool))

        self.__last_mouse_pos_x = None
        self.__handle_pressed = False
        self.__is_editing = False

        self.buttons: list[tuple[QtWidgets.QPushButton, float]] = []
        for x in (-0.75, -0.5, -0.25, 0.25, 0.5, 0.75):
            button = QtWidgets.QPushButton(self)

            height = 8 if abs(x) == 0.5 else 6
            button.setFixedSize(5, height)

            button.setVisible(True)
            button.setAccessibleName("sliderButton")

            button.mousePressEvent = lambda e, x=x: self.__btn_press_event(x)
            button.mouseReleaseEvent = self.mouseReleaseEvent

            self.buttons.append((button, x))

    def inbetween_value(self) -> float:
        return self.__inbetween_value

    def set_inbetween_value(self, value: float, disable_clamp=False) -> None:
        """ 
        Set the value of the slider and emit the valueChanged signal
        """

        if not disable_clamp and abs(value) > 1 and not self.overshoot_allowed:
            value = -1 if value < 0 else 1

        self.__inbetween_value = value

        self.setValue(int(value * self.SLIDER_RESOLUTION))

        if self.__is_editing:
            self.editingValueChanged.emit(self.inbetween_value())

        self.__updateHandleStyle()

    @property
    def blend_from_current_pose(self) -> bool:
        """ 
        True = Blend from the current pose towards the neighboring poses
        False = Do a absolute blend between the neighboring poses
        """
        return self.__blend_from_current_pose

    @blend_from_current_pose.setter
    def blend_from_current_pose(self, value):
        self.__blend_from_current_pose = value
        self.settings.setValue(self.SETTING_ID_BLEND_CURRENT_POSE, value)

    @property
    def overshoot_allowed(self) -> bool:
        """
        Amount of overshoot to allow when dragging the slider
        """
        return self.__overshoot_allowed

    @overshoot_allowed.setter
    def overshoot_allowed(self, value: bool):
        self.__overshoot_allowed = value
        self.settings.setValue(self.SETTING_ID_OVERSHOOT, value)

    def paintEvent(self, event: QtGui.QPaintEvent):
        super().paintEvent(event)

        # Draw the current value on the slider while editing
        if self.__is_editing:
            painter = QtGui.QPainter(self)
            rect = self.rect()
            rect.adjust(10, 0, -10, 0)

            painter.setOpacity(0.5)
            value = self.inbetween_value()

            if value > 0:
                align = QtCore.Qt.AlignmentFlag.AlignLeft
            else:
                align = QtCore.Qt.AlignmentFlag.AlignRight

            painter.drawText(rect, align, f"{value:.2f}")

    def resizeEvent(self, event: QtGui.QResizeEvent):
        self.__update_button_positions()

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        self.__last_mouse_pos_x = event.pos().x()

        # Right click context menu
        if event.button() == QtCore.Qt.MouseButton.RightButton:
            self.show_context_menu_options(event.pos())
            return

        # Double click handle to edit value with input
        handle_rect = self.get_handle_rect()
        if event.type() == QtCore.QEvent.Type.MouseButtonDblClick and event.button() == QtCore.Qt.MouseButton.LeftButton:
            if handle_rect.contains(event.pos()):
                self.show_context_menu_value_input(event.pos())
            return

        # To allow double clicking the handle without starting editing
        # `mousePressEvent` will instead be called again from `mouseMoveEvent`
        if not self.__handle_pressed and handle_rect.contains(event.pos()):
            self.__handle_pressed = True
            return

        super().mousePressEvent(event)

        self.__beginEditing()

        if event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
            self.__snap(event)
        elif event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
            if self.blend_from_current_pose:
                self.__set_value_no_signal(0)
            else:
                self.set_inbetween_value(0)
        else:
            self.set_inbetween_value(self.value() / self.SLIDER_RESOLUTION)

    def mouseReleaseEvent(self, e: QtGui.QMouseEvent):
        self.__endEditing()
        super().mouseReleaseEvent(e)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        # If the user clicked the handle, and starts dragging, call mousePressEvent again to start the editing process
        if self.__handle_pressed and not self.__is_editing:
            self.mousePressEvent(event)

        if self.__is_editing and self.__last_mouse_pos_x is not None:
            # Snap if control is pressed
            if event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
                self.__snap(event)
                self.__last_mouse_pos_x = event.pos().x()
                return

            delta = event.pos().x() - self.__last_mouse_pos_x

            # Use more precise delta if shift is pressed
            if event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
                delta *= 0.1

            self.__inbetween_value = self.__inbetween_value + (delta / self.width()) * 2
            self.set_inbetween_value(self.__inbetween_value)

            self.__last_mouse_pos_x = event.pos().x()

    def __btn_press_event(self, value: float) -> None:
        self.__is_editing = True
        self.set_inbetween_value(value)

        self.__last_mouse_pos_x = self.mapFromGlobal(QtGui.QCursor().pos()).x()

    def __updateHandleStyle(self) -> None:
        if not self.__is_editing:
            self.setStyleSheet(self.parent().styleSheet())
        elif abs(self.inbetween_value()) > 1:
            width = max(9 - (abs(self.inbetween_value()) - 1) * 3, 5)
            self.setStyleSheet(f"QSlider::handle {{ background: {self.COLOR_HANDLE_OVERSHOOT}; width: {width}px; }}")
        else:
            self.setStyleSheet(f"QSlider::handle {{ background: {self.COLOR_HANDLE_EDITING}; }}")

    def __snap(self, event: QtGui.QMouseEvent):
        target_value = (self.maximum() - self.minimum()) * event.pos().x() / self.width() + self.minimum()
        snapped_value = round(target_value / self.tickInterval()) * self.tickInterval()
        self.set_inbetween_value(snapped_value / self.SLIDER_RESOLUTION)

    def __beginEditing(self):
        self.__is_editing = True
        self.beginEditing.emit()

        self.__updateHandleStyle()

    def __endEditing(self):
        self.__is_editing = False
        self.__handle_pressed = False
        self.__last_mouse_pos_x = None
        self.__set_value_no_signal(0)
        self.__updateHandleStyle()
        self.endEditing.emit()

    def __set_value_no_signal(self, value: int):
        self.blockSignals(True)
        self.set_inbetween_value(value)
        self.blockSignals(False)

    def __update_button_positions(self):
        rect = self.rect()
        for button, x in self.buttons:
            button_center_x = (x + 1) * rect.width() / 2
            button_center_x -= x * 4

            button.move(int(button_center_x - button.width() / 2), rect.bottom() - button.height() + 2)
            button.setHidden(False)

    def get_handle_rect(self) -> QtCore.QRect:
        """ 
        Get the QRect of the slider handle
        """
        opt = QtWidgets.QStyleOptionSlider()
        self.initStyleOption(opt)
        handle_rect = self.style().subControlRect(QtWidgets.QStyle.ComplexControl.CC_Slider, opt, QtWidgets.QStyle.SubControl.SC_SliderHandle, self)
        return handle_rect

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
        action_overshoot = QtGui.QAction("Allow overshoot", self)
        action_overshoot.setCheckable(True)
        action_overshoot.setChecked(self.overshoot_allowed)
        action_overshoot.triggered.connect(lambda checked: setattr(self, "overshoot_allowed", checked))
        menu.addAction(action_overshoot)

        menu.exec_(self.mapToGlobal(pos))
        menu.deleteLater()

    def show_context_menu_value_input(self, pos: QtCore.QPoint):
        """
        Show a context menu where the user can input which value to set the slider to
        """
        menu = QtWidgets.QMenu(self)

        value_input = DotDoubleSpinbox()
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

        value_input.valueChanged.connect(lambda value: self.set_inbetween_value(value, disable_clamp=True))
        value_input.editingFinished.connect(menu.close)

        self.__beginEditing()
        menu.exec_(self.mapToGlobal(pos))
        menu.deleteLater()
        self.__endEditing()


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
            btn.setChecked(bool(self.settings.value(btn.text(), default_value, type=bool)))

            btn.clicked.connect(self.__on_button_clicked)

            layout.addWidget(btn)

        self.setLayout(layout)

    @property
    def translation(self) -> bool:
        return self.translation_btn.isChecked()

    @property
    def rotation(self) -> bool:
        return self.rotation_btn.isChecked()

    @property
    def scale(self) -> bool:
        return self.scale_btn.isChecked()

    def __on_button_clicked(self):
        modifiers = QtGui.QGuiApplication.keyboardModifiers()
        sender = self.sender()

        # If Ctrl is held, isolate the clicked button
        if modifiers == QtCore.Qt.KeyboardModifier.ControlModifier:
            for btn in (self.translation_btn, self.rotation_btn, self.scale_btn):
                btn.setChecked(btn == sender)
                self.settings.setValue(btn.text(), btn.isChecked())
        else:
            self.settings.setValue(sender.text(), sender.isChecked())


class InBetweenUI(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget, stylesheet: str | None = None):
        super().__init__(parent)

        self.undo_manager = fb.FBUndoManager()
        self.settings = QtCore.QSettings("MotionBuilder", "InBetweener")

        self.editing = False

        self.models = set()
        self.next_pose = None
        self.prev_pose = None
        self.current_pose = None

        # Initialize the UI
        layout = QtWidgets.QHBoxLayout()
        layout.setSpacing(5)
        layout.setContentsMargins(1, 1, 6, 1)

        self.trs_option = TRSOption(self, self.settings)

        self.slider = Slider(self, self.settings)

        self.slider.editingValueChanged.connect(self.apply_inbeetween)
        self.slider.beginEditing.connect(self.on_begin_editing)
        self.slider.endEditing.connect(self.on_end_editing)

        layout.addWidget(self.trs_option)
        layout.addWidget(self.slider)

        self.setLayout(layout)

        if stylesheet is None:
            with open(STYLESHEET_FILE, "r") as f:
                stylesheet = f.read()

        self.setStyleSheet(stylesheet)

    def on_begin_editing(self):
        """ 
        Call when user begins editing the slider

        Check for the nearest poses and store them, and open a undo transaction
        """
        self.cache_nearest_poses()

        self.undo_manager.TransactionBegin("Inbetween")
        for model in self.models:
            self.undo_manager.TransactionAddModelTRS(model)

    def on_end_editing(self):
        """
        Call when user is finished editing the slider

        Ends the undo transaction
        """
        self.undo_manager.TransactionEnd()

    def apply_inbeetween(self, value: int):
        """ 
        Call when the slider value changes
        """
        ratio = value

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

    def cache_nearest_poses(self):
        """ 
        Check for the nearest neighboring poses and store them
        """
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


class InBetweenWidgetHolder(fb.FBWidgetHolder):
    def __init__(self, stylesheet: str | None = None):
        super().__init__()

        self.stylesheet = stylesheet

    def WidgetCreate(self, parent_cpp_ptr: int):
        self.native_widget = InBetweenUI(wrapInstance(parent_cpp_ptr, QtWidgets.QWidget), self.stylesheet)
        return getCppPointer(self.native_widget)[0]


class InBetweenTool(fb.FBTool):
    def __init__(self, name: str, stylesheet: str | None = None):
        super().__init__(name, True)
        self.native_holder = InBetweenWidgetHolder(stylesheet)
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
        tool = InBetweenTool(TOOL_NAME, stylesheet)

    return fb.ShowTool(tool)


if __name__ == "__main__" or "builtin" in __name__:
    show_tool()
