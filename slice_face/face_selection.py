"""
Face Selection Module for Slice Face Operations

This module contains functions for saving, retrieving, and clearing
slice face selections from mesh objects.

Functions:
    - save_slice_face_selection: Save selected faces as slice face
    - get_slice_plane_from_object: Retrieve saved slice plane info
    - clear_slice_face_data: Clear all slice face data from object
"""

import bpy
import bmesh
from mathutils import Vector

# Import material functions
from .materials import apply_slice_face_material, remove_slice_face_material

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


def save_slice_face_selection(obj: bpy.types.Object):
    """
    Save the currently selected faces in Edit Mode as the slice face for this object.
    Also applies red material to highlight the slice faces.

    Args:
        obj: Blender mesh object
    """
    if obj.type != 'MESH':
        log.warning(f"Object {obj.name} is not a mesh, skipping")
        return False

    if obj.mode != 'EDIT':
        log.warning(f"Object {obj.name} is not in Edit Mode")
        return False

    # Get mesh data
    mesh = obj.data
    bm = bmesh.from_edit_mesh(mesh)

    # Find selected faces
    selected_faces = [f.index for f in bm.faces if f.select]

    if not selected_faces:
        log.warning(f"No faces selected in {obj.name}")
        return False

    # Calculate average normal and center of selected faces
    avg_normal = Vector((0, 0, 0))
    avg_center = Vector((0, 0, 0))

    # Also store individual face Z positions for pocket machining
    face_z_positions = []  # List of (face_index, z_position)

    for face_idx in selected_faces:
        face = bm.faces[face_idx]
        # Transform to world space
        world_normal = (obj.matrix_world.to_3x3() @ face.normal).normalized()
        world_center = obj.matrix_world @ face.calc_center_median()

        avg_normal += world_normal
        avg_center += world_center

        # Store Z position of this face (for pocket depth calculation)
        face_z_positions.append((face_idx, world_center.z))

    avg_normal = avg_normal.normalized()
    avg_center = avg_center / len(selected_faces)

    # Store slice plane info in object custom properties
    obj["slice_face_indices"] = selected_faces
    obj["slice_plane_normal"] = [avg_normal.x, avg_normal.y, avg_normal.z]
    obj["slice_plane_point"] = [avg_center.x, avg_center.y, avg_center.z]

    # Store individual face Z positions for pocket machining
    # Format: list of [face_index, z_position] pairs
    obj["slice_face_z_positions"] = [list(pair) for pair in face_z_positions]

    # Apply red material to highlight the slice faces
    apply_slice_face_material(obj, selected_faces)

    log.info(f"Saved {len(selected_faces)} face(s) as slice face for {obj.name}")
    log.info(f"  Normal: {avg_normal}, Center: {avg_center}")

    return True


def get_slice_plane_from_object(obj: bpy.types.Object) -> tuple:
    """
    Get the saved slice plane information from an object.

    Args:
        obj: Blender mesh object

    Returns:
        Tuple of (plane_point: Vector, plane_normal: Vector) or (None, None) if not set
    """
    if "slice_plane_point" not in obj or "slice_plane_normal" not in obj:
        return None, None

    point = Vector(obj["slice_plane_point"])
    normal = Vector(obj["slice_plane_normal"])

    return point, normal


def clear_slice_face_data(obj: bpy.types.Object):
    """
    Clear the saved slice face data from an object and remove the material highlight.

    Args:
        obj: Blender mesh object
    """
    if obj.type != 'MESH':
        return

    # Remove material highlight from faces
    remove_slice_face_material(obj)

    # Remove custom properties
    for prop in ["slice_face_indices", "slice_plane_normal", "slice_plane_point", "slice_face_z_positions"]:
        if prop in obj:
            del obj[prop]

    log.info(f"Cleared slice face data for {obj.name}")
