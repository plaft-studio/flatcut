"""
G-code Operators Module

This module contains Blender operators for G-code generation and export.
"""

import bpy
import math
from bpy.props import StringProperty
from bpy_extras.io_utils import ExportHelper
from mathutils import Vector

from .settings import GcodeSettings
from .generator import GcodeGenerator
from .visualization import arrange_objects_for_export, create_toolpath_visualization
from ..slice_face import extract_contour_from_slice_face, calculate_cutting_depth_from_slice_face
from ..slice_face.mesh_processing import extract_contour_from_rotated_mesh

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


def get_source_gcode_properties(scene):
    """
    Get gcode_properties from the source (original) scene.
    If in a preview scene, follows the reference back to the original.
    This ensures settings are always read/written on one scene.
    """
    source_name = scene.get("gcode_export_source_scene")
    if source_name and source_name in bpy.data.scenes:
        return bpy.data.scenes[source_name].gcode_properties
    return scene.gcode_properties


class CAM_OT_SavePreset(bpy.types.Operator):
    """Save current settings as a named preset"""
    bl_idname = "cam.save_gcode_preset"
    bl_label = "Save Preset"

    def execute(self, context):
        from .presets import save_preset
        gcode_props = get_source_gcode_properties(context.scene)
        name = gcode_props.preset_name.strip()

        if not name:
            self.report({'ERROR'}, "Enter a preset name")
            return {'CANCELLED'}

        save_preset(name, gcode_props)
        self.report({'INFO'}, f"Saved preset: {name}")
        return {'FINISHED'}


class CAM_OT_LoadPreset(bpy.types.Operator):
    """Load a saved settings preset"""
    bl_idname = "cam.load_gcode_preset"
    bl_label = "Load Preset"

    preset_name: StringProperty()

    def execute(self, context):
        from .presets import load_preset
        gcode_props = get_source_gcode_properties(context.scene)

        if load_preset(self.preset_name, gcode_props):
            gcode_props.preset_name = self.preset_name
            self.report({'INFO'}, f"Loaded preset: {self.preset_name}")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, f"Preset not found: {self.preset_name}")
            return {'CANCELLED'}


