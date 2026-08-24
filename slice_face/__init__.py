"""
Slice Face Management Package

Handles slice face selection, contour extraction, and related operations.
"""

from .mesh_processing import (
    extract_contour_from_slice_face,
    extract_contour_from_rotated_mesh,
    calculate_cutting_depth_from_slice_face,
    position_for_slice_plane,
    get_dimension_for_plane,
)

from .materials import (
    get_or_create_slice_material,
    apply_slice_face_material,
    remove_slice_face_material,
)

from .face_selection import (
    save_slice_face_selection,
    get_slice_plane_from_object,
    clear_slice_face_data,
)

from .operators import (
    CAM_OT_SaveSliceFace,
    CAM_OT_ClearSliceFace,
)

__all__ = [
    'extract_contour_from_slice_face',
    'extract_contour_from_rotated_mesh',
    'calculate_cutting_depth_from_slice_face',
    'position_for_slice_plane',
    'get_dimension_for_plane',
    'get_or_create_slice_material',
    'apply_slice_face_material',
    'remove_slice_face_material',
    'save_slice_face_selection',
    'get_slice_plane_from_object',
    'clear_slice_face_data',
    'CAM_OT_SaveSliceFace',
    'CAM_OT_ClearSliceFace',
]
