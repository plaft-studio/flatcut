"""
Settings Module

This module contains settings classes and property groups for G-code generation.
"""

import bpy
from bpy.props import (
    FloatProperty, IntProperty, EnumProperty,
    StringProperty, BoolProperty
)


class GcodeSettings:
    """Settings for generation"""
    def __init__(self, props):
        self.machine_type = props.machine_type
        self.feed_rate_cut = props.feed_rate_cut
        self.feed_rate_plunge = props.feed_rate_plunge
        self.safe_height = props.safe_height
        self.step_down = props.step_down
        self.tool_diameter = props.tool_diameter
        self.spindle_speed = props.spindle_speed
        self.start_position = props.start_position


def update_machine_type(self, context):
    """Update related properties when machine type changes"""
    if self.machine_type == 'LASER':
        # Laser defaults
        self.tool_diameter = 0.5  # 0.5mm kerf width (minimum allowed)
        self.feed_rate_cut = 1000.0  # Laser cutting speed (mm/min)
        self.spindle_speed = 200  # Laser power (0-255 range, or percentage)
    else:  # CNC
        self.tool_diameter = 1.4
        self.feed_rate_cut = 500.0
        self.feed_rate_plunge = 100.0
        self.step_down = 0.7
        self.spindle_speed = 4000


class GcodeProperties(bpy.types.PropertyGroup):
    """Properties for G-code generation"""

    preset_name: StringProperty(
        name="Preset Name",
        description="Name for saving/loading presets",
        default=""
    )

    machine_type: EnumProperty(
        name="Machine Type",
        description="Type of CNC machine",
        items=[
            ('CNC', "CNC Mill", "CNC milling machine with Z-axis depth control"),
            ('LASER', "Laser Cutter", "Laser cutter with power control (no Z-axis depth)"),
        ],
        default='CNC',
        update=update_machine_type
    )

    output_path: StringProperty(
        name="Output Path",
        description="Directory to save G-code files",
        default="//gcode/",
        subtype='DIR_PATH'
    )

    feed_rate_cut: FloatProperty(
        name="Feed Rate (Cut)",
        description="Cutting feed rate (mm/min)",
        default=500.0,
        min=10.0,
        max=3000.0
    )

    feed_rate_plunge: FloatProperty(
        name="Feed Rate (Plunge)",
        description="Plunge feed rate (mm/min)",
        default=100.0,
        min=10.0,
        max=1000.0
    )

    safe_height: FloatProperty(
        name="Safe Height",
        description="Safe Z height for rapid moves (mm)",
        default=10.0,
        min=1.0,
        max=20.0,
        subtype='DISTANCE'
    )

    step_down: FloatProperty(
        name="Step Down",
        description="Depth of cut per pass (mm)",
        default=0.7,
        min=0.1,
        max=10.0,
        soft_min=0.3,
        soft_max=2.0,
        subtype='DISTANCE'
    )

    tool_diameter: FloatProperty(
        name="Tool Diameter",
        description="CNC: End mill diameter (mm) / Laser: Beam kerf width (mm)",
        default=1.4,
        min=0.5,
        max=30.0,
        soft_min=1.0,
        soft_max=6.0,
        subtype='DISTANCE'
    )

    spindle_speed: IntProperty(
        name="Spindle Speed",
        description="Spindle speed (RPM)",
        default=4000,
        min=100,
        max=10000
    )

    # Laser-specific properties
    laser_power: FloatProperty(
        name="Laser Power",
        description="Laser power percentage (0-100%)",
        default=80.0,
        min=0.0,
        max=100.0,
        subtype='PERCENTAGE'
    )

    laser_speed: FloatProperty(
        name="Laser Speed",
        description="Laser cutting/engraving speed (mm/min)",
        default=1000.0,
        min=100.0,
        max=5000.0
    )

    total_depth: FloatProperty(
        name="Total Depth",
        description="Total cutting depth (mm)",
        default=3.0,    # 3mm (typical plywood thickness)
        min=1.0,        # 1mm
        max=20.0,       # 20mm
        subtype='DISTANCE'
    )

    depth_extra: FloatProperty(
        name="Extra Depth",
        description="Additional depth beyond material thickness to ensure full cut-through (mm)",
        default=0.2,
        min=0.0,
        max=2.0,
        subtype='DISTANCE'
    )

    # Tab settings
    tab_enabled: BoolProperty(
        name="Enable Tabs",
        description="Leave small tabs on outer boundary to prevent part from detaching during cutting",
        default=True
    )

    tab_height: FloatProperty(
        name="Tab Height",
        description="Height of tabs from bottom of material (mm)",
        default=0.5,
        min=0.1,
        max=3.0,
        subtype='DISTANCE'
    )

    tab_width: FloatProperty(
        name="Tab Width",
        description="Width of each tab along the contour (mm)",
        default=3.0,
        min=1.0,
        max=10.0,
        subtype='DISTANCE'
    )

    tab_count: IntProperty(
        name="Tab Count",
        description="Number of tabs per outer boundary contour",
        default=3,
        min=1,
        max=10
    )

    show_gcode_section: BoolProperty(
        name="Show Section",
        description="Show/hide settings and export section",
        default=True
    )

    retract_between_passes: BoolProperty(
        name="Retract Between Passes",
        description="Retract to safe height between depth passes of the same contour. Disable for faster cutting when multiple passes on the same contour",
        default=False
    )

    pack_area_width: FloatProperty(
        name="Work Area Width",
        description="Width of the work area for packing objects (mm)",
        default=200.0,
        min=10.0,
        max=1000.0,
        subtype='DISTANCE'
    )

    pack_area_height: FloatProperty(
        name="Work Area Height",
        description="Height of the work area for packing objects (mm)",
        default=200.0,
        min=10.0,
        max=1000.0,
        subtype='DISTANCE'
    )

    start_position: EnumProperty(
        name="Start Position",
        description="Work area position used as machine origin (X0 Y0)",
        items=[
            ('FRONT_LEFT', "Front Left", "Front-left corner as origin (default)"),
            ('FRONT_RIGHT', "Front Right", "Front-right corner as origin"),
            ('BACK_LEFT', "Back Left", "Back-left corner as origin"),
            ('BACK_RIGHT', "Back Right", "Back-right corner as origin"),
            ('CENTER', "Center", "Center of work area as origin"),
        ],
        default='FRONT_LEFT',
    )

    slice_plane: EnumProperty(
        name="Slice Plane",
        description="Which plane to use for slicing the object",
        items=[
            ('XY', "XY (Bottom)", "Slice at Z=0 (bottom face)"),
            ('XZ', "XZ (Front)", "Slice at Y=0 (front face)"),
            ('YZ', "YZ (Side)", "Slice at X=0 (side face)"),
        ],
        default='XY'
    )
