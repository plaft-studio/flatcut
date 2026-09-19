"""
Flatcut - Blender Extension
Main package initialization file

Public extension build: settings, Slice Face Setup, and the
fabrication export workflow, in a single panel.
Built from the craft-addon source tree by scripts/build_extension.sh, which
copies slice_face/, gcode_gen/ and logger.py alongside this package.
"""

import bpy
from bpy.props import PointerProperty

# Import logger first
from . import logger

# Import subpackages
from . import slice_face
from . import gcode_gen
from . import ui_panel

# Import specific classes for registration
from .slice_face import (
    CAM_OT_SaveSliceFace,
    CAM_OT_SelectSliceFace,
    CAM_OT_ClearSliceFace,
)

from .gcode_gen import (
    GcodeProperties,
    CAM_OT_SavePreset,
    CAM_OT_LoadPreset,
    CAM_OT_DeletePreset,
    CAM_OT_Settings,
    CAM_OT_PrepareGcodeExport,
    CAM_OT_CompactArrangement,
    CAM_OT_AddToolpathVisualization,
    CAM_OT_DownloadGcode,
    CAM_OT_ExportSVG,
    CAM_OT_CancelGcodeExport,
)

from .ui_panel import (
    CAM_PT_FabricationPanel,
)

# Get logger instance
log = logger.get_logger()


# Classes to register
classes = (
    GcodeProperties,
    CAM_OT_SaveSliceFace,
    CAM_OT_SelectSliceFace,
    CAM_OT_ClearSliceFace,
    CAM_OT_SavePreset,
    CAM_OT_LoadPreset,
    CAM_OT_DeletePreset,
    CAM_OT_Settings,
    CAM_OT_PrepareGcodeExport,
    CAM_OT_CompactArrangement,
    CAM_OT_AddToolpathVisualization,
    CAM_OT_DownloadGcode,
    CAM_OT_ExportSVG,
    CAM_OT_CancelGcodeExport,
    CAM_PT_FabricationPanel,
)


def register():
    log.info("Registering Flatcut...")

    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.gcode_properties = PointerProperty(type=GcodeProperties)

    log.info("Flatcut registered successfully")


def unregister():
    log.info("Unregistering Flatcut...")

    del bpy.types.Scene.gcode_properties

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    log.info("Flatcut unregistered")


if __name__ == "__main__":
    register()
