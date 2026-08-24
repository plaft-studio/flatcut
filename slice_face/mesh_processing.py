"""
Mesh Processing Module for Slice Face Operations

This module contains functions for extracting contours from slice faces,
calculating cutting depths, and positioning objects for CNC operations.

Functions:
    - extract_contour_from_slice_face: Extract 2D contours from saved slice face
    - calculate_cutting_depth_from_slice_face: Calculate cutting depth
    - position_for_slice_plane: Position object for slice plane
    - get_dimension_for_plane: Get dimension perpendicular to slice plane
"""

import bpy
import math
from typing import List, Tuple
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


def extract_contour_from_slice_face(obj: bpy.types.Object) -> List[List[Tuple[float, float]]]:
    """
    Extract 2D contours directly from the saved slice face vertices.
    Projects the face vertices onto a 2D plane.

    Args:
        obj: Original Blender mesh object (with saved slice face)

    Returns:
        List of contours, where each contour is a list of (x, y) points
    """
    if obj.type != 'MESH':
        log.warning(f"Object {obj.name} is not a mesh, skipping")
        return []

    # Get saved slice face data
    if "slice_face_indices" not in obj:
        log.warning(f"No slice face saved for {obj.name}")
        return []

    face_indices = obj["slice_face_indices"]
    plane_normal = Vector(obj["slice_plane_normal"])
    plane_point = Vector(obj["slice_plane_point"])

    log.info(f"Extracting contour from saved slice face for {obj.name}")
    log.info(f"  {len(face_indices)} saved face(s)")
    log.info(f"  Plane normal: {plane_normal}")
    log.info(f"  Plane point: {plane_point}")

    # Get mesh data
    mesh = obj.data

    # Collect all edges that form the boundary of selected faces
    # An edge is a boundary edge if it belongs to exactly one selected face
    edge_face_count = {}

    for face_idx in face_indices:
        if face_idx >= len(mesh.polygons):
            continue
        face = mesh.polygons[face_idx]
        for edge_key in face.edge_keys:
            # Sort edge key for consistency
            edge_key = tuple(sorted(edge_key))
            edge_face_count[edge_key] = edge_face_count.get(edge_key, 0) + 1

    # Find boundary edges (edges with count == 1)
    boundary_edges = [edge for edge, count in edge_face_count.items() if count == 1]

    log.info(f"  Found {len(boundary_edges)} boundary edges")

    if not boundary_edges:
        log.warning(f"No boundary edges found for {obj.name}")
        return []

    # Build vertex connectivity map
    vertex_to_edges = {}
    for edge in boundary_edges:
        for vert_idx in edge:
            if vert_idx not in vertex_to_edges:
                vertex_to_edges[vert_idx] = []
            vertex_to_edges[vert_idx].append(edge)

    # Build contours by following connected edges
    contours = []
    used_edges = set()

    for start_edge in boundary_edges:
        if start_edge in used_edges:
            continue

        # Build a contour starting from this edge
        contour_vertices = []
        current_edge = start_edge
        current_vert = start_edge[0]

        # Add starting vertex
        contour_vertices.append(current_vert)

        while current_edge and current_edge not in used_edges:
            used_edges.add(current_edge)

            # Find the next vertex
            next_vert = current_edge[1] if current_edge[0] == current_vert else current_edge[0]
            contour_vertices.append(next_vert)

            # Find next edge connected to next_vert
            next_edge = None
            if next_vert in vertex_to_edges:
                for edge in vertex_to_edges[next_vert]:
                    if edge != current_edge and edge not in used_edges:
                        next_edge = edge
                        current_vert = next_vert
                        break

            current_edge = next_edge

        if len(contour_vertices) > 2:
            log.info(f"  Found contour with {len(contour_vertices)} vertices")

            # Convert 3D vertices to 2D by projecting onto plane
            # Create coordinate system on the plane
            # Z-axis is the plane normal
            z_axis = plane_normal.normalized()

            # Find an arbitrary perpendicular vector for X-axis
            if abs(z_axis.z) < 0.9:
                x_axis = z_axis.cross(Vector((0, 0, 1))).normalized()
            else:
                x_axis = z_axis.cross(Vector((1, 0, 0))).normalized()

            # Y-axis is perpendicular to both
            y_axis = z_axis.cross(x_axis).normalized()

            log.info(f"  Projection basis: X={x_axis}, Y={y_axis}, Z={z_axis}")

            # Project vertices onto 2D plane
            contour_2d = []
            for vert_idx in contour_vertices:
                # Get vertex in world space
                vert_world = obj.matrix_world @ mesh.vertices[vert_idx].co

                # Vector from plane point to vertex
                rel_vec = vert_world - plane_point

                # Project onto X and Y axes
                x = rel_vec.dot(x_axis)
                y = rel_vec.dot(y_axis)

                contour_2d.append((x, y))

            log.info(f"  Projected contour to 2D: {len(contour_2d)} points")
            contours.append(contour_2d)

    log.info(f"Extracted {len(contours)} contour(s) from slice face")
    return contours


