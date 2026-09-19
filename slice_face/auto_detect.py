"""
Automatic Slice Face Detection Module

Detects the slice face of a plate-like object without a manual Edit Mode
selection. Coplanar faces are grouped into clusters and the largest cluster
is saved as the slice face, which is what a flat part cut from sheet stock
looks like: one large face plus thin side walls.

Functions:
    - detect_slice_face_indices: Find the best slice face candidate
    - auto_detect_slice_face: Detect and save the slice face
"""

import math
import bpy
from mathutils import Vector

from .face_selection import store_slice_face

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


# Faces whose normals differ by less than this are treated as parallel
NORMAL_ANGLE_TOLERANCE = math.radians(1.0)

# Faces within (bounding box diagonal * this) along the normal are coplanar
COPLANAR_TOLERANCE_RATIO = 1e-4

# Areas within this ratio of the largest one count as a tie
AREA_TIE_RATIO = 0.01

# Give up on meshes with no dominant plane (curved / organic geometry)
MAX_CLUSTERS = 500

# A candidate is only plate-like when the object is at most this fraction of
# the candidate's width thick (a cube or a chunky block is rejected)
MAX_THICKNESS_RATIO = 0.5


def _world_face_data(obj: bpy.types.Object) -> list:
    """
    Compute normal, center and area in world space for every polygon.

    Args:
        obj: Blender mesh object (must not be in Edit Mode)

    Returns:
        List with one (normal, center, area) tuple per polygon, or None for
        degenerate polygons
    """
    mesh = obj.data
    matrix = obj.matrix_world
    world_verts = [matrix @ vert.co for vert in mesh.vertices]

    face_data = []
    for poly in mesh.polygons:
        points = [world_verts[i] for i in poly.vertices]

        if len(points) < 3:
            face_data.append(None)
            continue

        # Newell's method: handles n-gons and yields twice the polygon area
        normal = Vector((0.0, 0.0, 0.0))
        for i, current in enumerate(points):
            following = points[(i + 1) % len(points)]
            normal.x += (current.y - following.y) * (current.z + following.z)
            normal.y += (current.z - following.z) * (current.x + following.x)
            normal.z += (current.x - following.x) * (current.y + following.y)

        length = normal.length
        if length == 0.0:
            face_data.append(None)
            continue

        face_data.append((normal / length, matrix @ poly.center, length / 2.0))

    return face_data


def _cluster_coplanar_faces(face_data: list, coplanar_tolerance: float):
    """
    Group faces that lie on the same plane and face the same direction.

    Faces pointing the opposite way (the other side of the plate) end up in
    their own cluster, which is what we want.

    Args:
        face_data: Output of _world_face_data
        coplanar_tolerance: Maximum distance from the cluster plane

    Returns:
        List of cluster dicts, or None if the mesh has no dominant plane
    """
    cos_tolerance = math.cos(NORMAL_ANGLE_TOLERANCE)
    clusters = []

    for face_idx, entry in enumerate(face_data):
        if entry is None:
            continue

        normal, center, area = entry

        for cluster in clusters:
            if normal.dot(cluster["normal"]) < cos_tolerance:
                continue
            if abs(cluster["normal"].dot(center - cluster["point"])) > coplanar_tolerance:
                continue

            cluster["indices"].append(face_idx)
            cluster["area"] += area
            break
        else:
            if len(clusters) >= MAX_CLUSTERS:
                return None
            clusters.append({
                "normal": normal.copy(),
                "point": center.copy(),
                "indices": [face_idx],
                "area": area,
            })

    return clusters


def detect_slice_face_indices(obj: bpy.types.Object) -> list:
    """
    Find the faces that form the largest flat surface of a plate-like object.

    Args:
        obj: Blender mesh object (must not be in Edit Mode)

    Returns:
        Sorted list of face indices, or an empty list if no candidate was found
    """
    if obj.type != 'MESH':
        log.warning(f"Object {obj.name} is not a mesh, skipping auto-detection")
        return []

    if obj.mode == 'EDIT':
        log.warning(f"Object {obj.name} is in Edit Mode, skipping auto-detection")
        return []

    mesh = obj.data
    if not mesh.polygons:
        log.warning(f"Object {obj.name} has no faces, skipping auto-detection")
        return []

    bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    bbox_min = Vector((min(c[i] for c in bbox_corners) for i in range(3)))
    bbox_max = Vector((max(c[i] for c in bbox_corners) for i in range(3)))
    coplanar_tolerance = max((bbox_max - bbox_min).length * COPLANAR_TOLERANCE_RATIO, 1e-6)

    face_data = _world_face_data(obj)
    clusters = _cluster_coplanar_faces(face_data, coplanar_tolerance)

    if clusters is None:
        log.warning(f"No dominant flat surface in {obj.name} (too many planes)")
        return []

    if not clusters:
        log.warning(f"No usable faces in {obj.name}")
        return []

    # Largest surface wins; ties go to the cluster facing up (+Z)
    largest_area = max(cluster["area"] for cluster in clusters)
    candidates = [c for c in clusters if c["area"] >= largest_area * (1.0 - AREA_TIE_RATIO)]
    best = max(candidates, key=lambda c: c["normal"].z)

    # A slice face only makes sense when the object is plate-like: the
    # thickness perpendicular to the candidate must be small next to its width
    projections = [corner.dot(best["normal"]) for corner in bbox_corners]
    thickness = max(projections) - min(projections)
    width = math.sqrt(best["area"])

    if width <= 0.0 or thickness > width * MAX_THICKNESS_RATIO:
        log.warning(
            f"{obj.name} is not plate-like "
            f"(thickness {thickness:.3f} vs. width {width:.3f}), skipping auto-detection"
        )
        return []

    log.info(
        f"Auto-detected slice face for {obj.name}: {len(best['indices'])} face(s), "
        f"normal {best['normal']}, area {best['area']:.3f}, thickness {thickness:.3f}"
    )

    return sorted(best["indices"])


def auto_detect_slice_face(obj: bpy.types.Object) -> bool:
    """
    Detect the slice face of an object and save it as if it had been selected
    manually in Edit Mode.

    Args:
        obj: Blender mesh object (must not be in Edit Mode)

    Returns:
        True if a slice face was detected and saved, False otherwise
    """
    face_indices = detect_slice_face_indices(obj)

    if not face_indices:
        return False

    return store_slice_face(obj, face_indices)
