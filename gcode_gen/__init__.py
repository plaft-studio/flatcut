"""
G-code Generation Package

This package handles G-code generation for CNC and laser cutting operations,
including settings management, toolpath generation, visualization, and export operators.
"""

from .settings import (
    GcodeSettings,
    GcodeProperties,
)

from .generator import (
    GcodeGenerator,
    LaserGcodeGenerator,
)

from .visualization import (
    arrange_objects_for_export,
    create_toolpath_visualization,
)

from .operators import (
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

__all__ = [
    # Settings
    'GcodeSettings',
    'GcodeProperties',

    # Generators
    'GcodeGenerator',
    'LaserGcodeGenerator',

    # Visualization
    'arrange_objects_for_export',
    'create_toolpath_visualization',

    # Operators
    'CAM_OT_SavePreset',
    'CAM_OT_LoadPreset',
    'CAM_OT_DeletePreset',
    'CAM_OT_Settings',
    'CAM_OT_PrepareGcodeExport',
    'CAM_OT_CompactArrangement',
    'CAM_OT_AddToolpathVisualization',
    'CAM_OT_DownloadGcode',
    'CAM_OT_ExportSVG',
    'CAM_OT_CancelGcodeExport',
]
