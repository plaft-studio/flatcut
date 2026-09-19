"""
Operators Module for Slice Face Operations

This module contains Blender operators for managing slice face selections
through the UI.

Operators:
    - CAM_OT_SaveSliceFace: Save selected faces as slice face
    - CAM_OT_SelectSliceFace: Select the saved slice face in Edit Mode
    - CAM_OT_ClearSliceFace: Clear saved slice face data
"""

import bpy
import bmesh

# Import face selection functions
from .face_selection import (
    save_slice_face_selection,
    clear_slice_face_data,
    get_slice_face_indices,
)

# Import logger
try:
    from .. import logger
    log = logger.get_logger()
except ImportError:
    # Fallback if logger not available
    import logging
    log = logging.getLogger(__name__)
    log.addHandler(logging.StreamHandler())
    log.setLevel(logging.INFO)


class CAM_OT_SaveSliceFace(bpy.types.Operator):
    """Save selected faces as the slice face for this object"""
    bl_idname = "cam.save_slice_face"
    bl_label = "Save Slice Face"
    bl_description = "Save the currently selected faces in Edit Mode as the slice face for this object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object

        if not obj or obj.type != 'MESH':
            self.report({'WARNING'}, "No active mesh object")
            return {'CANCELLED'}

        if obj.mode != 'EDIT':
            self.report({'WARNING'}, "Object must be in Edit Mode. Select faces first, then save.")
            return {'CANCELLED'}

        success = save_slice_face_selection(obj)

        if success:
            self.report({'INFO'}, f"Saved slice face for {obj.name}")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "No faces selected or failed to save")
            return {'CANCELLED'}


class CAM_OT_SelectSliceFace(bpy.types.Operator):
    """Select the saved slice face in Edit Mode"""
    bl_idname = "cam.select_slice_face"
    bl_label = "Select Slice Face"
    bl_description = "Enter Edit Mode and select the faces saved as the slice face"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object

        if not obj or obj.type != 'MESH':
            self.report({'WARNING'}, "No active mesh object")
            return {'CANCELLED'}

        face_indices = get_slice_face_indices(obj)

        if not face_indices:
            self.report({'WARNING'}, f"No slice face saved for {obj.name}")
            return {'CANCELLED'}

        # Face select mode makes the saved faces readable at a glance
        context.tool_settings.mesh_select_mode = (False, False, True)

        if obj.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')

        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()

        wanted = set(face_indices)
        stale = len([i for i in wanted if i >= len(bm.faces)])

        for face in bm.faces:
            face.select = face.index in wanted

        bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data)

        selected = len(wanted) - stale
        if stale:
            self.report(
                {'WARNING'},
                f"Selected {selected} face(s); {stale} saved face(s) no longer exist. "
                "Re-save the slice face."
            )
            log.warning(f"{obj.name}: {stale} saved slice face indices are out of range")
        else:
            self.report({'INFO'}, f"Selected {selected} slice face(s) on {obj.name}")

        return {'FINISHED'}


class CAM_OT_ClearSliceFace(bpy.types.Operator):
    """Clear saved slice face data"""
    bl_idname = "cam.clear_slice_face"
    bl_label = "Clear Slice Face"
    bl_description = "Clear the saved slice face data for selected objects"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']

        if not selected_objects:
            self.report({'WARNING'}, "No mesh objects selected")
            return {'CANCELLED'}

        for obj in selected_objects:
            clear_slice_face_data(obj)

        self.report({'INFO'}, f"Cleared slice face data for {len(selected_objects)} object(s)")
        return {'FINISHED'}
