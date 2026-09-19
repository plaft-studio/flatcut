"""
Face Selection Module for Slice Face Operations

This module contains functions for saving, retrieving, and clearing
slice face selections from mesh objects.

Functions:
    - save_slice_face_selection: Save selected faces as slice face
    - store_slice_face: Save given face indices as slice face (no Edit Mode)
    - get_slice_plane_from_object: Retrieve saved slice plane info
    - clear_slice_face_data: Clear all slice face data from object
    - get_slice_face_indices: Retrieve saved face indices

The slice face lives in the object's custom properties only; the mesh itself
is left untouched. Use "Select Slice Face" to see which faces are saved.
"""

import bpy
import bmesh
from mathutils import Vector

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


# Highlight material used by versions that marked the slice face by recoloring
LEGACY_HIGHLIGHT_MATERIAL = "SliceFaceHighlight"


def save_slice_face_selection(obj: bpy.types.Object):
    """
    Save the currently selected faces in Edit Mode as the slice face for this object.

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

    # Collect world-space normal and center for each selected face
    face_data = []
    for face_idx in selected_faces:
        face = bm.faces[face_idx]
        world_normal = (obj.matrix_world.to_3x3() @ face.normal).normalized()
        world_center = obj.matrix_world @ face.calc_center_median()
        face_data.append((face_idx, world_normal, world_center))

    return _store_slice_face_data(obj, face_data)


def store_slice_face(obj: bpy.types.Object, face_indices: list) -> bool:
    """
    Save the given faces as the slice face for this object, reading the mesh
    data directly. Unlike save_slice_face_selection this needs no Edit Mode
    selection, so it can be driven by automatic slice face detection.

    Args:
        obj: Blender mesh object (must not be in Edit Mode)
        face_indices: Indices of the faces forming the slice face

    Returns:
        True if the slice face was saved, False otherwise
    """
    if obj.type != 'MESH':
        log.warning(f"Object {obj.name} is not a mesh, skipping")
        return False

    if obj.mode == 'EDIT':
        log.warning(f"Object {obj.name} is in Edit Mode, mesh data may be stale")
        return False

    mesh = obj.data
    face_data = []

    for face_idx in face_indices:
        if face_idx >= len(mesh.polygons):
            continue
        face = mesh.polygons[face_idx]
        world_normal = (obj.matrix_world.to_3x3() @ face.normal).normalized()
        world_center = obj.matrix_world @ face.center
        face_data.append((face_idx, world_normal, world_center))

    return _store_slice_face_data(obj, face_data)


def _store_slice_face_data(obj: bpy.types.Object, face_data: list) -> bool:
    """
    Write the slice face custom properties.

    Args:
        obj: Blender mesh object
        face_data: List of (face_index, world_normal, world_center) tuples

    Returns:
        True if the slice face was saved, False otherwise
    """
    if not face_data:
        log.warning(f"No faces to save as slice face for {obj.name}")
        return False

    # Average normal and center define the slice plane
    avg_normal = Vector((0, 0, 0))
    avg_center = Vector((0, 0, 0))

    # Also store individual face Z positions for pocket machining
    face_indices = []
    face_z_positions = []  # List of [face_index, z_position]

    for face_idx, world_normal, world_center in face_data:
        avg_normal += world_normal
        avg_center += world_center

        face_indices.append(face_idx)
        face_z_positions.append([face_idx, world_center.z])

    avg_normal = avg_normal.normalized()
    avg_center = avg_center / len(face_data)

    # Store slice plane info in object custom properties
    obj["slice_face_indices"] = face_indices
    obj["slice_plane_normal"] = [avg_normal.x, avg_normal.y, avg_normal.z]
    obj["slice_plane_point"] = [avg_center.x, avg_center.y, avg_center.z]
    obj["slice_face_z_positions"] = face_z_positions

    # Objects saved by older versions carry a highlight material slot
    remove_legacy_slice_material(obj)

    log.info(f"Saved {len(face_indices)} face(s) as slice face for {obj.name}")
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
    Clear the saved slice face data from an object.

    Args:
        obj: Blender mesh object
    """
    if obj.type != 'MESH':
        return

    # Objects saved by older versions carry a highlight material slot
    remove_legacy_slice_material(obj)

    # Remove custom properties
    for prop in ["slice_face_indices", "slice_plane_normal", "slice_plane_point", "slice_face_z_positions"]:
        if prop in obj:
            del obj[prop]

    log.info(f"Cleared slice face data for {obj.name}")


def get_slice_face_indices(obj: bpy.types.Object) -> list:
    """
    Get the saved slice face indices of an object.

    Args:
        obj: Blender mesh object

    Returns:
        List of face indices, empty if no slice face is saved
    """
    if obj.type != 'MESH' or "slice_face_indices" not in obj:
        return []

    return list(obj["slice_face_indices"])


def remove_legacy_slice_material(obj: bpy.types.Object):
    """
    Remove the highlight material slot left behind by older versions, which
    marked the slice face by recoloring its faces.

    Removing the slot remaps the remaining face material indices, so faces
    that were highlighted fall back to the object's first material.

    Args:
        obj: Blender mesh object
    """
    if obj.type != 'MESH':
        return

    mesh = obj.data
    for slot_index, material in enumerate(mesh.materials):
        if material and material.name.startswith(LEGACY_HIGHLIGHT_MATERIAL):
            mesh.materials.pop(index=slot_index)
            log.info(f"Removed legacy highlight material slot from {obj.name}")

            # Drop the datablock once the last object stops using it
            if material.users == 0:
                bpy.data.materials.remove(material)
                log.info(f"Purged unused material: {LEGACY_HIGHLIGHT_MATERIAL}")
            return
