"""
UI Panel

Single UI panel for the Flatcut extension, header labeled with the addon
name/version: Settings, Slice Face Setup, then the export workflow.
"""

import tomllib
from pathlib import Path

import bpy


def _get_manifest():
    """Read blender_manifest.toml (single source of truth for name/version)."""
    manifest_path = Path(__file__).parent / "blender_manifest.toml"
    try:
        with open(manifest_path, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


class CAM_PT_FabricationPanel(bpy.types.Panel):
    """Main panel: settings, slice face setup, and export workflow"""
    bl_label = "Flatcut"
    bl_idname = "CAM_PT_fabrication"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Flatcut'
    bl_options = set()
    bl_order = 0

    def draw(self, context):
        manifest = _get_manifest()
        name = manifest.get("name", "Flatcut")
        version = manifest.get("version", "0.0.0")
        self.bl_label = f"{name} v{version}"

        obj = context.active_object
        is_edit_mode = obj is not None and obj.mode == 'EDIT'

        col = self.layout.column(align=True)

        # --- Settings ---
        subcol = col.column(align=False)
        subcol.operator("cam.gcode_settings", text="Settings", icon='SETTINGS')

        subcol.separator()

        # --- Slice Face Setup (Save requires Edit Mode on a mesh) ---
        can_save_slice_face = is_edit_mode and obj.type == 'MESH'

        subcol.label(text="Slice Face Setup:", icon='FACESEL')
        if not can_save_slice_face:
            subcol.label(text="Enter Edit Mode on a mesh to select faces", icon='EDITMODE_HLT')
        row = subcol.row()
        row.enabled = can_save_slice_face
        row.operator("cam.save_slice_face", text="Save Slice Face", icon='FILE_TICK')

        # Selecting the saved faces is how the user sees what is set, since
        # the slice face leaves no mark on the mesh itself.
        has_slice_face = obj is not None and obj.type == 'MESH' and "slice_face_indices" in obj
        row = subcol.row()
        row.enabled = has_slice_face
        row.operator("cam.select_slice_face", text="Select Slice Face", icon='RESTRICT_SELECT_OFF')

        subcol.operator("cam.clear_slice_face", text="Clear Slice Face", icon='X')

        subcol.separator()

        # --- Export Workflow ---
        is_preview_scene = "gcode_export_source_scene" in context.scene
        has_toolpaths = is_preview_scene and any(
            coll.name == "Toolpaths" and len(coll.objects) > 0
            for coll in context.scene.collection.children
        )
        # The workflow operates on Object Mode selections/scenes; Edit Mode
        # is reserved for the Slice Face Setup step above.
        can_export = not is_edit_mode

        if is_preview_scene:
            subcol.label(text="Preview Scene Active", icon='SCENE_DATA')
        subcol.label(text="Export Workflow:", icon='SORTSIZE')

        # Step 1 creates the preview scene from the source scene, so it only
        # makes sense to run while not already inside one.
        row = subcol.row()
        row.enabled = can_export and not is_preview_scene
        row.operator("cam.prepare_gcode_export", text="1. Flatten & Arrange", icon='SCENE_DATA')

        # Steps 2-4 and SVG export operate on the preview scene's arrangement.
        row = subcol.row()
        row.enabled = can_export and is_preview_scene
        row.operator("cam.compact_arrangement", text="2. Pack Objects", icon='STICKY_UVS_LOC')

        row = subcol.row()
        row.enabled = can_export and is_preview_scene
        row.operator("cam.add_toolpath_visualization", text="3. Add Toolpaths", icon='CURVE_PATH')

        row = subcol.row()
        row.enabled = can_export and has_toolpaths
        row.operator("cam.download_gcode", text="4. Download G-code", icon='EXPORT')

        row = subcol.row()
        row.enabled = can_export and is_preview_scene
        row.operator("cam.export_svg", text="Export SVG (Top View)", icon='OUTLINER_OB_CURVE')

        subcol.separator()
        row = subcol.row()
        row.enabled = can_export and is_preview_scene
        row.operator("cam.cancel_gcode_export", text="Cancel and Return", icon='BACK')
