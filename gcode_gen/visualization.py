"""
Visualization Module

This module contains functions for visualizing toolpaths and arranging objects.
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


def arrange_objects_for_export(objects: List[bpy.types.Object], spacing: float = 2.0, pack_tight: bool = False) -> List[Tuple[bpy.types.Object, Vector]]:
    """
    Arrange objects in a grid layout or tight packing layout.
    Returns a list of (object, offset_position) tuples.

    Args:
        objects: List of objects to arrange
        spacing: Spacing between objects in mm (default: 2.0mm)
        pack_tight: If True, use tight row-based packing instead of uniform grid (default: False)

    Returns:
        List of (object, offset_position) tuples where offset_position is the XY offset to apply
    """
    if not objects:
        return []

    mode = "tight packing" if pack_tight else "uniform grid"
    log.info(f"Arranging {len(objects)} objects using {mode} with {spacing}mm spacing...")

    # Calculate bounding box for each object
    object_data = []
    for obj in objects:
        # Get bounding box in world space
        bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]

        # Calculate dimensions
        min_x = min(corner.x for corner in bbox_corners)
        max_x = max(corner.x for corner in bbox_corners)
        min_y = min(corner.y for corner in bbox_corners)
        max_y = max(corner.y for corner in bbox_corners)

        width = max_x - min_x
        height = max_y - min_y

        # Store current bbox min (bottom-left corner in world space)
        current_bbox_min = Vector((min_x, min_y, 0))

        object_data.append({
            'object': obj,
            'width': width,
            'height': height,
            'current_bbox_min': current_bbox_min
        })

        log.info(f"  {obj.name}: {width:.2f}×{height:.2f}mm, bbox_min=({min_x:.2f}, {min_y:.2f})")

    arranged_objects = []

    if pack_tight:
        # Tight packing: arrange objects row by row, fitting as many as possible per row
        # Sort by height (tallest first) for better packing
        object_data.sort(key=lambda d: d['height'], reverse=True)

        max_row_width = 500.0  # Maximum width per row (mm)
        current_x = 0.0
        current_y = 0.0
        row_height = 0.0

        log.info(f"Tight packing mode: max_row_width={max_row_width}mm")

        for data in object_data:
            obj_width = data['width']
            obj_height = data['height']

            # Check if object fits in current row
            if current_x > 0 and current_x + obj_width > max_row_width:
                # Move to next row
                current_x = 0.0
                current_y += row_height + spacing
                row_height = 0.0
                log.info(f"  New row at Y={current_y:.2f}mm")

            # Place object at current position
            target_position = Vector((current_x, current_y, 0))
            offset = target_position - data['current_bbox_min']

            arranged_objects.append((data['object'], offset))
            log.info(f"  {data['object'].name} -> X={current_x:.2f}, Y={current_y:.2f}, offset=({offset.x:.2f}, {offset.y:.2f})")

            # Update current position for next object
            current_x += obj_width + spacing
            row_height = max(row_height, obj_height)

    else:
        # Uniform grid layout: arrange in rows with uniform cell sizing
        grid_cols = math.ceil(math.sqrt(len(objects)))

        # Find max dimensions for uniform cell sizing
        max_width = max(data['width'] for data in object_data)
        max_height = max(data['height'] for data in object_data)

        cell_width = max_width + spacing
        cell_height = max_height + spacing

        log.info(f"Grid: {grid_cols} columns, cell={cell_width:.2f}×{cell_height:.2f}mm")

        for idx, data in enumerate(object_data):
            row = idx // grid_cols
            col = idx % grid_cols

            # Target position (bottom-left of grid cell)
            target_x = col * cell_width
            target_y = row * cell_height
            target_position = Vector((target_x, target_y, 0))

            # Calculate offset from current position to target
            offset = target_position - data['current_bbox_min']

            arranged_objects.append((data['object'], offset))
            log.info(f"  {data['object'].name} -> ({col},{row}), offset=({offset.x:.2f}, {offset.y:.2f})")

    return arranged_objects


def create_toolpath_visualization(original_object: bpy.types.Object,
                                  compensated_contours: List[List[Tuple[float, float]]],
                                  depth: float,
                                  step_down: float,
                                  target_scene: bpy.types.Scene,
                                  offset: Vector,
                                  enable_step2: bool = False) -> bpy.types.Object:
    """
    Create toolpath visualization with original mesh and tool path meshes.

    Process:
    1. Copy original object to temp scene with slice face at Z-top, bottom at Z=0
    2. Create tool path meshes for each depth pass (offset outward by tool radius)
    3. All objects grouped in a collection

    Args:
        original_object: Original mesh object
        compensated_contours: List of tool-compensated contours (tool center path)
        depth: Total cutting depth
        step_down: Depth per cutting pass
        target_scene: Scene to add visualization
        offset: XY offset for grid arrangement
        enable_step2: If True, create toolpath meshes (Step 2)

    Returns:
        The created mesh object (transformed and positioned)
    """
    name = original_object.name
    log.info(f"Creating toolpath visualization for {name}, depth={depth:.3f}mm, offset={offset}")

    # Calculate number of passes
    num_passes = int(math.ceil(depth / step_down))

    # Create collection
    collection_name = f"{name}_Toolpath_Collection"
    if collection_name in bpy.data.collections:
        old_collection = bpy.data.collections[collection_name]
        bpy.data.collections.remove(old_collection)

    toolpath_collection = bpy.data.collections.new(collection_name)
    target_scene.collection.children.link(toolpath_collection)
    log.info(f"Created collection: {collection_name}")

    # Step 1: Create new mesh from original object's world-space geometry
    # This approach copies only mesh data, avoiding issues with inherited properties
    log.info(f"Original object transform: loc={original_object.location}, rot={original_object.rotation_euler}, scale={original_object.scale}")

    # Get world matrix to transform vertices
    world_matrix = original_object.matrix_world.copy()

    # Create new mesh data by copying and transforming original mesh
    new_mesh = bpy.data.meshes.new(f"{name}_Original_mesh")

    # Copy vertices, edges, and faces from original mesh, transforming to world space
    verts = [world_matrix @ v.co for v in original_object.data.vertices]
    edges = [[e.vertices[0], e.vertices[1]] for e in original_object.data.edges]
    faces = [[v for v in p.vertices] for p in original_object.data.polygons]

    new_mesh.from_pydata(verts, edges, faces)
    new_mesh.update()

    # Copy materials to new mesh BEFORE creating object
    for mat in original_object.data.materials:
        new_mesh.materials.append(mat)

    # Copy material assignments (face material indices)
    for i, src_poly in enumerate(original_object.data.polygons):
        if i < len(new_mesh.polygons):
            new_mesh.polygons[i].material_index = src_poly.material_index

    # Create completely new object with this mesh (no inheritance from original)
    mesh_copy = bpy.data.objects.new(f"{name}_Original", new_mesh)

    # CRITICAL: Copy slice face custom properties for Step 2 contour extraction
    # These properties are required by extract_contour_from_rotated_mesh()
    if "slice_face_indices" in original_object:
        mesh_copy["slice_face_indices"] = list(original_object["slice_face_indices"])
        log.info(f"Copied slice_face_indices: {len(mesh_copy['slice_face_indices'])} faces")

    if "slice_plane_normal" in original_object:
        mesh_copy["slice_plane_normal"] = list(original_object["slice_plane_normal"])

    if "slice_plane_point" in original_object:
        mesh_copy["slice_plane_point"] = list(original_object["slice_plane_point"])

    # NOTE: slice_face_z_positions will be recalculated AFTER rotation is applied
    # Store a flag to indicate recalculation is needed
    needs_z_recalculation = "slice_face_z_positions" in original_object

    log.info(f"Copied {len(new_mesh.materials)} materials with face assignments")

    # Set to origin with identity transforms
    mesh_copy.location = Vector((0, 0, 0))
    mesh_copy.rotation_mode = 'XYZ'  # Use Euler for cleaner display
    mesh_copy.rotation_euler = (0, 0, 0)
    mesh_copy.scale = Vector((1, 1, 1))

    # Add to collection
    toolpath_collection.objects.link(mesh_copy)

    # Update scene and ensure object is in view layer
    bpy.context.view_layer.update()
    target_scene.view_layers[0].update()

    # CRITICAL: Set origin to geometry center
    # This ensures consistent grid placement without overlapping
    # We need to set this object as active and selected for the operator to work

    # Temporarily switch to target scene to perform the operation
    original_scene = bpy.context.window.scene
    bpy.context.window.scene = target_scene

    # Store previous selection state
    previous_active = bpy.context.view_layer.objects.active
    previous_selection = [obj for obj in bpy.context.view_layer.objects if obj.select_get()]

    # Deselect all
    for obj in previous_selection:
        obj.select_set(False)

    # Select and set active
    mesh_copy.select_set(True)
    bpy.context.view_layer.objects.active = mesh_copy

    # Set origin to geometry center
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')

    # Restore previous selection
    mesh_copy.select_set(False)
    for obj in previous_selection:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = previous_active

    # Restore original scene
    bpy.context.window.scene = original_scene

    # Update scene after origin change
    target_scene.view_layers[0].update()

    log.info(f"Created new mesh object from world-space geometry (clean, no inheritance, origin at geometry center)")

    # Position mesh at grid offset with bottom at Z=0 (before rotation)
    # After Origin to Geometry, the bounding box is centered at origin
    bbox_corners_initial = [Vector(corner) for corner in mesh_copy.bound_box]
    min_z_initial = min(corner.z for corner in bbox_corners_initial)

    # Set initial position: XY at offset, Z adjusted so bottom is at Z=0
    mesh_copy.location = Vector((offset.x, offset.y, -min_z_initial))
    target_scene.view_layers[0].update()

    log.info(f"Initial position set: offset=({offset.x:.3f}, {offset.y:.3f}), bottom at Z=0 (min_z_local={min_z_initial:.3f})")

    # Get slice face normal from the object's custom properties
    from ..slice_face import get_slice_plane_from_object
    slice_plane = get_slice_plane_from_object(original_object)

    if slice_plane:
        plane_point, plane_normal = slice_plane
        log.info(f"Slice plane normal (local): {plane_normal}, point (local): {plane_point}")

        # Transform plane_normal to world space using original object's rotation
        # Since we've already baked the world transform into geometry, we need to use the
        # world-space normal for alignment calculation
        world_normal = (world_matrix.to_3x3() @ plane_normal).normalized()
        log.info(f"Slice plane normal (world): {world_normal}")

        # Calculate rotation to align slice face normal with +Z axis
        target_normal = Vector((0, 0, 1))  # +Z direction

        # Calculate rotation quaternion to align world_normal with target_normal
        # Handle the case where vectors are parallel or anti-parallel
        dot = world_normal.dot(target_normal)
        if abs(dot - 1.0) < 0.001:
            # Already aligned
            rotation = None
            log.info("Slice face already aligned with +Z")
        elif abs(dot + 1.0) < 0.001:
            # Opposite direction, rotate 180 degrees around any perpendicular axis
            # For (0,0,-1) to (0,0,1), rotate 180° around X or Y axis
            from mathutils import Quaternion
            axis = Vector((1, 0, 0)) if abs(world_normal.x) < 0.9 else Vector((0, 1, 0))
            rotation = Quaternion(axis, math.pi)  # 180 degrees = π radians
            log.info(f"Slice face opposite to +Z, rotating 180° around {axis}")
        else:
            # General case: rotate from world_normal to target_normal
            axis = world_normal.cross(target_normal).normalized()
            angle = math.acos(max(-1, min(1, dot)))
            from mathutils import Quaternion
            rotation = Quaternion(axis, angle)
            log.info(f"Rotating slice face: axis={axis}, angle={math.degrees(angle):.1f}°")

        # Apply rotation to geometry (if needed)
        if rotation:
            # Apply rotation directly to mesh geometry
            mesh_copy.data.transform(rotation.to_matrix().to_4x4())

            # Keep object rotation at identity (Euler mode)
            target_scene.view_layers[0].update()

            log.info(f"Applied rotation to geometry, object remains at identity rotation")

            # After rotation, re-adjust Z position to keep bottom at Z=0
            # Get bounding box in local space (before world transform)
            bbox_corners_local = [Vector(corner) for corner in mesh_copy.bound_box]
            min_z_local = min(corner.z for corner in bbox_corners_local)
            max_z_local = max(corner.z for corner in bbox_corners_local)
            obj_height = max_z_local - min_z_local

            # Re-position: maintain XY offset, adjust Z so bottom is at Z=0
            # The slice face (now pointing +Z) will be at the top
            mesh_copy.location = Vector((offset.x, offset.y, -min_z_local))
            target_scene.view_layers[0].update()

            # Verify final position in world space
            bbox_world = [mesh_copy.matrix_world @ Vector(corner) for corner in mesh_copy.bound_box]
            min_z_world = min(corner.z for corner in bbox_world)
            max_z_world = max(corner.z for corner in bbox_world)

            log.info(f"Re-positioned after rotation: offset=({offset.x:.3f}, {offset.y:.3f}), bottom at Z=0, slice face at top Z={obj_height:.3f}mm")
            log.info(f"  Local bbox: min_z={min_z_local:.3f}, max_z={max_z_local:.3f}")
            log.info(f"  World bbox: min_z={min_z_world:.3f}, max_z={max_z_world:.3f}")
    else:
        # Fallback: no slice plane found, keep current position (already set with bottom at Z=0)
        log.warning(f"No slice plane found for {name}, using original orientation (no rotation applied)")
        log.info(f"Position maintained at offset ({offset.x:.3f}, {offset.y:.3f}), bottom at Z=0")

    # CRITICAL: Recalculate slice_face_z_positions AFTER rotation and positioning
    # The mesh geometry has been transformed, so we need to recalculate Z positions
    if needs_z_recalculation and "slice_face_indices" in mesh_copy:
        slice_face_indices = mesh_copy["slice_face_indices"]
        new_face_z_positions = []

        # Calculate Z position for each slice face in world space
        for face_idx in slice_face_indices:
            if face_idx < len(mesh_copy.data.polygons):
                poly = mesh_copy.data.polygons[face_idx]
                # Calculate face center in local space
                center_local = Vector((0, 0, 0))
                for vert_idx in poly.vertices:
                    center_local += mesh_copy.data.vertices[vert_idx].co
                center_local /= len(poly.vertices)

                # Transform to world space
                center_world = mesh_copy.matrix_world @ center_local
                new_face_z_positions.append([face_idx, center_world.z])

        mesh_copy["slice_face_z_positions"] = new_face_z_positions
        log.info(f"Recalculated slice_face_z_positions after rotation: {len(new_face_z_positions)} positions")
        if new_face_z_positions:
            z_values = [z for _, z in new_face_z_positions]
            log.info(f"  Z range: {min(z_values):.3f} to {max(z_values):.3f}mm")

    # Update scene to apply transforms
    target_scene.view_layers[0].update()

    # Lock transformations to prevent accidental modification
    mesh_copy.lock_location = (False, False, True)  # XY free for repositioning, Z locked
    mesh_copy.lock_rotation = (True, True, False)   # XY locked, Z free for rotation adjustment
    mesh_copy.lock_scale = (True, True, True)       # All scale locked

    # Set display type to SOLID (not WIRE) to avoid showing internal edges
    mesh_copy.display_type = 'SOLID'
    mesh_copy.show_wire = False
    mesh_copy.show_all_edges = False

    log.info(f"Step 1 complete: Original object positioned at offset ({offset.x:.3f}, {offset.y:.3f}).")

    # Step 2: Create tool path visualization meshes for each depth pass
    if enable_step2:
        log.info(f"Step 2: Creating toolpath meshes...")
        for pass_num in range(num_passes):
            current_depth = min((pass_num + 1) * step_down, depth)
            z_height = depth - current_depth  # From top down

            # Color gradient: blue (shallow/top) to red (deep/bottom)
            progress = current_depth / depth
            r = progress
            g = 0.0
            b = 1.0 - progress

            # Create mesh from compensated contours at this Z height
            for contour_idx, contour in enumerate(compensated_contours):
                if len(contour) < 3:
                    continue

                # Create mesh data
                mesh_name = f"{name}_Toolpath_P{pass_num+1}_C{contour_idx}"
                mesh_data = bpy.data.meshes.new(mesh_name)

                # Contour coordinates need to be offset by the grid position
                # Add offset to each vertex
                vertices = [(x + offset.x, y + offset.y, z_height) for x, y in contour]
                edges = [(i, (i+1) % len(vertices)) for i in range(len(vertices))]

                mesh_data.from_pydata(vertices, edges, [])
                mesh_data.update()

                # Create object
                mesh_obj = bpy.data.objects.new(mesh_name, mesh_data)
                toolpath_collection.objects.link(mesh_obj)

                # Position at world origin (vertices already have offset baked in)
                mesh_obj.location = Vector((0, 0, 0))
                mesh_obj.rotation_mode = 'QUATERNION'
                mesh_obj.rotation_quaternion = (1, 0, 0, 0)

                # Lock transformations
                mesh_obj.lock_location = (True, True, True)
                mesh_obj.lock_rotation = (True, True, True)
                mesh_obj.lock_scale = (True, True, True)

                # Set material with emission shader
                mat = bpy.data.materials.new(name=f"Toolpath_Mat_P{pass_num+1}_C{contour_idx}")
                mat.use_nodes = True
                nodes = mat.node_tree.nodes
                nodes.clear()

                emission = nodes.new(type='ShaderNodeEmission')
                emission.inputs['Color'].default_value = (r, g, b, 1)
                emission.inputs['Strength'].default_value = 5.0

                output = nodes.new(type='ShaderNodeOutputMaterial')
                mat.node_tree.links.new(emission.outputs['Emission'], output.inputs['Surface'])

                mesh_obj.data.materials.append(mat)
                mesh_obj.display_type = 'WIRE'

                log.info(f"  Created toolpath mesh: pass {pass_num+1}/{num_passes}, Z={z_height:.3f}, color=({r:.2f},{g:.2f},{b:.2f})")

        log.info(f"Step 2 complete: {num_passes} toolpath passes created.")
    else:
        log.info(f"Step 2 skipped (enable_step2=False).")

    # Return the created mesh object for arrangement calculation
    return mesh_copy