class CAM_OT_DeletePreset(bpy.types.Operator):
    """Delete a saved settings preset"""
    bl_idname = "cam.delete_gcode_preset"
    bl_label = "Delete Preset"

    preset_name: StringProperty()

    def execute(self, context):
        from .presets import delete_preset

        if delete_preset(self.preset_name):
            gcode_props = get_source_gcode_properties(context.scene)
            if gcode_props.preset_name == self.preset_name:
                gcode_props.preset_name = ""
            self.report({'INFO'}, f"Deleted preset: {self.preset_name}")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, f"Preset not found: {self.preset_name}")
            return {'CANCELLED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)


class CAM_OT_Settings(bpy.types.Operator):
    """Open Settings dialog"""
    bl_idname = "cam.gcode_settings"
    bl_label = "Settings"
    bl_options = {'REGISTER'}

    def execute(self, _context):
        return {'FINISHED'}

    def invoke(self, context, _event):
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        layout = self.layout
        gcode_props = get_source_gcode_properties(context.scene)
        is_laser = (gcode_props.machine_type == 'LASER')

        # Machine Type Selection (at top)
        layout.label(text="Machine Configuration", icon='SETTINGS')
        box = layout.box()
        box.prop(gcode_props, "machine_type")

        if is_laser:
            box.label(text="Laser Mode: spindle_speed = laser power", icon='INFO')
            box.label(text="step_down is ignored (single pass)", icon='INFO')
        else:
            box.label(text="CNC Mode: spindle_speed = RPM", icon='INFO')
            box.label(text="step_down = depth per pass", icon='INFO')

        layout.separator()

        # Presets
        from .presets import list_presets
        presets = list_presets()

        layout.label(text="Presets", icon='PRESET')
        box = layout.box()
        row = box.row(align=True)
        row.prop(gcode_props, "preset_name", text="")
        row.operator("cam.save_gcode_preset", text="", icon='FILE_TICK')

        if presets:
            for preset in presets:
                row = box.row(align=True)
                op = row.operator("cam.load_gcode_preset", text=preset, icon='PRESET')
                op.preset_name = preset
                op = row.operator("cam.delete_gcode_preset", text="", icon='X')
                op.preset_name = preset

        layout.separator()
        layout.label(text="Tool Settings", icon='TOOL_SETTINGS')
        box = layout.box()

        if is_laser:
            box.prop(gcode_props, "tool_diameter", text="Beam Kerf Width (mm)")
            box.label(text="Typical: 0.1-0.3mm (test & adjust)", icon='INFO')
            box.prop(gcode_props, "spindle_speed", text="Laser Power (0-255 or %)")
        else:
            box.prop(gcode_props, "tool_diameter")
            box.prop(gcode_props, "spindle_speed")

        layout.separator()
        layout.label(text="Feed Rates", icon='DRIVER')
        box = layout.box()
        if is_laser:
            box.prop(gcode_props, "laser_speed")
        else:
            box.prop(gcode_props, "feed_rate_cut")

        # Mill Settings (CNC only)
        if not is_laser:
            layout.separator()
            layout.label(text="Mill Settings", icon='MOD_BOOLEAN')
            box = layout.box()
            box.prop(gcode_props, "step_down")
            box.prop(gcode_props, "feed_rate_plunge")
            box.prop(gcode_props, "safe_height")
            box.prop(gcode_props, "depth_extra")
            box.prop(gcode_props, "retract_between_passes")

            box.separator()
            box.label(text="Tabs", icon='MOD_SOLIDIFY')
            box.prop(gcode_props, "tab_enabled")
            if gcode_props.tab_enabled:
                box.prop(gcode_props, "tab_count")
                box.prop(gcode_props, "tab_width")
                box.prop(gcode_props, "tab_height")

        layout.separator()
        layout.label(text="Packing", icon='STICKY_UVS_LOC')
        box = layout.box()
        box.prop(gcode_props, "pack_area_width")
        box.prop(gcode_props, "pack_area_height")
        box.separator()
        box.label(text="Start Position (G-code X0 Y0)", icon='OBJECT_ORIGIN')
        box.prop(gcode_props, "start_position")


class CAM_OT_PrepareGcodeExport(bpy.types.Operator):
    """Step 1: Flatten and arrange objects for fabrication"""
    bl_idname = "cam.prepare_gcode_export"
    bl_label = "Step 1: Flatten & Arrange"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        gcode_props = get_source_gcode_properties(context.scene)

        # Get selected mesh objects, or all mesh objects with slice face if none selected
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']

        if not selected_objects:
            # No selection: use all mesh objects in scene that have slice face saved
            log.info("No objects selected. Searching for all mesh objects with slice face...")
            from .generator import has_slice_face_data
            all_mesh_objects = [obj for obj in context.scene.objects if obj.type == 'MESH']
            selected_objects = [obj for obj in all_mesh_objects if has_slice_face_data(obj)]

            if not selected_objects:
                self.report({'ERROR'}, "No mesh objects with slice face found in scene")
                log.error("No mesh objects with slice face data found")
                return {'CANCELLED'}

            log.info(f"Found {len(selected_objects)} mesh objects with slice face")
        else:
            log.info(f"Using {len(selected_objects)} selected mesh objects")

        log.info(f"Step 1: Preparing preview scene for {len(selected_objects)} object(s)...")

        # Create temporary scene for visualization
        temp_scene = bpy.data.scenes.new("GcodeExportPreview")
        log.info(f"Created temporary scene: {temp_scene.name}")

        # Copy unit scale from source scene
        temp_scene.unit_settings.scale_length = context.scene.unit_settings.scale_length
        temp_scene.unit_settings.length_unit = context.scene.unit_settings.length_unit
        log.info(f"Copied unit scale: {temp_scene.unit_settings.scale_length} ({temp_scene.unit_settings.length_unit})")

        # Store source scene name so preview scene can reference its settings
        temp_scene["gcode_export_source_scene"] = context.scene.name
        temp_scene["gcode_export_objects"] = [obj.name for obj in selected_objects]

        # Phase 1: Create and transform all objects, record their final sizes
        log.info("Phase 1: Creating and transforming objects...")
        created_objects = []  # List of (original_obj, mesh_copy, contours, depth) tuples

        for obj in selected_objects:
            log.info(f"Processing object: {obj.name}")

            # Extract contours directly from saved slice face
            contours = extract_contour_from_slice_face(obj)

            if not contours:
                self.report({'WARNING'}, f"No slice face saved for {obj.name}. Skipping.")
                log.warning(f"Skipping {obj.name}: no slice face or failed to extract contours")
                continue

            # Calculate cutting depth
            depth = calculate_cutting_depth_from_slice_face(obj)

            # Apply tool compensation to contours (for visualization)
            from .generator import compensate_contours
            tool_radius = gcode_props.tool_diameter / 2.0
            compensated_contours = compensate_contours(contours, tool_radius)

            # Create and transform object (at origin for now), returns the created mesh object
            mesh_copy = create_toolpath_visualization(
                original_object=obj,
                compensated_contours=compensated_contours,
                depth=depth,
                step_down=gcode_props.step_down,
                target_scene=temp_scene,
                offset=Vector((0, 0, 0)),  # Temporary position at origin
                enable_step2=False  # Don't create toolpath meshes yet
            )

            created_objects.append((obj, mesh_copy, compensated_contours, depth))

        # Phase 2: Calculate grid arrangement based on actual final sizes
        log.info("Phase 2: Calculating grid arrangement based on final sizes...")
        arranged_objects = arrange_objects_for_export(
            [mesh_copy for _, mesh_copy, _, _ in created_objects],
            spacing=2.0
        )

        # Store arranged objects data for Step 2
        # Store: (original_object_name, created_mesh_name, offset)
        arranged_data = []
        for (original_obj, mesh_copy, _, _), (_, offset) in zip(created_objects, arranged_objects):
            arranged_data.append((original_obj.name, mesh_copy.name, (offset.x, offset.y, offset.z)))
        temp_scene["gcode_arranged_objects"] = arranged_data

        # Phase 3: Apply final positions
        log.info("Phase 3: Applying final positions...")
        for (original_obj, mesh_copy, compensated_contours, depth), (_, offset) in zip(created_objects, arranged_objects):
            log.info(f"Repositioning {mesh_copy.name} with offset {offset}")

            # Apply offset to current location (offset is a delta, not absolute position)
            # Maintain Z (already at bottom=0), update XY by adding offset
            current_loc = mesh_copy.location.copy()
            mesh_copy.location = Vector((current_loc.x + offset.x, current_loc.y + offset.y, current_loc.z))

            log.info(f"  Previous location: ({current_loc.x:.3f}, {current_loc.y:.3f}, {current_loc.z:.3f})")
            log.info(f"  New location: ({mesh_copy.location.x:.3f}, {mesh_copy.location.y:.3f}, {mesh_copy.location.z:.3f})")

        # Switch to temporary scene
        context.window.scene = temp_scene

        # Set view to top-down (Z axis) and frame all objects
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        override = context.copy()
                        override['area'] = area
                        override['region'] = region
                        # Set top view (numpad 7)
                        area.spaces[0].region_3d.view_perspective = 'ORTHO'
                        area.spaces[0].region_3d.view_rotation = (1, 0, 0, 0)  # Top-down quaternion
                        # Frame all objects (Home)
                        with context.temp_override(**override):
                            bpy.ops.view3d.view_all()
                        break
                break

        log.info(f"Step 1 complete: Created preview scene with {len(created_objects)} objects")
        self.report({'INFO'}, f"Step 1 complete. {len(created_objects)} objects arranged. Use Step 2 to pack tighter.")
        return {'FINISHED'}


class CAM_OT_CompactArrangement(bpy.types.Operator):
    """Step 2: Compact object arrangement by removing wasted space"""
    bl_idname = "cam.compact_arrangement"
    bl_label = "Step 2: Pack Objects"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene

        log.info(f"Step 2: Starting compact arrangement...")

        # Check if we're in the preview scene
        if "gcode_export_source_scene" not in scene:
            self.report({'ERROR'}, "Not in preview scene. Run Step 1 first.")
            return {'CANCELLED'}

        # Find all mesh objects with '_Original' suffix
        mesh_objects = [obj for obj in scene.objects if obj.type == 'MESH' and '_Original' in obj.name]

        if not mesh_objects:
            self.report({'ERROR'}, "No objects found to arrange")
            return {'CANCELLED'}

        gcode_props = get_source_gcode_properties(scene)
        padding = 2.0
        spacing = 2.0
        area_w = gcode_props.pack_area_width - padding * 2
        area_h = gcode_props.pack_area_height - padding * 2

        log.info(f"  Work area: {gcode_props.pack_area_width:.0f}x{gcode_props.pack_area_height:.0f}mm (packing area: {area_w:.0f}x{area_h:.0f}mm with {padding}mm padding)")

        import mathutils

        # Phase 1: Restore original geometry if re-running, then find best rotation
        items = []
        for idx, obj in enumerate(mesh_objects):
            # Restore original geometry if saved (from previous pack run)
            if "_pack_original_verts" in obj:
                import json
                orig_verts = json.loads(obj["_pack_original_verts"])
                for vi, v in enumerate(obj.data.vertices):
                    v.co = Vector(orig_verts[vi])
                obj.data.update()
                # Reset location to saved original
                orig_loc = json.loads(obj["_pack_original_location"])
                obj.location = Vector(orig_loc)
                bpy.context.view_layer.update()

            # Save original geometry and location before any modification
            import json
            obj["_pack_original_verts"] = json.dumps([list(v.co) for v in obj.data.vertices])
            obj["_pack_original_location"] = json.dumps(list(obj.location))

            # Find best rotation by testing angles and measuring Y-extent from mesh vertices
            best_angle = 0
            best_height = float('inf')
            best_width = 0

            # Get vertices in world space
            world_verts = [obj.matrix_world @ v.co for v in obj.data.vertices]

            for angle_deg in range(0, 180, 5):  # 5-degree steps for accuracy
                angle_rad = math.radians(angle_deg)
                cos_a = math.cos(angle_rad)
                sin_a = math.sin(angle_rad)

                # Rotate vertices around centroid
                cx = sum(v.x for v in world_verts) / len(world_verts)
                cy = sum(v.y for v in world_verts) / len(world_verts)

                ys = []
                xs = []
                for v in world_verts:
                    dx, dy = v.x - cx, v.y - cy
                    rx = dx * cos_a - dy * sin_a
                    ry = dx * sin_a + dy * cos_a
                    xs.append(rx)
                    ys.append(ry)

                h = max(ys) - min(ys)
                w = max(xs) - min(xs)

                if h < best_height - 0.01:
                    best_height = h
                    best_width = w
                    best_angle = angle_deg

            items.append({
                'index': idx,
                'packed_width': best_width,
                'packed_height': best_height,
                'angle': best_angle,
            })
            log.info(f"  {obj.name}: best angle={best_angle}°, size={best_width:.1f}x{best_height:.1f}mm")

        # Phase 2: Run packing
        from .packing import pack_objects_bl
        packed = pack_objects_bl(items, area_w, area_h, spacing)

        packed_by_index = {p['index']: p for p in packed}

        num_plates = max((p['plate'] for p in packed), default=0) + 1
        full_plate_w = gcode_props.pack_area_width
        full_plate_h = gcode_props.pack_area_height
        plate_spacing_x = full_plate_w + 20.0

        # Remove old plate objects
        old_plates = [obj for obj in scene.objects if obj.name.startswith("WorkArea_Plate_")]
        for old in old_plates:
            bpy.data.objects.remove(old, do_unlink=True)

        # Phase 3: Apply rotations and positions
        moved_count = 0
        overflow_count = 0

        for idx, obj in enumerate(mesh_objects):
            p = packed_by_index[idx]

            if not p['placed']:
                log.warning(f"  {obj.name}: could not fit in work area")
                overflow_count += 1
                continue

            plate_offset_x = p['plate'] * plate_spacing_x

            # Apply rotation to geometry
            rotation_angle = math.radians(p['angle'])
            if abs(rotation_angle) > 0.001:
                bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
                center_x = (min(c.x for c in bbox_corners) + max(c.x for c in bbox_corners)) / 2
                center_y = (min(c.y for c in bbox_corners) + max(c.y for c in bbox_corners)) / 2

                rot_matrix = mathutils.Matrix.Rotation(rotation_angle, 4, 'Z')
                center_local = obj.matrix_world.inverted() @ Vector((center_x, center_y, 0))
                translate_to_origin = mathutils.Matrix.Translation(-center_local)
                translate_back = mathutils.Matrix.Translation(center_local)
                transform = translate_back @ rot_matrix @ translate_to_origin
                obj.data.transform(transform)
                obj.data.update()

            # Recalculate bbox after rotation
            bpy.context.view_layer.update()
            bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
            new_min_x = min(c.x for c in bbox_corners)
            new_min_y = min(c.y for c in bbox_corners)

            # Move to packed position (add padding offset)
            offset_x = p['x'] + padding + plate_offset_x - new_min_x
            offset_y = p['y'] + padding - new_min_y
            obj.location.x += offset_x
            obj.location.y += offset_y

            log.info(f"  {obj.name}: plate {p['plate']}, angle={p['angle']:.0f}°, at ({p['x']:.1f}, {p['y']:.1f})")
            moved_count += 1

        bpy.context.view_layer.update()

        # Create plate visualization meshes (full size including padding)
        for plate_idx in range(num_plates):
            plate_x = plate_idx * plate_spacing_x
            self._create_plate_mesh(scene, plate_idx, plate_x, 0, full_plate_w, full_plate_h)

        bpy.context.view_layer.update()

        msg = f"Packed {moved_count} objects into {num_plates} plate(s) ({full_plate_w:.0f}x{full_plate_h:.0f}mm)."
        if overflow_count > 0:
            msg += f" {overflow_count} object(s) did not fit!"
            self.report({'WARNING'}, msg)
        else:
            self.report({'INFO'}, msg)
        return {'FINISHED'}

    @staticmethod
    def _create_plate_mesh(scene, plate_idx, x, y, width, height):
        """Create a flat rectangle mesh to visualize the work area plate."""
        name = f"WorkArea_Plate_{plate_idx}"

        # Create mesh
        mesh = bpy.data.meshes.new(name)
        verts = [
            (x, y, -0.01),
            (x + width, y, -0.01),
            (x + width, y + height, -0.01),
            (x, y + height, -0.01),
        ]
        faces = [(0, 1, 2, 3)]
        mesh.from_pydata(verts, [], faces)
        mesh.update()

        obj = bpy.data.objects.new(name, mesh)
        scene.collection.objects.link(obj)

        # Material (semi-transparent)
        mat = bpy.data.materials.new(name=f"{name}_Mat")
        mat.use_nodes = True
        mat.blend_method = 'BLEND'
        nodes = mat.node_tree.nodes
        nodes.clear()

        bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
        bsdf.inputs['Base Color'].default_value = (0.3, 0.6, 0.3, 1.0)
        bsdf.inputs['Alpha'].default_value = 0.15

        output = nodes.new(type='ShaderNodeOutputMaterial')
        mat.node_tree.links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

        obj.data.materials.append(mat)

        # Lock transforms
        obj.lock_location = (True, True, True)
        obj.lock_rotation = (True, True, True)
        obj.lock_scale = (True, True, True)

        log.info(f"  Created plate: {name} at ({x:.0f}, {y:.0f}), {width:.0f}x{height:.0f}mm")


class CAM_OT_AddToolpathVisualization(bpy.types.Operator):
    """Step 3: Add toolpath visualization meshes to preview scene"""
    bl_idname = "cam.add_toolpath_visualization"
    bl_label = "Step 3: Add Toolpaths"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene

        # Check if we're in the preview scene
        if "gcode_export_source_scene" not in scene:
            self.report({'ERROR'}, "Not in preview scene. Run Step 1 first.")
            return {'CANCELLED'}

        gcode_props = get_source_gcode_properties(scene)

        log.info(f"Step 2: Adding toolpath visualization...")

        # Step 2.1: Create or get dedicated Toolpaths collection
        toolpaths_collection_name = "Toolpaths"

        # Check if collection already exists in this scene
        toolpaths_collection = None
        for coll in scene.collection.children:
            if coll.name == toolpaths_collection_name:
                toolpaths_collection = coll
                break

        log.info(f"Collection search result: {'Found' if toolpaths_collection else 'Not found'}")

        if toolpaths_collection:
            # Collection exists in this scene, clear it completely
            log.info(f"Clearing existing toolpath meshes from '{toolpaths_collection_name}' collection...")

            # Create list of objects to remove (to avoid modifying collection during iteration)
            objects_to_remove = [obj for obj in toolpaths_collection.objects]
            log.info(f"  Found {len(objects_to_remove)} existing toolpath objects to remove")

            for obj in objects_to_remove:
                # Store mesh data reference before removing object
                mesh_data = obj.data

                # Unlink from collection
                toolpaths_collection.objects.unlink(obj)

                # Remove object from Blender data
                bpy.data.objects.remove(obj, do_unlink=True)

                # Remove mesh data if no longer used
                if mesh_data and mesh_data.users == 0:
                    bpy.data.meshes.remove(mesh_data)

            log.info(f"  Cleared {len(objects_to_remove)} toolpath objects")
        else:
            # Collection doesn't exist in this scene, create it
            # First check if it exists globally but not linked to this scene
            if toolpaths_collection_name in bpy.data.collections:
                toolpaths_collection = bpy.data.collections[toolpaths_collection_name]

                # Clear all objects from the globally existing collection before linking
                objects_to_remove = [obj for obj in toolpaths_collection.objects]
                log.info(f"Found existing global '{toolpaths_collection_name}' collection with {len(objects_to_remove)} objects")

                for obj in objects_to_remove:
                    mesh_data = obj.data
                    toolpaths_collection.objects.unlink(obj)
                    bpy.data.objects.remove(obj, do_unlink=True)
                    if mesh_data and mesh_data.users == 0:
                        bpy.data.meshes.remove(mesh_data)

                log.info(f"  Cleared {len(objects_to_remove)} old toolpath objects from global collection")

                # Link to this scene
                scene.collection.children.link(toolpaths_collection)
                log.info(f"Linked existing '{toolpaths_collection_name}' collection to scene")
            else:
                # Create brand new collection
                toolpaths_collection = bpy.data.collections.new(toolpaths_collection_name)
                scene.collection.children.link(toolpaths_collection)
                log.info(f"Created new '{toolpaths_collection_name}' collection")

        # Find all mesh objects with '_Original' suffix in the preview scene
        # These are the transformed meshes created in Step 1
        mesh_objects = []
        for obj in scene.objects:
            if obj.type == 'MESH' and '_Original' in obj.name:
                mesh_objects.append(obj)

        if not mesh_objects:
            self.report({'ERROR'}, "No mesh objects found in preview scene")
            log.error("No mesh objects with '_Original' suffix found")
            return {'CANCELLED'}

        log.info(f"Found {len(mesh_objects)} mesh objects to process")

        for mesh_obj in mesh_objects:
            log.info(f"Processing {mesh_obj.name}...")
            log.info(f"  Mesh has {len(mesh_obj.data.vertices)} vertices, {len(mesh_obj.data.edges)} edges")

            # Extract contours by directly reading slice face edges from the rotated mesh
            # The mesh is already rotated with slice face pointing +Z
            contours = extract_contour_from_rotated_mesh(mesh_obj)
            log.info(f"  extract_contour_from_rotated_mesh returned: {len(contours) if contours else 0} contours")

            if not contours:
                log.warning(f"No contours found for {mesh_obj.name}, skipping")
                continue

            log.info(f"  Extracted {len(contours)} contour(s)")

            # Get object height for depth calculation
            # For rotated mesh, depth is simply the Z-extent (object height)
            bbox_corners = [mesh_obj.matrix_world @ Vector(corner) for corner in mesh_obj.bound_box]
            depth = max(corner.z for corner in bbox_corners) - min(corner.z for corner in bbox_corners)

            # Add extra depth for full cut-through
            depth_extra = gcode_props.depth_extra
            depth += depth_extra
            log.info(f"  Calculated depth: {depth:.3f}mm (includes +{depth_extra:.1f}mm extra)")

            # All contours (outer boundary and holes) are through-cuts to full depth.
            # Previous pocket-machining logic was removed because slice_face_z_positions is
            # always stored for every object, causing holes to be misidentified as pockets
            # when face centers drifted even slightly below obj_max_z.
            contour_depths = {}
            log.info(f"  Through-cutting mode: all {len(contours)} contour(s) to depth {depth:.3f}mm")
            for idx in range(len(contours)):
                contour_depths[idx] = depth

            # Validate depth and step_down values
            if depth < 0.001:  # Less than 0.001mm (1 micron)
                log.warning(f"Depth too small ({depth:.6f}mm), skipping {mesh_obj.name}")
                continue

            is_laser = (gcode_props.machine_type == 'LASER')

            if is_laser:
                # Laser mode: single pass at material top surface
                num_passes = 1
                step_down = depth
                log.info(f"  Laser mode: 1 pass at material top surface")
            else:
                if gcode_props.step_down < 0.1:  # Less than 0.1mm
                    log.warning(f"Step down too small ({gcode_props.step_down:.3f}mm), using minimum 0.1mm")
                    step_down = 0.1
                else:
                    step_down = gcode_props.step_down

                # Calculate and validate number of passes
                # Add small epsilon to handle floating point precision issues
                # If depth is 4.0000001mm and step_down is 1mm, we want 4 passes, not 5
                EPSILON = 1e-6  # 1 micrometer tolerance
                passes_exact = depth / step_down
                num_passes = max(1, int(math.ceil(passes_exact - EPSILON)))
                MAX_PASSES = 1000  # Safety limit
                if num_passes > MAX_PASSES:
                    log.warning(f"Too many passes ({num_passes}), limiting to {MAX_PASSES}")
                    num_passes = MAX_PASSES
                    step_down = depth / MAX_PASSES
                    log.info(f"  Adjusted step_down to {step_down:.3f}mm")

                log.info(f"  Will create {num_passes} passes with step_down={step_down:.3f}mm")

            # Apply tool compensation
            from .generator import compensate_contours, contour_area
            tool_radius = gcode_props.tool_diameter / 2.0
            compensated_contours = compensate_contours(contours, tool_radius)

            # Log compensation results
            for ci, (orig, comp) in enumerate(zip(contours, compensated_contours)):
                orig_a = contour_area(orig)
                comp_a = contour_area(comp)
                log.info(f"  Contour {ci}: area {orig_a:.2f} -> {comp_a:.2f}mm²")

            # Get object dimensions in world space
            obj_world_pos = mesh_obj.matrix_world.translation
            bbox_corners = [mesh_obj.matrix_world @ Vector(corner) for corner in mesh_obj.bound_box]
            obj_max_z = max(corner.z for corner in bbox_corners)  # Top surface Z coordinate
            obj_min_z = min(corner.z for corner in bbox_corners)  # Bottom surface Z coordinate
            obj_height = obj_max_z - obj_min_z  # Material thickness

            log.info(f"  Material: thickness={obj_height:.3f}mm, top Z={obj_max_z:.3f}mm, bottom Z={obj_min_z:.3f}mm, position=({obj_world_pos.x:.3f}, {obj_world_pos.y:.3f}, {obj_world_pos.z:.3f})")

            # All toolpath meshes will be added to the dedicated Toolpaths collection
            log.info(f"  Using dedicated Toolpaths collection for {mesh_obj.name}")

            # Create toolpath meshes (use validated num_passes and step_down from above)
            # num_passes was already calculated and validated above

            for pass_num in range(num_passes):
                if is_laser:
                    # Laser mode: single pass at material top surface (no depth)
                    current_depth = 0.0
                    z_height = obj_max_z
                    r, g, b = 1.0, 0.0, 0.0
                else:
                    current_depth = min((pass_num + 1) * step_down, depth)
                    # Toolpath Z position: start from material top and go down by current_depth
                    z_height = obj_max_z - current_depth

                    # Color gradient
                    progress = current_depth / depth
                    r = progress
                    g = 0.0
                    b = 1.0 - progress

                # Consolidate all contours into a single mesh for this pass
                all_vertices = []
                all_edges = []
                vertex_offset = 0
                contour_count = 0

                for contour_idx, contour in enumerate(compensated_contours):
                    if len(contour) < 3:
                        continue

                    # Get this contour's specific depth (from contour_depths dict)
                    contour_max_depth = contour_depths.get(contour_idx, depth)

                    # Only add this contour if current pass depth <= contour's max depth
                    if current_depth > contour_max_depth:
                        continue  # Skip this contour for this pass (already reached its max depth)

                    # Add vertices for this contour at the current Z height
                    contour_vertices = [(x, y, z_height) for x, y in contour]
                    all_vertices.extend(contour_vertices)

                    # Add edges for this contour (offset by current vertex count)
                    contour_edges = [(i + vertex_offset, (i + 1) % len(contour_vertices) + vertex_offset)
                                     for i in range(len(contour_vertices))]
                    all_edges.extend(contour_edges)

                    vertex_offset += len(contour_vertices)
                    contour_count += 1

                if not all_vertices:
                    log.warning(f"  Pass {pass_num+1}: No valid contours, skipping")
                    continue

                # Create mesh name from the base name (remove '_Original' suffix)
                base_name = mesh_obj.name.replace('_Original', '')
                toolpath_mesh_name = f"{base_name}_Toolpath_P{pass_num+1}"
                toolpath_mesh_data = bpy.data.meshes.new(toolpath_mesh_name)

                # Create mesh with all contours
                toolpath_mesh_data.from_pydata(all_vertices, all_edges, [])
                toolpath_mesh_data.update()

                # Create object
                toolpath_obj = bpy.data.objects.new(toolpath_mesh_name, toolpath_mesh_data)
                toolpaths_collection.objects.link(toolpath_obj)

                # Position at world origin (vertices already in world space)
                toolpath_obj.location = Vector((0, 0, 0))
                toolpath_obj.rotation_mode = 'QUATERNION'
                toolpath_obj.rotation_quaternion = (1, 0, 0, 0)

                log.info(f"  Toolpath {toolpath_mesh_name}: Z={z_height:.3f}mm (depth={current_depth:.3f}mm from top), {contour_count} contours, {len(all_vertices)} vertices")

                # Lock transformations
                toolpath_obj.lock_location = (True, True, True)
                toolpath_obj.lock_rotation = (True, True, True)
                toolpath_obj.lock_scale = (True, True, True)

                # Set material
                mat = bpy.data.materials.new(name=f"Toolpath_Mat_{base_name}_P{pass_num+1}")
                mat.use_nodes = True
                nodes = mat.node_tree.nodes
                nodes.clear()

                emission = nodes.new(type='ShaderNodeEmission')
                emission.inputs['Color'].default_value = (r, g, b, 1)
                emission.inputs['Strength'].default_value = 5.0

                output = nodes.new(type='ShaderNodeOutputMaterial')
                mat.node_tree.links.new(emission.outputs['Emission'], output.inputs['Surface'])

                toolpath_obj.data.materials.append(mat)
                toolpath_obj.display_type = 'WIRE'

            log.info(f"Added {num_passes} toolpath pass meshes for {mesh_obj.name}")

        self.report({'INFO'}, f"Step 3 complete. Use 'Step 4' to generate G-code or 'Cancel' to return.")
        return {'FINISHED'}


class CAM_OT_DownloadGcode(bpy.types.Operator, ExportHelper):
    """Step 4: Generate and download G-code file"""
    bl_idname = "cam.download_gcode"
    bl_label = "Step 4: Download G-code"
    bl_options = {'REGISTER'}

    filename_ext = ".nc"
    filter_glob: StringProperty(default="*.nc;*.gcode", options={'HIDDEN'})

    def invoke(self, context, event):
        from datetime import datetime
        gcode_props = get_source_gcode_properties(context.scene)

        # Build filename: tool_diameter-step_down-feed_YYYYMMDD.nc
        date_str = datetime.now().strftime("%Y%m%d")
        td = f"D{gcode_props.tool_diameter:.1f}"
        sd = f"SD{gcode_props.step_down:.1f}"
        fr = f"F{gcode_props.feed_rate_cut:.0f}"
        sp = f"S{gcode_props.spindle_speed}"

        self.filepath = f"{td}_{sd}_{fr}_{sp}_{date_str}.nc"

        return super().invoke(context, event)

    def execute(self, context):
        scene = context.scene

        # Check if we're in the preview scene
        if "gcode_export_source_scene" not in scene:
            self.report({'ERROR'}, "Not in G-code preview scene")
            return {'CANCELLED'}

        # Check if toolpaths have been generated (Step 3)
        toolpaths_collection = None
        for coll in scene.collection.children:
            if coll.name == "Toolpaths":
                toolpaths_collection = coll
                break

        if not toolpaths_collection or len(toolpaths_collection.objects) == 0:
            self.report({'ERROR'}, "No toolpaths found. Run Step 3 first to generate toolpaths.")
            return {'CANCELLED'}

        log.info(f"Step 4: Generating G-code from {len(toolpaths_collection.objects)} toolpath meshes...")

        # Generate G-code from toolpath meshes
        gcode_props = get_source_gcode_properties(scene)
        settings = GcodeSettings(gcode_props)
        generator = GcodeGenerator(settings)

        # Group toolpath meshes by object name and pass number
        # Mesh name format: {base_name}_Toolpath_P{pass_num}
        import re
        objects_data = {}  # {base_name: {pass_num: mesh_obj}}

        for mesh_obj in toolpaths_collection.objects:
            if mesh_obj.type != 'MESH' or '_Toolpath_P' not in mesh_obj.name:
                continue
            try:
                # Match pattern: {base_name}_Toolpath_P{pass_num} with optional Blender suffix
                # Examples: "link01_Toolpath_P3", "link01_Toolpath_P3.001"
                tp_match = re.match(r'^(.+)_Toolpath_P(\d+)(?:\.\d{3})?$', mesh_obj.name)
                if not tp_match:
                    log.warning(f"Could not parse toolpath name: {mesh_obj.name}")
                    continue

                base_name_with_suffix = tp_match.group(1)
                pass_num = int(tp_match.group(2))

                # Remove Blender's auto suffix from base name too
                base_match = re.match(r'^(.+)\.\d{3}$', base_name_with_suffix)
                base_name = base_match.group(1) if base_match else base_name_with_suffix

                if base_name not in objects_data:
                    objects_data[base_name] = {}
                objects_data[base_name][pass_num] = mesh_obj

            except (ValueError, IndexError):
                continue

        if not objects_data:
            self.report({'ERROR'}, "No valid toolpath meshes found")
            return {'CANCELLED'}

        # Group objects by plate based on actual X position
        # This handles manual repositioning after Pack Objects
        full_plate_w = gcode_props.pack_area_width
        plate_spacing_x = full_plate_w + 20.0

        plate_objects = {}  # {plate_idx: {base_name: {pass_num: mesh_obj}}}
        for base_name, passes in objects_data.items():
            # Determine plate from actual mesh position
            any_mesh = next(iter(passes.values()))
            bbox_corners = [any_mesh.matrix_world @ Vector(corner) for corner in any_mesh.bound_box]
            center_x = (min(c.x for c in bbox_corners) + max(c.x for c in bbox_corners)) / 2
            plate_idx = max(0, int(center_x / plate_spacing_x))

            if plate_idx not in plate_objects:
                plate_objects[plate_idx] = {}
            plate_objects[plate_idx][base_name] = passes
            log.info(f"  {base_name}: center_x={center_x:.1f}mm -> plate {plate_idx}")

        num_plates = len(plate_objects)
        log.info(f"Found {len(objects_data)} objects across {num_plates} plate(s)")

        # Generate G-code per plate
        import os
        base_path, ext = os.path.splitext(self.filepath)
        saved_files = []

        full_plate_w = gcode_props.pack_area_width
        plate_spacing_x = full_plate_w + 20.0

        for plate_idx in sorted(plate_objects.keys()):
            plate_data = plate_objects[plate_idx]
            plate_origin_x = plate_idx * plate_spacing_x
            lines = self._generate_plate_gcode(plate_data, gcode_props, settings, generator, plate_origin_x)

            # File naming: single plate = original name, multiple = _plate1, _plate2...
            if num_plates == 1:
                filepath = self.filepath
            else:
                filepath = f"{base_path}_plate{plate_idx + 1}{ext}"

            gcode_data = '\n'.join(lines)
            with open(filepath, 'w') as f:
                f.write(gcode_data)

            saved_files.append(filepath)
            log.info(f"✓ G-code saved: {filepath}")

        if num_plates == 1:
            self.report({'INFO'}, f"G-code saved to: {saved_files[0]}")
        else:
            self.report({'INFO'}, f"G-code saved: {num_plates} files ({', '.join(os.path.basename(f) for f in saved_files)})")

        return {'FINISHED'}

    def _generate_plate_gcode(self, plate_data, gcode_props, settings, generator, plate_origin_x=0.0):
        """Generate G-code lines for a single plate's objects.
        All XY coordinates are offset by -plate_origin_x so each plate starts at X=0."""
        from .generator import contour_area as _contour_area

        lines = []

        # Header
        header_lines = generator.generate_header()
        filtered_header = [line for line in header_lines if not line.startswith("G0 Z")]
        lines.extend(filtered_header)
        lines.append(f"(G-code generated from toolpath positions)")
        lines.append("")

        safe_height = settings.safe_height
        lines.append(f"G0 Z{safe_height:.3f} (Move to safe height)")
        lines.append("")

        # Calculate XY offset based on start_position
        start_pos = gcode_props.start_position
        plate_w = gcode_props.pack_area_width
        plate_h = gcode_props.pack_area_height

        if start_pos == 'FRONT_RIGHT':
            origin_offset_x = plate_w
            origin_offset_y = 0.0
        elif start_pos == 'BACK_LEFT':
            origin_offset_x = 0.0
            origin_offset_y = plate_h
        elif start_pos == 'BACK_RIGHT':
            origin_offset_x = plate_w
            origin_offset_y = plate_h
        elif start_pos == 'CENTER':
            origin_offset_x = plate_w / 2.0
            origin_offset_y = plate_h / 2.0
        else:  # FRONT_LEFT
            origin_offset_x = 0.0
            origin_offset_y = 0.0

        if origin_offset_x != 0.0 or origin_offset_y != 0.0:
            pos_label = {'FRONT_RIGHT': 'Front Right', 'BACK_LEFT': 'Back Left',
                         'BACK_RIGHT': 'Back Right', 'CENTER': 'Center'}.get(start_pos, start_pos)
            lines.append(f"(Origin: {pos_label}  X offset={-origin_offset_x:.3f}  Y offset={-origin_offset_y:.3f})")
            lines.append("")

        is_laser = (gcode_props.machine_type == 'LASER')

        # Snake-order cutting: top-left first, alternate row direction
        base_name_positions = {}
        for base_name, passes in plate_data.items():
            any_mesh = next(iter(passes.values()))
            bbox = [any_mesh.matrix_world @ Vector(corner) for corner in any_mesh.bound_box]
            xs = [c.x - plate_origin_x - origin_offset_x for c in bbox]
            ys = [c.y - origin_offset_y for c in bbox]
            base_name_positions[base_name] = {
                'min_y': min(ys),
                'max_y': max(ys),
                'cx': (min(xs) + max(xs)) / 2,
            }

        # Group into rows by Y-range overlap, top first
        sorted_by_top = sorted(base_name_positions.keys(),
                              key=lambda n: -base_name_positions[n]['max_y'])
        rows = []
        for name in sorted_by_top:
            pos = base_name_positions[name]
            placed = False
            for row in rows:
                if pos['max_y'] >= row['min_y'] and pos['min_y'] <= row['max_y']:
                    row['members'].append(name)
                    row['min_y'] = min(row['min_y'], pos['min_y'])
                    row['max_y'] = max(row['max_y'], pos['max_y'])
                    placed = True
                    break
            if not placed:
                rows.append({
                    'min_y': pos['min_y'],
                    'max_y': pos['max_y'],
                    'members': [name],
                })

        # Within each row, alternate X-sort direction for serpentine path
        snake_order = []
        for row_idx, row in enumerate(rows):
            reverse = (row_idx % 2 == 1)
            sorted_row = sorted(row['members'],
                               key=lambda n: base_name_positions[n]['cx'],
                               reverse=reverse)
            snake_order.extend(sorted_row)
            log.info(f"  Row {row_idx} (Y={row['min_y']:.1f}-{row['max_y']:.1f}, "
                    f"{'R->L' if reverse else 'L->R'}): {sorted_row}")

        for base_name in snake_order:
            passes = plate_data[base_name]
            pass_numbers = sorted(passes.keys())

            lines.append(f"(Object: {base_name})")
            lines.append("")

            # Calculate material top Z
            first_pass_mesh = passes[pass_numbers[0]]
            bbox_corners = [first_pass_mesh.matrix_world @ Vector(corner) for corner in first_pass_mesh.bound_box]
            first_pass_z = max(corner.z for corner in bbox_corners)
            max_z = first_pass_z + gcode_props.step_down

            # Extract contours from all passes
            pass_data = {}
            for pass_num in pass_numbers:
                mesh_obj = passes[pass_num]
                bbox_corners = [mesh_obj.matrix_world @ Vector(corner) for corner in mesh_obj.bound_box]
                z_height = sum(corner.z for corner in bbox_corners) / len(bbox_corners)
                current_depth = max_z - z_height
                z_height_relative = z_height - max_z

                contours = self._extract_contours_from_mesh(mesh_obj)
                if contours:
                    contours = [[(x - plate_origin_x - origin_offset_x, y - origin_offset_y)
                                 for x, y in c] for c in contours]
                    pass_data[pass_num] = (z_height_relative, current_depth, contours)

            if not pass_data:
                continue

            # Identify outer boundary and holes
            first_pass_contours = pass_data[pass_numbers[0]][2]
            contour_areas = [_contour_area(c) for c in first_pass_contours]
            outer_idx = contour_areas.index(max(contour_areas)) if contour_areas else -1
            hole_indices = [i for i in range(len(first_pass_contours)) if i != outer_idx]

            # Pre-calculate reference areas
            contour_ref_areas = {idx: _contour_area(c) for idx, c in enumerate(first_pass_contours) if len(c) >= 3}

            def _find_matching_contour(ref_area, contours):
                best_idx = None
                best_ratio = float('inf')
                for idx, contour in enumerate(contours):
                    if len(contour) < 3:
                        continue
                    area = _contour_area(contour)
                    if area < 0.001:
                        continue
                    ratio = max(area, ref_area) / min(area, ref_area) if min(area, ref_area) > 0.001 else float('inf')
                    if ratio < best_ratio:
                        best_ratio = ratio
                        best_idx = idx
                if best_ratio > 2.0:
                    return None
                return best_idx

            # Tab settings
            tab_enabled = gcode_props.tab_enabled and not is_laser
            tab_height = gcode_props.tab_height
            tab_width = gcode_props.tab_width
            tab_count = gcode_props.tab_count

            def _contour_length(contour):
                """Calculate total perimeter length of a contour."""
                total = 0.0
                for i in range(len(contour)):
                    j = (i + 1) % len(contour)
                    dx = contour[j][0] - contour[i][0]
                    dy = contour[j][1] - contour[i][1]
                    total += math.sqrt(dx * dx + dy * dy)
                return total

            def _calc_tab_positions(contour, num_tabs, width):
                """Calculate tab positions as (cumulative_distance, tab_half_width) pairs.
                Tabs are evenly spaced along the contour perimeter."""
                perimeter = _contour_length(contour)
                if perimeter < 0.001 or num_tabs == 0:
                    return []
                spacing = perimeter / num_tabs
                half_w = width / 2.0
                return [(spacing * (i + 0.5), half_w) for i in range(num_tabs)]

            def _is_in_tab(cum_dist, tab_positions):
                """Check if a cumulative distance along contour falls within any tab."""
                for center, half_w in tab_positions:
                    if abs(cum_dist - center) <= half_w:
                        return True
                return False

            def generate_contour_passes(contour_idx, label, is_outer=False):
                lines.append(f"({label}, cutting to final depth)")
                lines.append("")
                ref_area = contour_ref_areas.get(contour_idx)

                # Collect valid passes (skip unmatched) to determine true last pass
                valid_passes = []
                for pass_num in pass_numbers:
                    z_height, current_depth, contours = pass_data[pass_num]
                    if ref_area is not None:
                        matched_idx = _find_matching_contour(ref_area, contours)
                    else:
                        matched_idx = contour_idx if contour_idx < len(contours) else None
                    if matched_idx is not None:
                        contour = contours[matched_idx]
                        if len(contour) >= 2:
                            valid_passes.append(pass_num)

                if not valid_passes:
                    return

                last_valid_pass = valid_passes[-1]
                last_z = pass_data[last_valid_pass][0]

                # Tab top Z: any pass that goes below this must leave tab regions uncut
                tabs_active = tab_enabled and is_outer
                tab_z = last_z + tab_height if tabs_active else None

                # For outer boundary with tabs: skip duplicate passes at final depth
                # so only the tab pass cuts at that depth
                if tabs_active:
                    deduped = []
                    for vp in valid_passes:
                        vp_z = pass_data[vp][0]
                        if vp != last_valid_pass and abs(vp_z - last_z) < 0.001:
                            continue  # Skip non-tab pass at same depth as final
                        deduped.append(vp)
                    valid_passes = deduped

                for pass_idx, pass_num in enumerate(pass_numbers):
                    if pass_num not in valid_passes:
                        continue

                    z_height, current_depth, contours = pass_data[pass_num]

                    if ref_area is not None:
                        matched_idx = _find_matching_contour(ref_area, contours)
                    else:
                        matched_idx = contour_idx if contour_idx < len(contours) else None

                    if matched_idx is None:
                        continue

                    contour = contours[matched_idx]
                    if len(contour) < 2:
                        continue

                    is_first_pass = (pass_num == valid_passes[0])
                    is_last_pass = (pass_num == last_valid_pass)
                    # Use tabs on any pass that would cut below the tab top surface
                    use_tabs = tabs_active and z_height < tab_z - 0.001

                    if use_tabs and is_last_pass:
                        lines.append(f"({label}, FINAL Pass with {tab_count} tabs, Z={z_height:.3f}mm)")
                    elif use_tabs:
                        lines.append(f"({label}, Pass {pass_num}/{len(pass_numbers)} with {tab_count} tabs, Z={z_height:.3f}mm, depth={current_depth:.3f}mm)")
                    else:
                        lines.append(f"({label}, Pass {pass_num}/{len(pass_numbers)}, Z={z_height:.3f}mm, depth={current_depth:.3f}mm)")

                    if is_first_pass or gcode_props.retract_between_passes:
                        lines.append(f"G0 Z{safe_height:.3f} (Retract to safe height)")
                        start_x, start_y = contour[0]
                        lines.append(f"G0 X{start_x:.3f} Y{start_y:.3f} (Move to start)")
                    else:
                        start_x, start_y = contour[0]

                    if is_laser:
                        if is_first_pass or gcode_props.retract_between_passes:
                            lines.append(f"G0 Z0.000 (At surface)")
                        lines.append(f"M3 S{settings.spindle_speed} (Laser ON)")
                        feed_rate = gcode_props.laser_speed
                        for x, y in contour[1:]:
                            lines.append(f"G1 X{x:.3f} Y{y:.3f} F{feed_rate:.1f}")
                        if contour[0] != contour[-1]:
                            lines.append(f"G1 X{start_x:.3f} Y{start_y:.3f} F{feed_rate:.1f} (Close loop)")
                        lines.append(f"M5 (Laser OFF)")
                    else:
                        feed_rate = settings.feed_rate_cut
                        plunge_rate = settings.feed_rate_plunge

                        if is_first_pass:
                            prev_z = 0.0
                        else:
                            prev_pass_num = pass_numbers[pass_idx - 1]
                            prev_z = pass_data[prev_pass_num][0]

                        lines.append(f"G0 Z{prev_z:.3f} (Move to previous pass depth)")

                        remaining_points = contour[1:]
                        if contour[0] != contour[-1]:
                            remaining_points = list(remaining_points) + [contour[0]]

                        total_points = len(remaining_points)
                        z_drop = prev_z - z_height
                        ramp_points = max(1, min(total_points // 10, 5))

                        if use_tabs:
                            tab_positions = _calc_tab_positions(contour, tab_count, tab_width)
                            tab_z = z_height + tab_height

                            # Ramp entry first
                            for i, (x, y) in enumerate(remaining_points[:ramp_points]):
                                progress = (i + 1) / ramp_points
                                z_interp = prev_z - (z_drop * progress)
                                lines.append(f"G1 X{x:.3f} Y{y:.3f} Z{z_interp:.3f} F{plunge_rate:.1f}")

                            # Flat phase with tabs — interpolate points at tab boundaries
                            cum_dist = 0.0
                            prev_point = (start_x, start_y)
                            for x, y in remaining_points[:ramp_points]:
                                dx = x - prev_point[0]
                                dy = y - prev_point[1]
                                cum_dist += math.sqrt(dx * dx + dy * dy)
                                prev_point = (x, y)

                            in_tab = _is_in_tab(cum_dist, tab_positions)

                            for x, y in remaining_points[ramp_points:]:
                                dx = x - prev_point[0]
                                dy = y - prev_point[1]
                                seg_len = math.sqrt(dx * dx + dy * dy)
                                next_dist = cum_dist + seg_len

                                # Check for tab boundary crossings within this segment
                                for center, half_w in tab_positions:
                                    tab_start = center - half_w
                                    tab_end = center + half_w

                                    # Entering tab
                                    if not in_tab and cum_dist < tab_start <= next_dist:
                                        t = (tab_start - cum_dist) / seg_len if seg_len > 0 else 0
                                        ix = prev_point[0] + dx * t
                                        iy = prev_point[1] + dy * t
                                        lines.append(f"G1 X{ix:.3f} Y{iy:.3f} F{feed_rate:.1f}")
                                        lines.append(f"G1 X{ix:.3f} Y{iy:.3f} Z{tab_z:.3f} F{plunge_rate:.1f} (Tab start)")
                                        in_tab = True

                                    # Leaving tab
                                    if in_tab and cum_dist < tab_end <= next_dist:
                                        t = (tab_end - cum_dist) / seg_len if seg_len > 0 else 0
                                        ix = prev_point[0] + dx * t
                                        iy = prev_point[1] + dy * t
                                        lines.append(f"G1 X{ix:.3f} Y{iy:.3f} F{feed_rate:.1f}")
                                        lines.append(f"G1 X{ix:.3f} Y{iy:.3f} Z{z_height:.3f} F{plunge_rate:.1f} (Tab end)")
                                        in_tab = False

                                cum_dist = next_dist
                                prev_point = (x, y)
                                lines.append(f"G1 X{x:.3f} Y{y:.3f} F{feed_rate:.1f}")
                        else:
                            # Normal pass (no tabs)
                            for i, (x, y) in enumerate(remaining_points[:ramp_points]):
                                progress = (i + 1) / ramp_points
                                z_interp = prev_z - (z_drop * progress)
                                lines.append(f"G1 X{x:.3f} Y{y:.3f} Z{z_interp:.3f} F{plunge_rate:.1f}")

                            for x, y in remaining_points[ramp_points:]:
                                lines.append(f"G1 X{x:.3f} Y{y:.3f} F{feed_rate:.1f}")

                    lines.append("")

                lines.append(f"G0 Z{safe_height:.3f} (Retract after completing {label})")
                lines.append("")

            # Cut holes first, then outer boundary
            for hole_idx in hole_indices:
                generate_contour_passes(hole_idx, f"Hole {hole_idx+1}", is_outer=False)

            if outer_idx >= 0:
                generate_contour_passes(outer_idx, "Outer boundary", is_outer=True)

            lines.append("")

        # Footer
        footer_lines = generator.generate_footer()
        for line in footer_lines:
            if line.startswith("G0 Z") and "safe height" in line.lower():
                lines.append(f"G0 Z{safe_height:.3f} (Safe height)")
            else:
                lines.append(line)

        return lines

    def _extract_contours_from_mesh(self, mesh_obj):
        """Extract closed contours from mesh edges in correct order."""
        mesh = mesh_obj.data

        # Build edge connectivity
        edges = [(edge.vertices[0], edge.vertices[1]) for edge in mesh.edges]

        if not edges:
            return []

        # Build adjacency list
        adjacency = {}
        for v1, v2 in edges:
            if v1 not in adjacency:
                adjacency[v1] = []
            if v2 not in adjacency:
                adjacency[v2] = []
            adjacency[v1].append(v2)
            adjacency[v2].append(v1)

        # Extract contours by following edges
        contours = []
        visited_edges = set()

        for start_v in adjacency.keys():
            if len([e for e in edges if start_v in e and e not in visited_edges]) == 0:
                continue

            # Start a new contour
            contour = []
            current_v = start_v
            prev_v = None

            while True:
                contour.append(current_v)

                # Find next unvisited vertex
                next_v = None
                for neighbor in adjacency[current_v]:
                    if neighbor != prev_v:
                        edge = tuple(sorted([current_v, neighbor]))
                        if edge not in visited_edges:
                            next_v = neighbor
                            visited_edges.add(edge)
                            break

                if next_v is None or next_v == start_v:
                    # Contour closed or no more edges
                    break

                prev_v = current_v
                current_v = next_v

            if len(contour) >= 3:
                # Convert vertex indices to world coordinates
                world_matrix = mesh_obj.matrix_world
                contour_points = []
                for v_idx in contour:
                    vertex = mesh.vertices[v_idx]
                    world_pos = world_matrix @ vertex.co
                    contour_points.append((world_pos.x, world_pos.y))

                contours.append(contour_points)

        return contours


class CAM_OT_ExportSVG(bpy.types.Operator, ExportHelper):
    """Export top-down SVG drawing of all plates (outer contours + holes)"""
    bl_idname = "cam.export_svg"
    bl_label = "Export SVG"
    bl_options = {'REGISTER'}

    filename_ext = ".svg"
    filter_glob: StringProperty(default="*.svg", options={'HIDDEN'})

    def invoke(self, context, event):
        from datetime import datetime
        date_str = datetime.now().strftime("%Y%m%d")
        self.filepath = f"layout_{date_str}.svg"
        return super().invoke(context, event)

    def execute(self, context):
        from .svg_export import build_svg, order_contours

        scene = context.scene

        if "gcode_export_source_scene" not in scene:
            self.report({'ERROR'}, "Not in preview scene. Run Step 1 first.")
            return {'CANCELLED'}

        mesh_objects = [obj for obj in scene.objects if obj.type == 'MESH' and '_Original' in obj.name]
        if not mesh_objects:
            self.report({'ERROR'}, "No prepared objects found. Run Step 1 first.")
            return {'CANCELLED'}

        gcode_props = get_source_gcode_properties(scene)
        plate_w = gcode_props.pack_area_width
        plate_h = gcode_props.pack_area_height
        plate_spacing_x = plate_w + 20.0

        # Collect contours per object, ordered (outer first)
        object_contours = []
        max_plate_idx = 0
        plate_indices_seen = set()

        for mesh_obj in mesh_objects:
            contours = extract_contour_from_rotated_mesh(mesh_obj)
            ordered = order_contours(contours)
            if not ordered:
                log.warning(f"No contours for {mesh_obj.name}, skipping")
                continue
            object_contours.append(ordered)

            # Determine plate from mesh center X
            bbox = [mesh_obj.matrix_world @ Vector(c) for c in mesh_obj.bound_box]
            center_x = (min(c.x for c in bbox) + max(c.x for c in bbox)) / 2
            plate_idx = max(0, int(center_x / plate_spacing_x))
            plate_indices_seen.add(plate_idx)
            if plate_idx > max_plate_idx:
                max_plate_idx = plate_idx

        if not object_contours:
            self.report({'ERROR'}, "No contours could be extracted")
            return {'CANCELLED'}

        # Build plate rectangles (origin at plate_idx * spacing_x, 0)
        plate_rects = [
            (idx * plate_spacing_x, 0.0, plate_w, plate_h)
            for idx in sorted(plate_indices_seen)
        ]

        svg_text = build_svg(object_contours, plate_rects)
        if not svg_text:
            self.report({'ERROR'}, "Failed to build SVG")
            return {'CANCELLED'}

        with open(self.filepath, 'w', encoding='utf-8') as f:
            f.write(svg_text)

        log.info(f"SVG saved: {self.filepath}")
        self.report({'INFO'}, f"SVG saved to: {self.filepath}")
        return {'FINISHED'}


class CAM_OT_CancelGcodeExport(bpy.types.Operator):
    """Cancel G-code export and return to original scene"""
    bl_idname = "cam.cancel_gcode_export"
    bl_label = "Cancel and Return"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene

        # Check if we're in the preview scene
        if "gcode_export_source_scene" not in scene:
            self.report({'WARNING'}, "Not in G-code preview scene")
            return {'CANCELLED'}

        # Get source scene name
        source_scene_name = scene["gcode_export_source_scene"]

        # Switch back to source scene
        if source_scene_name in bpy.data.scenes:
            context.window.scene = bpy.data.scenes[source_scene_name]
            log.info(f"Returned to scene: {source_scene_name}")
        else:
            self.report({'ERROR'}, f"Source scene '{source_scene_name}' not found")
            return {'CANCELLED'}

        # Remove temporary scene
        bpy.data.scenes.remove(scene)
        log.info(f"Removed temporary scene")

        # Frame all objects in original scene (Home)
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        with context.temp_override(area=area, region=region):
                            bpy.ops.view3d.view_all()
                        break
                break

        self.report({'INFO'}, "Returned to original scene")
        return {'FINISHED'}
