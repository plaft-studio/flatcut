"""
G-code Generator Module

This module contains the core G-code generation logic for CNC and laser cutting.
"""

import bpy
import math
from typing import List, Tuple
from mathutils import Vector

from .settings import GcodeSettings


def has_slice_face_data(obj: bpy.types.Object) -> bool:
    """
    Check if an object has slice face data saved.

    Args:
        obj: Object to check

    Returns:
        True if object has slice face data, False otherwise
    """
    return "slice_plane_normal" in obj and "slice_plane_point" in obj


def is_contour_clockwise(contour: List[Tuple[float, float]]) -> bool:
    """
    Determine if a 2D contour is oriented clockwise (CW) or counter-clockwise (CCW).
    Uses the shoelace formula to calculate the signed area.

    Args:
        contour: List of (x, y) points

    Returns:
        True if clockwise (hole), False if counter-clockwise (outer boundary)
    """
    if len(contour) < 3:
        return False

    # Shoelace formula for signed area
    area = 0.0
    n = len(contour)
    for i in range(n):
        j = (i + 1) % n
        area += contour[i][0] * contour[j][1]
        area -= contour[j][0] * contour[i][1]

    # Positive area = CCW (outer), Negative area = CW (hole)
    return area < 0


def normalize_contour_to_ccw(contour: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """
    Normalize a contour to counter-clockwise (CCW) orientation.
    If the contour is clockwise, reverse it to make it counter-clockwise.

    Args:
        contour: List of (x, y) points

    Returns:
        Contour in CCW orientation
    """
    if is_contour_clockwise(contour):
        # Reverse to make CCW
        return list(reversed(contour))
    else:
        # Already CCW
        return contour


def offset_contour(contour: List[Tuple[float, float]], offset_distance: float) -> List[Tuple[float, float]]:
    """
    Offset a CCW-oriented 2D contour by a specified distance.
    IMPORTANT: This function assumes the contour is already in CCW orientation.
    Use normalize_contour_to_ccw() first if needed.

    Args:
        contour: List of (x, y) points forming a closed CCW contour
        offset_distance: Distance to offset (mm).
                        Positive = outward (expand), Negative = inward (contract)

    Returns:
        Offset contour as list of (x, y) points
    """
    if len(contour) < 3:
        # Not enough points to offset properly
        return contour

    # Ensure contour is closed
    points = list(contour)
    if points[0] != points[-1]:
        points.append(points[0])

    # Calculate offset points using perpendicular normals
    # Assumes CCW orientation where (-v.y, v.x) points outward (to the left of the vector)
    offset_points = []
    n = len(points) - 1  # Number of segments (excluding closing point)

    for i in range(n):
        # Current point and neighbors
        prev_idx = (i - 1) % n
        curr_idx = i
        next_idx = (i + 1) % n

        p_prev = Vector((points[prev_idx][0], points[prev_idx][1], 0))
        p_curr = Vector((points[curr_idx][0], points[curr_idx][1], 0))
        p_next = Vector((points[next_idx][0], points[next_idx][1], 0))

        # Vectors to previous and next points
        v1 = (p_curr - p_prev).normalized()
        v2 = (p_next - p_curr).normalized()

        # Calculate perpendicular normals (2D)
        # For CCW contours, (-v.y, v.x) points outward (to the left)
        n1 = Vector((-v1.y, v1.x, 0))
        n2 = Vector((-v2.y, v2.x, 0))

        # Average normal at this vertex
        normal = (n1 + n2).normalized()

        # Handle degenerate cases
        if normal.length < 0.001:
            normal = n1 if n1.length > 0.001 else Vector((0, 1, 0))

        # Calculate offset point
        # The offset distance is adjusted by the angle between segments
        angle_factor = 1.0
        dot = v1.dot(v2)
        if abs(dot) < 0.999:  # Not parallel
            # Calculate the actual offset needed at corner
            angle_factor = 1.0 / max(0.1, math.sqrt((1 + dot) / 2))  # Limit extreme angles

        offset_point = p_curr + normal * offset_distance * angle_factor
        offset_points.append((offset_point.x, offset_point.y))

    return offset_points


def contour_area(contour: List[Tuple[float, float]]) -> float:
    """Calculate the absolute area of a 2D contour using the shoelace formula."""
    if len(contour) < 3:
        return 0.0
    area = 0.0
    n = len(contour)
    for i in range(n):
        j = (i + 1) % n
        area += contour[i][0] * contour[j][1]
        area -= contour[j][0] * contour[i][1]
    return abs(area / 2.0)


def compensate_contours(contours: List[List[Tuple[float, float]]],
                        tool_radius: float) -> List[List[Tuple[float, float]]]:
    """
    Apply tool diameter compensation to contours.

    - Outer boundary (largest area): offset inward so tool center stays inside material
    - Holes (smaller areas): offset so toolpath is inside the hole (smaller circle)

    The hole offset direction is validated by checking the result area.
    If the offset makes the hole larger instead of smaller, the direction is flipped.

    Args:
        contours: List of 2D contours
        tool_radius: Tool radius (half of tool diameter) in mm

    Returns:
        List of compensated contours
    """
    if tool_radius < 0.001:
        return contours

    # Calculate area for each contour
    areas = [contour_area(c) for c in contours]

    # Outer boundary = largest area
    outer_idx = areas.index(max(areas)) if areas else -1

    result = []
    for idx, contour in enumerate(contours):
        if len(contour) < 3:
            result.append(contour)
            continue

        ccw = normalize_contour_to_ccw(contour)

        if idx == outer_idx:
            # Outer: toolpath inside the boundary
            result.append(offset_contour(ccw, -tool_radius))
        else:
            # Hole: toolpath must be a smaller circle inside the hole
            compensated = offset_contour(ccw, -tool_radius)
            if contour_area(compensated) < areas[idx]:
                result.append(compensated)
            else:
                # Wrong direction — flip
                result.append(offset_contour(ccw, tool_radius))

    return result


def get_bl_info_version():
    """
    Get bl_info version from the root module.
    Falls back to (1, 0, 0) if not available.
    """
    try:
        # Try to import from parent module
        from .. import bl_info
        return bl_info['version']
    except (ImportError, KeyError):
        # Fallback version if bl_info not available
        return (1, 0, 0)


class GcodeGenerator:
    """Generate G-code for CNC machining"""

    def __init__(self, settings: GcodeSettings):
        self.settings = settings

    def generate_header(self) -> List[str]:
        """Generate G-code header"""
        version = get_bl_info_version()
        return [
            f"(Generated by Craft G-code Generator v{version[0]}.{version[1]})",
            "(Units: mm)",
            "",
            "G21 (Metric units)",
            "G90 (Absolute positioning)",
            f"M3 S{self.settings.spindle_speed} (Start spindle)",
            "G4 P2.0 (Wait 2 seconds)",
            f"G0 Z{self.settings.safe_height:.3f} (Move to safe height)",
            "",
        ]

    def generate_footer(self) -> List[str]:
        """Generate G-code footer"""
        return [
            "",
            f"G0 Z{self.settings.safe_height:.3f} (Safe height)",
            "M5 (Stop spindle)",
            "G0 X0 Y0 (Return to origin)",
            "M2 (End program)",
        ]

    def generate_circle(self, center_x: float, center_y: float, radius: float,
                       total_depth: float, is_hole: bool = False) -> List[str]:
        """
        Generate G-code for circular pocket or hole

        Args:
            center_x, center_y: Center coordinates (mm)
            radius: Radius of circle (mm)
            total_depth: Total cutting depth (mm)
            is_hole: True for through holes, False for pockets
        """
        lines = []
        s = self.settings

        lines.append(f"(Circle: center=({center_x:.3f},{center_y:.3f}) radius={radius:.3f} depth={total_depth:.3f})")

        # Calculate number of passes
        num_passes = max(1, int(math.ceil(total_depth / s.step_down)))

        for pass_num in range(1, num_passes + 1):
            current_depth = min(pass_num * s.step_down, total_depth)

            lines.append(f"(Pass {pass_num}/{num_passes}, depth: {current_depth:.3f}mm)")

            # Move to start position (edge of circle)
            start_x = center_x + radius
            start_y = center_y

            lines.append(f"G0 X{start_x:.3f} Y{start_y:.3f}")
            lines.append(f"G1 Z{-current_depth:.3f} F{s.feed_rate_plunge}")

            # Cut circle (counterclockwise)
            lines.append(f"G2 X{start_x:.3f} Y{start_y:.3f} "
                        f"I{-radius:.3f} J0 F{s.feed_rate_cut}")

            lines.append(f"G0 Z{s.safe_height:.3f}")

        lines.append("")
        return lines

    def generate_cam_profile(self, cam_type: str, radius: float, lift: float,
                            thickness: float, shaft_diameter: float) -> List[str]:
        """
        Generate G-code for cam profile cutting

        Args:
            cam_type: 'ECCENTRIC' or 'HEART'
            radius: Cam radius (mm)
            lift: Lift amount (mm)
            thickness: Material thickness (mm)
            shaft_diameter: Shaft hole diameter (mm)
        """
        lines = []
        s = self.settings

        lines.append(f"(Cam Profile: type={cam_type} radius={radius} lift={lift})")
        lines.append("")

        # 1. Cut outer profile
        segments = 64
        points = []

        if cam_type == 'ECCENTRIC':
            # Eccentric cam: circular profile offset from center
            eccentricity = lift
            for i in range(segments + 1):
                angle = 2 * math.pi * i / segments
                x = eccentricity + radius * math.cos(angle)
                y = radius * math.sin(angle)
                points.append((x, y))
        else:  # HEART
            # Heart cam: varying radius
            base_r = radius - lift
            for i in range(segments + 1):
                angle = 2 * math.pi * i / segments
                if angle <= math.pi:
                    r = base_r + lift * (angle / math.pi)
                else:
                    r = radius - lift * ((angle - math.pi) / math.pi)
                x = r * math.cos(angle)
                y = r * math.sin(angle)
                points.append((x, y))

        # Cut profile in multiple passes
        num_passes = max(1, int(math.ceil(thickness / s.step_down)))

        for pass_num in range(1, num_passes + 1):
            current_depth = min(pass_num * s.step_down, thickness)

            lines.append(f"(Outer profile pass {pass_num}/{num_passes}, depth: {current_depth:.3f}mm)")

            # Move to start
            start_x, start_y = points[0]
            lines.append(f"G0 X{start_x:.3f} Y{start_y:.3f}")
            lines.append(f"G1 Z{-current_depth:.3f} F{s.feed_rate_plunge}")

            # Cut along profile
            for x, y in points[1:]:
                lines.append(f"G1 X{x:.3f} Y{y:.3f} F{s.feed_rate_cut}")

            lines.append(f"G0 Z{s.safe_height:.3f}")

        lines.append("")

        # 2. Cut center hole for shaft
        lines.extend(self.generate_circle(0, 0, shaft_diameter / 2, thickness, is_hole=True))

        return lines

    def generate_rectangular_pocket(self, width: float, height: float,
                                   depth: float, corner_radius: float = 0) -> List[str]:
        """
        Generate G-code for rectangular pocket

        Args:
            width, height: Pocket dimensions (mm)
            depth: Pocket depth (mm)
            corner_radius: Radius for rounded corners (mm)
        """
        lines = []
        s = self.settings

        lines.append(f"(Rectangular pocket: {width}x{height}mm, depth={depth}mm)")
        lines.append("")

        # Calculate boundaries
        half_w = width / 2
        half_h = height / 2

        num_passes = max(1, int(math.ceil(depth / s.step_down)))

        for pass_num in range(1, num_passes + 1):
            current_depth = min(pass_num * s.step_down, depth)

            lines.append(f"(Pass {pass_num}/{num_passes}, depth: {current_depth:.3f}mm)")

            # Move to start position
            lines.append(f"G0 X{-half_w:.3f} Y{-half_h:.3f}")
            lines.append(f"G1 Z{-current_depth:.3f} F{s.feed_rate_plunge}")

            # Cut rectangle
            lines.append(f"G1 X{half_w:.3f} Y{-half_h:.3f} F{s.feed_rate_cut}")
            lines.append(f"G1 X{half_w:.3f} Y{half_h:.3f}")
            lines.append(f"G1 X{-half_w:.3f} Y{half_h:.3f}")
            lines.append(f"G1 X{-half_w:.3f} Y{-half_h:.3f}")

            lines.append(f"G0 Z{s.safe_height:.3f}")

        lines.append("")
        return lines

    def generate_contour_cut(self, contours: List[List[Tuple[float, float]]],
                            depth: float, obj_name: str = "", offset: Vector = None) -> List[str]:
        """
        Generate G-code for cutting along 2D contours with tool diameter compensation
        Supports both CNC milling and laser cutting based on machine_type setting

        Args:
            contours: List of contours, each is a list of (x, y) points
            depth: Total cutting depth (mm)
            obj_name: Name of the object (for comments)
            offset: Optional offset to apply to all coordinates (for arranging multiple objects)
        """
        lines = []
        s = self.settings

        if offset is None:
            offset = Vector((0, 0, 0))

        # Check machine type
        is_laser = (s.machine_type == 'LASER')

        if obj_name:
            lines.append(f"(Object: {obj_name})")
        lines.append(f"(Machine Type: {s.machine_type})")
        lines.append(f"(Contours: {len(contours)}, depth: {depth:.3f}mm)")
        lines.append(f"(Tool Diameter: {s.tool_diameter:.3f}mm)")
        if offset.x != 0 or offset.y != 0:
            lines.append(f"(Offset: X{offset.x:.3f} Y{offset.y:.3f})")
        lines.append("")

        if not contours:
            lines.append("(Warning: No contours found)")
            return lines

        # Calculate tool radius for offsetting
        tool_radius = s.tool_diameter / 2.0

        # For laser mode, ignore step_down and use single pass
        # For CNC mode, use multiple passes based on step_down
        if is_laser:
            num_passes = 1
            lines.append(f"(Laser mode: single pass, power controlled by spindle_speed)")
        else:
            num_passes = max(1, int(math.ceil(depth / s.step_down)))
            lines.append(f"(CNC mode: {num_passes} passes, step_down: {s.step_down:.3f}mm)")
        lines.append("")

        for contour_idx, contour in enumerate(contours):
            if len(contour) < 2:
                continue

            lines.append(f"(Contour {contour_idx + 1}/{len(contours)}, points: {len(contour)})")

            # IMPORTANT: Contours are already tool-compensated from Step 2
            # Do NOT apply tool compensation again here (would cause double offset)
            # Just use the contour as-is
            compensated_contour = contour
            lines.append(f"(Tool compensation already applied in visualization step)")

            for pass_num in range(1, num_passes + 1):
                if is_laser:
                    # Laser mode: single pass at material surface (Z=0)
                    current_depth = 0.0
                    lines.append(f"(Pass {pass_num}/{num_passes}, laser cutting at surface)")
                else:
                    # CNC mode: multiple passes with incremental depth
                    current_depth = min(pass_num * s.step_down, depth)
                    lines.append(f"(Pass {pass_num}/{num_passes}, depth: {current_depth:.3f}mm)")

                # SAFETY: Retract to safe height before each pass
                # This ensures safe XY positioning for every pass
                lines.append(f"G0 Z{s.safe_height:.3f} (Retract to safe height)")

                # Move to start position with offset applied
                start_x, start_y = compensated_contour[0]
                lines.append(f"G0 X{start_x + offset.x:.3f} Y{start_y + offset.y:.3f}")

                if is_laser:
                    # Laser mode: Z stays at surface, use spindle_speed as laser power
                    lines.append(f"G0 Z0.000 (Move to material surface)")
                    lines.append(f"M3 S{s.spindle_speed} (Laser ON, power={s.spindle_speed})")
                else:
                    # CNC mode: plunge to depth
                    lines.append(f"G1 Z{-current_depth:.3f} F{s.feed_rate_plunge}")

                # Cut along compensated contour with offset applied
                for x, y in compensated_contour[1:]:
                    lines.append(f"G1 X{x + offset.x:.3f} Y{y + offset.y:.3f} F{s.feed_rate_cut}")

                # Close the contour if needed
                if compensated_contour[0] != compensated_contour[-1]:
                    lines.append(f"G1 X{start_x + offset.x:.3f} Y{start_y + offset.y:.3f} F{s.feed_rate_cut}")

                if is_laser:
                    # Laser mode: turn off laser after cut
                    lines.append(f"M5 (Laser OFF)")
                else:
                    # CNC mode: retract to safe height
                    lines.append(f"G0 Z{s.safe_height:.3f}")

            lines.append("")

        return lines


class LaserGcodeGenerator:
    """Generator for laser cutter G-code"""

    def __init__(self, settings: GcodeSettings):
        self.settings = settings

    def generate_header(self) -> List[str]:
        """Generate G-code header for laser cutter"""
        s = self.settings
        version = get_bl_info_version()
        lines = [
            f"(Laser G-code generated by Craft G-code Generator v{version[0]}.{version[1]})",
            f"(Machine: Laser Cutter)",
            f"(Laser Power: {s.laser_power:.1f}%)",
            f"(Laser Speed: {s.laser_speed:.1f} mm/min)",
            "",
            "G21 (Metric units)",
            "G90 (Absolute positioning)",
            "G17 (XY plane)",
            "M5 (Laser OFF)",
            "G0 Z0 (Set Z to focus height)",
            "",
        ]
        return lines

    def generate_footer(self) -> List[str]:
        """Generate G-code footer for laser cutter"""
        lines = [
            "",
            "(End of program)",
            "M5 (Laser OFF)",
            "G0 X0 Y0 (Return to origin)",
            "M2 (Program end)",
        ]
        return lines

    def generate_contour_cut(self, contours: List[List[Tuple[float, float]]],
                            depth: float, obj_name: str = "", offset: Vector = None) -> List[str]:
        """
        Generate G-code for laser cutting along 2D contours

        Args:
            contours: List of contours, each is a list of (x, y) points
            depth: Ignored for laser (material thickness for reference only)
            obj_name: Name of the object (for comments)
            offset: Optional offset to apply to all coordinates
        """
        lines = []
        s = self.settings

        if offset is None:
            offset = Vector((0, 0, 0))

        if obj_name:
            lines.append(f"(Object: {obj_name})")
        lines.append(f"(Contours: {len(contours)})")
        if offset.x != 0 or offset.y != 0:
            lines.append(f"(Offset: X{offset.x:.3f} Y{offset.y:.3f})")
        lines.append("")

        if not contours:
            lines.append("(Warning: No contours found)")
            return lines

        # Convert laser power percentage to S value (0-100)
        laser_s_value = int(s.laser_power)

        for contour_idx, contour in enumerate(contours):
            if len(contour) < 2:
                lines.append(f"(Skipping contour {contour_idx + 1}: insufficient points)")
                continue

            lines.append(f"(Contour {contour_idx + 1}/{len(contours)}, points: {len(contour)})")

            # Move to start position with laser OFF
            start_x, start_y = contour[0]
            lines.append(f"M5 (Laser OFF)")
            lines.append(f"G0 X{start_x + offset.x:.3f} Y{start_y + offset.y:.3f}")

            # Turn laser ON with specified power
            lines.append(f"M3 S{laser_s_value} (Laser ON at {s.laser_power:.1f}%)")

            # Cut along contour with specified speed
            for x, y in contour[1:]:
                lines.append(f"G1 X{x + offset.x:.3f} Y{y + offset.y:.3f} F{s.laser_speed:.1f}")

            # Close the contour if needed
            if contour[0] != contour[-1]:
                lines.append(f"G1 X{start_x + offset.x:.3f} Y{start_y + offset.y:.3f} F{s.laser_speed:.1f}")

            # Turn laser OFF
            lines.append(f"M5 (Laser OFF)")
            lines.append("")

        return lines
