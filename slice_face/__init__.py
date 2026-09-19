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

from .face_selection import (
    save_slice_face_selection,
    store_slice_face,
    get_slice_plane_from_object,
    clear_slice_face_data,
    get_slice_face_indices,
    remove_legacy_slice_material,
)

from .auto_detect import (
    detect_slice_face_indices,
    auto_detect_slice_face,
)

from .operators import (
    CAM_OT_SaveSliceFace,
    CAM_OT_SelectSliceFace,
    CAM_OT_ClearSliceFace,
)

__all__ = [
    'extract_contour_from_slice_face',
    'extract_contour_from_rotated_mesh',
    'calculate_cutting_depth_from_slice_face',
    'position_for_slice_plane',
    'get_dimension_for_plane',
    'save_slice_face_selection',
    'store_slice_face',
    'get_slice_plane_from_object',
    'clear_slice_face_data',
    'get_slice_face_indices',
    'remove_legacy_slice_material',
    'detect_slice_face_indices',
    'auto_detect_slice_face',
    'CAM_OT_SaveSliceFace',
    'CAM_OT_SelectSliceFace',
    'CAM_OT_ClearSliceFace',
]