def calculate_cutting_depth_from_slice_face(obj: bpy.types.Object) -> float:
    """
    Calculate cutting depth based on the saved slice face.
    Uses the object's dimension perpendicular to the slice plane.

    Args:
        obj: Blender mesh object (with saved slice face)

    Returns:
        Cutting depth in mm
    """
    if "slice_plane_normal" not in obj:
        log.warning(f"No slice face saved for {obj.name}")
        return 0.0

    plane_normal = Vector(obj["slice_plane_normal"])

    # Get bounding box diagonal
    bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]

    # Find the maximum extent along the normal direction
    # This represents the thickness of the object perpendicular to the slice face
    projections = [corner.dot(plane_normal) for corner in bbox_corners]
    depth = max(projections) - min(projections)

    log.info(f"Calculated cutting depth for {obj.name}: {depth:.3f}mm")
    return depth




def position_for_slice_plane(obj: bpy.types.Object, plane: str):
    """
    Position object so the selected plane face is at the appropriate zero position.
    Also rotates the object so the cutting plane is at Z=0 for CNC.

    Args:
        obj: Blender mesh object
        plane: Plane to position for ('XY', 'XZ', or 'YZ')
    """
    # Get bounding box in world space
    bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]

    if plane == 'XY':
        # Bottom face at Z=0, no rotation needed
        min_z = min(corner.z for corner in bbox_corners)
        obj.location.z -= min_z
        log.info(f"Positioned {obj.name} for XY slice (bottom at Z=0)")

    elif plane == 'XZ':
        # Front face at Y=0, rotate 90° around X axis to bring XZ plane to XY
        min_y = min(corner.y for corner in bbox_corners)
        obj.location.y -= min_y
        # Rotate so XZ plane becomes XY (rotate -90° around X)
        obj.rotation_euler.x += math.radians(-90)
        obj.location.z = 0  # Reset Z after rotation
        log.info(f"Positioned {obj.name} for XZ slice (front at Y=0, rotated to XY)")

    else:  # YZ
        # Side face at X=0, rotate 90° around Y axis to bring YZ plane to XY
        min_x = min(corner.x for corner in bbox_corners)
        obj.location.x -= min_x
        # Rotate so YZ plane becomes XY (rotate 90° around Y)
        obj.rotation_euler.y += math.radians(90)
        obj.location.z = 0  # Reset Z after rotation
        log.info(f"Positioned {obj.name} for YZ slice (side at X=0, rotated to XY)")


def get_dimension_for_plane(obj: bpy.types.Object, plane: str) -> float:
    """
    Get the dimension perpendicular to the slice plane (cutting depth).

    Args:
        obj: Blender mesh object
        plane: Plane being sliced ('XY', 'XZ', or 'YZ')

    Returns:
        The dimension perpendicular to the plane (cutting depth in mm)
    """
    if plane == 'XY':
        return obj.dimensions.z
    elif plane == 'XZ':
        return obj.dimensions.y
    else:  # YZ
        return obj.dimensions.x


