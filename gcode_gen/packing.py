"""
Bin Packing Module

Packs 2D rectangles into a given work area using a shelf-based Bottom-Left algorithm.
Supports multiple plates when objects don't fit in a single area.
Rotation is handled externally before calling pack functions.
"""

import math
from typing import List, Tuple


def _pack_single_plate(items, area_width, area_height, spacing):
    """
    Try to pack items into a single plate using shelf-based BL.
    Items must already have 'packed_width' and 'packed_height' set.

    Returns (placed_items, unplaced_items).
    """
    shelves = []  # [(y, height, next_x)]
    placed = []
    unplaced = []

    for item in items:
        iw = item['packed_width'] + spacing
        ih = item['packed_height'] + spacing
        item_placed = False

        # Try to fit on existing shelves (best-fit by wasted height)
        best_shelf_idx = None
        best_remaining = float('inf')

        for si, (sy, sh, sx) in enumerate(shelves):
            if sx + iw <= area_width + spacing and ih <= sh + 0.01:
                remaining = sh - ih
                if remaining < best_remaining:
                    best_remaining = remaining
                    best_shelf_idx = si

        if best_shelf_idx is not None:
            sy, sh, sx = shelves[best_shelf_idx]
            item['x'] = sx
            item['y'] = sy
            item['placed'] = True
            shelves[best_shelf_idx] = (sy, sh, sx + iw)
            item_placed = True
        else:
            # Create new shelf
            new_y = shelves[-1][0] + shelves[-1][1] if shelves else 0.0

            if new_y + ih <= area_height + spacing and iw <= area_width + spacing:
                item['x'] = 0.0
                item['y'] = new_y
                item['placed'] = True
                shelves.append((new_y, ih, iw))
                item_placed = True

        if item_placed:
            placed.append(item)
        else:
            item['placed'] = False
            unplaced.append(item)

    return placed, unplaced


def pack_objects_bl(items: List[dict], area_width: float, area_height: float,
                    spacing: float) -> List[dict]:
    """
    Pack items into work area(s) using shelf-based Bottom-Left.
    Automatically creates multiple plates if items don't fit in one.

    Each item must have:
        'index': original index
        'packed_width': width (already rotated if needed)
        'packed_height': height (already rotated if needed)
        'angle': rotation angle applied (for reference)

    Returns items with added keys:
        'x': placed X position (within plate)
        'y': placed Y position (within plate)
        'placed': True if successfully placed
        'plate': plate index (0-based)
    """
    # Sort by height descending (tall items first for better packing)
    pack_items = sorted(items, key=lambda d: d['packed_height'], reverse=True)

    remaining = pack_items
    plate_idx = 0

    while remaining:
        for item in remaining:
            item['placed'] = False

        placed, unplaced = _pack_single_plate(remaining, area_width, area_height, spacing)

        for item in placed:
            item['plate'] = plate_idx

        if not placed and unplaced:
            # Nothing could be placed — items too large
            for item in unplaced:
                item['x'] = 0.0
                item['y'] = 0.0
                item['placed'] = False
                item['plate'] = plate_idx
            break

        remaining = unplaced
        plate_idx += 1

    return pack_items
