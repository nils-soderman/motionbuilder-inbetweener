from __future__ import annotations

"""
In-between poses
"""

import types
import typing
import dataclasses

import pyfbsdk as fb


PoseT = dict[fb.FBModel, "ModelTransform"]
VectorT = typing.TypeVar("VectorT", fb.FBVector3d, fb.FBVector4d, fb.FBSVector)

@dataclasses.dataclass
class ModelTransform:
    translation: fb.FBVector3d
    rotation: fb.FBVector3d
    quaternion: fb.FBVector4d
    scaling: fb.FBVector3d


class change_all_models_ctx:
    """ Context manager to use when changing multiple models in the scene. """
    def __enter__(self):
        fb.FBBeginChangeAllModels()

    def __exit__(self, exc_type, exc_val, exc_tb):
        fb.FBEndChangeAllModels()


class set_time_ctx:
    """ Context manager to set the time in the scene. """
    def __init__(self, time: fb.FBTime, eval: bool = False) -> types.NoneType:
        self.time = time
        self.bEval = eval

        self.current_time = fb.FBSystem().LocalTime

    def __enter__(self):
        fb.FBPlayerControl().Goto(self.time)
        if self.bEval:
            fb.FBSystem().Scene.Evaluate()

    def __exit__(self, exc_type, exc_val, exc_tb):
        fb.FBPlayerControl().Goto(self.current_time)


def lerp(a: VectorT, b: VectorT, t: float, /) -> VectorT:
    return a + (b - a) * t


def get_models() -> set[fb.FBModel]:
    """
    Get the selected objects in the scene
    """
    selected_models = fb.FBModelList()
    fb.FBGetSelectedModels(selected_models)

    selected_models = set(selected_models)

    keying_mode = fb.FBGetCharactersKeyingMode()

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
                            groups.add(parent_keying_group.GetParentKeyingGroup(j))

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


def get_closest_keyframes(models: typing.Iterable[fb.FBModel]) -> tuple[fb.FBTime, fb.FBTime]:
    """
    Get the time of the closest keyframes to the current time.
    """
    system = fb.FBSystem()
    current_time = system.LocalTime

    time_previous = system.CurrentTake.LocalTimeSpan.GetStart()
    time_next = system.CurrentTake.LocalTimeSpan.GetStop()

    for model in models:
        for prop in model.PropertyList:
            if isinstance(prop, fb.FBPropertyAnimatable) and prop.IsAnimated():
                for node in prop.GetAnimationNode().Nodes:
                    for key in node.FCurve.Keys:
                        if key.Time < current_time and key.Time > time_previous:
                            time_previous = key.Time

                        if key.Time > current_time and key.Time < time_next:
                            time_next = key.Time

    return time_previous, time_next


def get_pose(models: typing.Iterable[fb.FBModel]) -> PoseT:
    """
    Get the translation, rotation and scaling of the models
    """
    pose: PoseT = {}

    for model in models:
        matrix = fb.FBMatrix()

        translation_4d = fb.FBVector4d()
        scaling = fb.FBSVector()

        model.GetLocalTransformationMatrixWithGlobalRotationDoF(matrix)

        rotation = fb.FBVector3d()
        fb.FBMatrixToTRS(translation_4d, rotation, scaling, matrix)

        quaternion = fb.FBVector4d()
        fb.FBRotationToQuaternion(quaternion, rotation)

        translation = fb.FBVector3d(translation_4d[0], translation_4d[1], translation_4d[2])

        pose[model] = ModelTransform(translation, rotation, quaternion, fb.FBVector3d(*scaling))

    return pose


def apply_inbetween_pose(models: typing.Iterable[fb.FBModel], pose_a: PoseT, pose_b: PoseT, ratio: float, *, use_translation: bool = True, use_rotation: bool = True, use_scaling: bool = True) -> None:
    with change_all_models_ctx():
        for model in models:
            model_trs_prev = pose_a[model]
            model_trs_next = pose_b[model]

            if use_translation:
                translation = lerp(model_trs_prev.translation, model_trs_next.translation, ratio)
                model.SetVector(translation, fb.FBModelTransformationType.kModelTranslation, False)

            if use_rotation:
                if model.QuaternionInterpolate:
                    Quaternion = fb.FBVector4d()
                    fb.FBInterpolateRotation(Quaternion, model_trs_prev.quaternion, model_trs_next.quaternion, ratio)

                    Rotation = fb.FBVector3d()
                    fb.FBQuaternionToRotation(Rotation, Quaternion)

                    model.SetVector(Rotation, fb.FBModelTransformationType.kModelRotation, False)
                else:
                    Rotation = fb.FBVector3d()
                    fb.FBInterpolateRotation(Rotation, model_trs_prev.rotation, model_trs_next.rotation, ratio)
                    model.SetVector(Rotation, fb.FBModelTransformationType.kModelRotation, False)

            if use_scaling:
                scaling = lerp(model_trs_prev.scaling, model_trs_next.scaling, ratio)
                model.SetVector(scaling, fb.FBModelTransformationType.kModelScaling, False)

def apply_pose(models: typing.Iterable[fb.FBModel], pose: PoseT) -> None:
    with change_all_models_ctx():
        for model in models:
            model_trs = pose[model]

            model.SetVector(model_trs.translation, fb.FBModelTransformationType.kModelTranslation, False)
            model.SetVector(model_trs.rotation, fb.FBModelTransformationType.kModelRotation, False)
            model.SetVector(model_trs.scaling, fb.FBModelTransformationType.kModelScaling, False)