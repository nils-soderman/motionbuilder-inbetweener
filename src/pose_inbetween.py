"""
In-between poses
"""

#pylint: disable=all

import pyfbsdk as fb
import pyfbsdk_additions as fb_additions

from PySide6 import QtWidgets, QtCore, QtGui
from shiboken6 import wrapInstance, getCppPointer


TOOL_NAME = "Inbetweener"

class change_all_models_ctx:
    def __enter__(self):
        fb.FBBeginChangeAllModels()

    def __exit__(self, exc_type, exc_val, exc_tb):
        fb.FBEndChangeAllModels()

def get_models() -> fb.FBModelList:
    """
    Get the selected objects in the scene
    """
    selected_models = fb.FBModelList()
    fb.FBGetSelectedModels(selected_models)

    selected_models = set(selected_models)

    keying_mode = fb.FBApplication().CurrentCharacter.KeyingMode

    if keying_mode != fb.FBCharacterKeyingMode.kFBCharacterKeyingSelection:
        groups = set()

        for keying_group in fb.FBSystem().Scene.KeyingGroups:
            if keying_group.IsObjectDependencySelected():
                for i in range(keying_group.GetParentKeyingGroupCount()):
                    parent_keying_group = keying_group.GetParentKeyingGroup(i)
                    if keying_mode == fb.FBCharacterKeyingMode.kFBCharacterKeyingBodyPart:
                        groups.add(parent_keying_group)
                    else:
                        for j in range(parent_keying_group.GetParentKeyingGroupCount()):
                            grand_parent_keying_group = parent_keying_group.GetParentKeyingGroup(j)
                            groups.add(grand_parent_keying_group)

        def _get_models_from_group(keying_group: fb.FBKeyingGroup):
            for i in range(keying_group.GetSubKeyingGroupCount()):
                sub_keying_group = keying_group.GetSubKeyingGroup(i)
                _get_models_from_group(sub_keying_group)

            for i in range(keying_group.GetPropertyCount()):
                prop = keying_group.GetProperty(i)
                model = prop.GetOwner()
                if isinstance(model, fb.FBModel):
                    selected_models.add(model)

        for group in groups:
            _get_models_from_group(group)

    return selected_models


def get_keyframe_time(models: fb.FBModelList):
    """
    Get the previous keyframe time of the model
    """
    time_prev = fb.FBSystem().CurrentTake.LocalTimeSpan.GetStart()
    time_next = fb.FBSystem().CurrentTake.LocalTimeSpan.GetStop()
    current_time = fb.FBSystem().LocalTime
    for model in models:
        for prop in model.PropertyList:
            if isinstance(prop, fb.FBPropertyAnimatable) and prop.IsAnimated():
                for node in prop.GetAnimationNode().Nodes:
                    for key in node.FCurve.Keys:
                        if key.Time < current_time and key.Time > time_prev:
                            time_prev = key.Time

                        if key.Time > current_time and key.Time < time_next:
                            time_next = key.Time

    return time_prev, time_next


def get_transformation_at_times(models: fb.FBModelList, prev_pose_time: fb.FBTime, next_pose_time: fb.FBTime):
    """
    Get the transformation of the model at the previous keyframe
    """
    current_time = fb.FBSystem().LocalTime

    # set time to previous keyframe
    fb.FBPlayerControl().Goto(prev_pose_time)
    fb.FBSystem().Scene.Evaluate()

    # key: model, value: translation, rotation, scaling 
    prev_pose = {}
    next_pose = {}

    for model in models:
        # Get the transformation matrix
        Matrix = fb.FBMatrix()

        Translation = fb.FBVector4d()
        Scaling = fb.FBSVector()

        model.GetLocalTransformationMatrixWithGlobalRotationDoF(Matrix)

        if model.QuaternionInterpolate:
            Rotation = fb.FBVector4d()
            fb.FBMatrixToTQS(Translation, Rotation, Scaling, Matrix)
        else:
            Rotation = fb.FBVector3d()
            fb.FBMatrixToTRS(Translation, Rotation, Scaling, Matrix)


        prev_pose[model] = (Translation, Rotation, Scaling)

    # set time to next keyframe
    fb.FBPlayerControl().Goto(next_pose_time)
    fb.FBSystem().Scene.Evaluate()

    for model in models:
        # Get the transformation matrix
        Matrix = fb.FBMatrix()

        Translation = fb.FBVector4d()
        Scaling = fb.FBSVector()

        model.GetLocalTransformationMatrixWithGlobalRotationDoF(Matrix)
        if model.QuaternionInterpolate:
            Rotation = fb.FBVector4d()
            fb.FBMatrixToTQS(Translation, Rotation, Scaling, Matrix)
        else:
            Rotation = fb.FBVector3d()
            fb.FBMatrixToTRS(Translation, Rotation, Scaling, Matrix)

        next_pose[model] = (Translation, Rotation, Scaling)

    # set time back to current time
    fb.FBPlayerControl().Goto(current_time)

    return prev_pose, next_pose


