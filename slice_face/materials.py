"""
Materials Module for Slice Face Operations

This module contains functions for creating and managing materials
used to highlight slice faces in the 3D viewport.

Functions:
    - get_or_create_slice_material: Get or create red highlight material
    - apply_slice_face_material: Apply material to specific faces
    - remove_slice_face_material: Remove material from faces
"""

import bpy

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


def get_or_create_slice_material() -> bpy.types.Material:
    """
    Get or create the red material for highlighting slice faces.

    Returns:
        Material for slice face highlighting
    """
    mat_name = "SliceFaceHighlight"

    # Check if material already exists
    if mat_name in bpy.data.materials:
        return bpy.data.materials[mat_name]

    # Create new material
    mat = bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True

    # Get the principled BSDF node
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    if bsdf:
        # Set bright red color with emission for visibility
        bsdf.inputs['Base Color'].default_value = (1.0, 0.0, 0.0, 1.0)  # Red
        bsdf.inputs['Emission Strength'].default_value = 0.3
        try:
            bsdf.inputs['Emission Color'].default_value = (1.0, 0.2, 0.2, 1.0)  # Blender 4.0+
        except KeyError:
            bsdf.inputs['Emission'].default_value = (1.0, 0.2, 0.2, 1.0)  # Blender 3.x

    log.info(f"Created slice face highlight material: {mat_name}")
    return mat


def apply_slice_face_material(obj: bpy.types.Object, face_indices: list):
    """
    Apply red material to specific faces.

    Args:
        obj: Blender mesh object
        face_indices: List of face indices to highlight
    """
    if obj.type != 'MESH':
        return

    # Store the current mode
    original_mode = obj.mode

    # Must be in Object Mode to modify materials
    if original_mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')

    # Ensure object has at least one material slot
    if len(obj.data.materials) == 0:
        # Add a default material if none exists
        default_mat = bpy.data.materials.new(name="DefaultMaterial")
        default_mat.use_nodes = True
        obj.data.materials.append(default_mat)

    # Get or create the highlight material
    slice_mat = get_or_create_slice_material()

    # Add material to object if not already present
    mat_index = -1
    for i, mat in enumerate(obj.data.materials):
        if mat and mat.name == slice_mat.name:
            mat_index = i
            break

    if mat_index == -1:
        obj.data.materials.append(slice_mat)
        mat_index = len(obj.data.materials) - 1

    # Assign material to the selected faces only
    mesh = obj.data
    for face_idx in face_indices:
        if face_idx < len(mesh.polygons):
            mesh.polygons[face_idx].material_index = mat_index

    # Switch back to original mode
    if original_mode == 'EDIT':
        bpy.ops.object.mode_set(mode='EDIT')

    log.info(f"Applied slice face material to {len(face_indices)} face(s) on {obj.name}")


def remove_slice_face_material(obj: bpy.types.Object):
    """
    Remove the slice face material from all faces, resetting to default material.

    Args:
        obj: Blender mesh object
    """
    if obj.type != 'MESH':
        return

    if "slice_face_indices" not in obj:
        return

    face_indices = obj["slice_face_indices"]

    # Store the current mode
    original_mode = obj.mode

    # Must be in Object Mode to modify materials
    if original_mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')

    # Reset faces to first material (index 0)
    mesh = obj.data
    if len(mesh.polygons) > 0:
        for face_idx in face_indices:
            if face_idx < len(mesh.polygons):
                mesh.polygons[face_idx].material_index = 0

    # Switch back to original mode
    if original_mode == 'EDIT':
        bpy.ops.object.mode_set(mode='EDIT')

    log.info(f"Removed slice face material from {len(face_indices)} face(s) on {obj.name}")
