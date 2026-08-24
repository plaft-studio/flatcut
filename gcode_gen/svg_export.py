"""
SVG Export Module

Generate top-down SVG drawings from preview-scene _Original meshes.
Outer contours and holes are rendered in different colors.
"""

from typing import List, Tuple, Optional

Contour = List[Tuple[float, float]]


def contour_area(contour: Contour) -> float:
    """Signed polygon area (shoelace). Used to identify outer vs hole contours."""
    n = len(contour)
    if n < 3:
        return 0.0
    a = 0.0
    for i in range(n):
        x1, y1 = contour[i]
        x2, y2 = contour[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return abs(a) * 0.5


def _contour_to_svg_path(contour: Contour) -> str:
    """Convert contour to SVG path 'd' attribute. Y is negated (Blender +Y up -> SVG +Y down)."""
    if not contour:
        return ""
    parts = [f"M {contour[0][0]:.3f} {-contour[0][1]:.3f}"]
    for x, y in contour[1:]:
        parts.append(f"L {x:.3f} {-y:.3f}")
    parts.append("Z")
    return " ".join(parts)


def build_svg(
    object_contours: List[List[Contour]],
    plate_rects: List[Tuple[float, float, float, float]],
    stroke_width_mm: float = 0.1,
    margin_mm: float = 5.0,
) -> str:
    """Build an SVG document string.

    Args:
        object_contours: For each object, a list of contours (first is outer by area).
        plate_rects: List of (x, y, width, height) in Blender XY (Y up).
        stroke_width_mm: SVG stroke width.
        margin_mm: Margin around the bounding box.
    """
    all_xs: List[float] = []
    all_ys: List[float] = []
    for contours in object_contours:
        for c in contours:
            for x, y in c:
                all_xs.append(x)
                all_ys.append(y)
    for x, y, w, h in plate_rects:
        all_xs.extend([x, x + w])
        all_ys.extend([y, y + h])

    if not all_xs:
        return ""

    min_x = min(all_xs) - margin_mm
    max_x = max(all_xs) + margin_mm
    min_y = min(all_ys) - margin_mm
    max_y = max(all_ys) + margin_mm

    # SVG Y is flipped: drawn Y range is [-max_y, -min_y]
    view_x = min_x
    view_y = -max_y
    view_w = max_x - min_x
    view_h = max_y - min_y

    lines: List[str] = []
    lines.append('<?xml version="1.0" encoding="UTF-8" standalone="no"?>')
    lines.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
        f'width="{view_w:.3f}mm" height="{view_h:.3f}mm" '
        f'viewBox="{view_x:.3f} {view_y:.3f} {view_w:.3f} {view_h:.3f}">'
    )

    # Plate frames (dashed gray)
    if plate_rects:
        lines.append('  <g id="plates" fill="none" stroke="#999999" '
                     f'stroke-width="{stroke_width_mm:.3f}" stroke-dasharray="2,1">')
        for x, y, w, h in plate_rects:
            lines.append(
                f'    <rect x="{x:.3f}" y="{(-y - h):.3f}" '
                f'width="{w:.3f}" height="{h:.3f}" />'
            )
        lines.append('  </g>')

    # Holes first (so outer overlays them visually)
    lines.append(f'  <g id="holes" fill="none" stroke="#ff0000" stroke-width="{stroke_width_mm:.3f}">')
    for contours in object_contours:
        if len(contours) <= 1:
            continue
        for hole in contours[1:]:
            d = _contour_to_svg_path(hole)
            if d:
                lines.append(f'    <path d="{d}" />')
    lines.append('  </g>')

    lines.append(f'  <g id="outer" fill="none" stroke="#000000" stroke-width="{stroke_width_mm:.3f}">')
    for contours in object_contours:
        if not contours:
            continue
        d = _contour_to_svg_path(contours[0])
        if d:
            lines.append(f'    <path d="{d}" />')
    lines.append('  </g>')

    lines.append('</svg>')
    return "\n".join(lines)


def order_contours(contours: List[Contour]) -> List[Contour]:
    """Return contours sorted so that the largest (outer) comes first."""
    valid = [c for c in contours if len(c) >= 3]
    if not valid:
        return []
    valid.sort(key=contour_area, reverse=True)
    return valid
