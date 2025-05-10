from __future__ import annotations

import pyfbsdk as fb
import pyfbsdk_additions as fb_add

try:
    from PySide6 import QtWidgets
    from shiboken6 import wrapInstance, getCppPointer
except ModuleNotFoundError:
    from PySide2 import QtWidgets
    from shiboken2 import wrapInstance, getCppPointer


class InBetweenerWidgetHolder(fb.FBWidgetHolder):
    def __init__(self, stylesheet: str | None = None):
        super().__init__()
        self.stylesheet = stylesheet

    def WidgetCreate(self, parent_cpp_ptr: int):
        from motionbuilder_inbetweener.ui import InBetweenUI
        self.native_widget = InBetweenUI(wrapInstance(parent_cpp_ptr, QtWidgets.QWidget), self.stylesheet)
        return getCppPointer(self.native_widget)[0]


class InBetweenerTool(fb.FBTool):
    TOOL_NAME = "Inbetweener"

    def __init__(self, Name: str = TOOL_NAME, RegisterTool: bool | None = None, stylesheet: str | None = None):
        super().__init__(Name, RegisterTool)

        self.StartSizeX = 350
        self.StartSizeY = 60

        self.MinSizeY = 20

        region_name = "main"
        self.AddRegion(region_name,
                       region_name,
                       fb.FBAddRegionParam(0, fb.FBAttachType.kFBAttachLeft, ""),
                       fb.FBAddRegionParam(0, fb.FBAttachType.kFBAttachTop, ""),
                       fb.FBAddRegionParam(0, fb.FBAttachType.kFBAttachRight, ""),
                       fb.FBAddRegionParam(0, fb.FBAttachType.kFBAttachBottom, ""))

        self.widget_holder = InBetweenerWidgetHolder(stylesheet)
        self.SetControl(region_name, self.widget_holder)


def show_tool(stylesheet: str | None = None) -> fb.FBTool:
    if InBetweenerTool.TOOL_NAME in fb_add.FBToolList:
        tool = fb_add.FBToolList[InBetweenerTool.TOOL_NAME]
    else:
        tool = InBetweenerTool(InBetweenerTool.TOOL_NAME, True, stylesheet)
        fb_add.FBAddTool(tool)

    return fb.ShowTool(tool)


if __name__ == "__main__" or "builtin" in __name__:
    fb_add.FBDestroyToolByName(InBetweenerTool.TOOL_NAME)
    show_tool()
