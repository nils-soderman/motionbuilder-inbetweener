"""
Register the Inbetweener tool
"""

import pyfbsdk_additions as fb_add
import motionbuilder_inbetweener


def register_inbetweener():
    if motionbuilder_inbetweener.InBetweenerTool.TOOL_NAME not in fb_add.FBToolList:
        tool = motionbuilder_inbetweener.InBetweenerTool(RegisterTool=True)
        fb_add.FBAddTool(tool)


register_inbetweener()