def extract_contour_from_rotated_mesh(mesh_obj: bpy.types.Object) -> List[List[Tuple[float, float]]]:
    """
    Extract 2D contours from rotated mesh by directly reading slice face edge vertices.
    This function is for Step 2 where the mesh has been rotated and geometry has been applied.

    Unlike extract_contour_from_slice_face which projects vertices, this function
    directly reads the XY coordinates of slice face vertices, assuming the slice face
    is already aligned with the +Z axis.

    Args:
        mesh_obj: Rotated mesh object (with rotation applied to geometry)

    Returns:
        List of contours, where each contour is a list of (x, y) points in local space
    """
    if mesh_obj.type != 'MESH':
        log.warning(f"Object {mesh_obj.name} is not a mesh, skipping")
        return []

    # Get mesh data
    mesh = mesh_obj.data

    # Strategy: For rotated meshes, find faces at the top Z level (slice face should be at top)
    # This is more reliable than using saved face indices after geometry transformation

    # Get all face centers in world space
    world_matrix = mesh_obj.matrix_world
    face_centers = []
    for face in mesh.polygons:
        center = sum((world_matrix @ mesh.vertices[v].co for v in face.vertices), Vector((0, 0, 0))) / len(face.vertices)
        face_centers.append((face.index, center.z))

    if not face_centers:
        log.warning(f"No faces found in mesh {mesh_obj.name}")
        return []

    # Find maximum Z coordinate
    max_z = max(z for _, z in face_centers)
    z_tolerance = 0.1  # 0.1mm tolerance (handles Boolean operation vertex drift)

    # Find all faces at the top Z level (these should be the slice face)
    top_face_indices = [idx for idx, z in face_centers if abs(z - max_z) < z_tolerance]

    log.info(f"Extracting contour from rotated mesh {mesh_obj.name}")
    log.info(f"  Found {len(top_face_indices)} face(s) at top Z={max_z:.3f}mm")
    log.info(f"  Total faces in mesh: {len(mesh.polygons)}")

    if not top_face_indices:
        log.warning(f"No faces found at top Z level")
        return []

    # Use top faces instead of saved_face_indices
    saved_faces_set = set(top_face_indices)
    edge_count_in_saved_faces = {}

    for face in mesh.polygons:
        if face.index in saved_faces_set:
            for edge_key in face.edge_keys:
                edge_count_in_saved_faces[edge_key] = edge_count_in_saved_faces.get(edge_key, 0) + 1

    # Boundary edges are edges that belong to only ONE saved face
    # (These form the perimeter of the slice face selection)
    boundary_edges = [edge_key for edge_key, count in edge_count_in_saved_faces.items() if count == 1]

    log.info(f"  Found {len(boundary_edges)} boundary edges")

    if not boundary_edges:
        log.warning(f"No boundary edges found for {mesh_obj.name}")
        return []

    # Build contours from boundary edges
    contours = []
    remaining_edges = set(boundary_edges)

    while remaining_edges:
        # Start a new contour
        contour = []
        edge = remaining_edges.pop()
        current_v = edge[0]
        next_v = edge[1]

        contour.append(current_v)
        contour.append(next_v)

        # Follow edges to build contour
        while True:
            # Find next edge that shares next_v
            found = False
            for e in list(remaining_edges):
                if e[0] == next_v:
                    contour.append(e[1])
                    next_v = e[1]
                    remaining_edges.remove(e)
                    found = True
                    break
                elif e[1] == next_v:
                    contour.append(e[0])
                    next_v = e[0]
                    remaining_edges.remove(e)
                    found = True
                    break

            if not found:
                # Contour complete or disconnected
                break

            # Check if we've closed the loop
            if next_v == contour[0]:
                contour.pop()  # Remove duplicate vertex
                break

        # Convert vertex indices to XY coordinates
        # Since the mesh is rotated and slice face points +Z, we can directly use XY
        contour_2d = []
        for v_idx in contour:
            vert = mesh.vertices[v_idx]
            # Use world space coordinates (object's matrix_world is applied)
            world_co = mesh_obj.matrix_world @ vert.co
            # Extract XY coordinates only (Z is ignored for 2D contour)
            contour_2d.append((world_co.x, world_co.y))

        if len(contour_2d) >= 3:
            contours.append(contour_2d)
            log.info(f"  Found contour with {len(contour_2d)} vertices")

    log.info(f"Extracted {len(contours)} contour(s) from rotated mesh")
    return contours