# UI

class PoseInbetween(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget):
        super(PoseInbetween, self).__init__(parent)

        self.initUI()

        self.models = get_models()
        prev_pose_time, next_pose_time = get_keyframe_time(self.models)
        self.prev_pose, self.next_pose = get_transformation_at_times(self.models, prev_pose_time, next_pose_time)

    def initUI(self):
        self.setWindowTitle("Pose Inbetween")
        self.setGeometry(100, 100, 300, 150)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
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
        self.slider.setMinimum(-20)
        self.slider.setMaximum(120)
        self.slider.setValue(50)
        self.slider.setTickPosition(QtWidgets.QSlider.TicksBelow)
        self.slider.setTickInterval(10)

        self.slider_label = QtWidgets.QLabel("50 %")
        self.slider_label.setFixedWidth(50)
        self.slider.valueChanged.connect(self.update_label)
        self.slider.valueChanged.connect(self.inbetween)

        slider_layout.addWidget(self.slider)
        slider_layout.addWidget(self.slider_label)

        layout.addLayout(button_layout)
        layout.addLayout(slider_layout)

        self.setLayout(layout)

        self.returnPressedShortcut = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Return), self)
        self.returnPressedShortcut.activated.connect(self.close)

    def update_label(self, value: int):
        self.slider_label.setText(str(value) + " %")

    def inbetween(self, value: int):
        ratio = value / 100.0

        with change_all_models_ctx():
            for model in self.models:
                # if "Effector" in model.Name:
                #     continue
                prev_pose = self.prev_pose[model]
                next_pose = self.next_pose[model]

                translation = prev_pose[0] + (next_pose[0] - prev_pose[0]) * ratio
                scaling = prev_pose[2] + (next_pose[2] - prev_pose[2]) * ratio

                Matrix = fb.FBMatrix()
                if model.QuaternionInterpolate:
                    Rotation = fb.FBVector4d()
                    fb.FBInterpolateRotation(Rotation, prev_pose[1], next_pose[1], ratio)
                    fb.FBTQSToMatrix(Matrix, translation, Rotation, scaling)
                else:
                    Rotation = fb.FBVector3d()
                    fb.FBInterpolateRotation(Rotation, prev_pose[1], next_pose[1], ratio)
                    fb.FBTRSToMatrix(Matrix, translation, Rotation, scaling)
                
                model.SetMatrix(Matrix, fb.FBModelTransformationType.kModelTransformation, False)


class NativeWidgetHolder(fb.FBWidgetHolder):
    def WidgetCreate(self, pWidgetParent: int):
        # parent = 
        self.mNativeQtWidget = PoseInbetween(wrapInstance(pWidgetParent, QtWidgets.QWidget))
        # dockWidget = self.mNativeQtWidget.parent().parent().parent()

        # dockWidget.setWindowFlags(dockWidget.windowFlags() | QtCore.Qt.FramelessWindowHint)
        # parent.parent().setWindowFlags(QtCore.Qt.FramelessWindowHint)
        # self.mNativeQtWidget.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        # self.mNativeQtWidget.parent().setAttribute(QtCore.Qt.WA_TranslucentBackground)
        # self.mNativeQtWidget.parent().parent().setAttribute(QtCore.Qt.WA_TranslucentBackground)

        # for child in dockWidget.children():
        #     if isinstance(child, QtWidgets.QWidget):
        #         # delete the close button


        return getCppPointer(self.mNativeQtWidget)[0]


class NativeQtWidgetTool(fb.FBTool):
    def __init__(self, name: str):
        super().__init__(name, True)
        self.mNativeWidgetHolder = NativeWidgetHolder()
        self.BuildLayout()

        self.SetPossibleDockPosition(fb.FBToolPossibleDockPosition.kFBToolPossibleDockPosNone)

        self.StartSizeX = 400
        self.StartSizeY = 80

        # Fetch cursor position
        cursor_pos = QtGui.QCursor.pos()

        # Move widget to cursor position
        self.StartPosX = int(cursor_pos.x() - self.StartSizeX / 2)
        self.StartPosY = cursor_pos.y() - 50

        

    def BuildLayout(self):
        x = fb.FBAddRegionParam(0,fb.FBAttachType.kFBAttachLeft,"")
        y = fb.FBAddRegionParam(0,fb.FBAttachType.kFBAttachTop,"")
        w = fb.FBAddRegionParam(0,fb.FBAttachType.kFBAttachRight,"")
        h = fb.FBAddRegionParam(0,fb.FBAttachType.kFBAttachBottom,"")
        self.AddRegion("main","main", x, y, w, h)
        self.SetControl("main", self.mNativeWidgetHolder)


fb_additions.FBDestroyToolByName(TOOL_NAME)


def main():
    if TOOL_NAME in fb_additions.FBToolList:
        tool = fb_additions.FBToolList[TOOL_NAME]
        fb.ShowTool(tool)
    else:
        tool = NativeQtWidgetTool(TOOL_NAME)
        fb.ShowTool(tool)

main()