"""
Groove Detection Module

Measures the V-grooves carved into a flat board and the board's true outline,
from the mesh alone.

A grooved board's faces sort by their normal: +-Z are the top and bottom
faces (and the floors of grooves that stop short of the far face), normals
perpendicular to Z are the outline's side walls, and everything tilted in
between is a groove wall. Coplanar, connected tilted faces make one wall; two
walls facing each other across a floor (or meeting in a ridge) make one
groove. Every groove is a straight prism, so it comes down to one centre line,
the width of its mouth and its depth.

The outline cannot be read off any single face: the grooves split the face
they open into, and a groove that runs off the edge of the board takes a notch
out of the side walls too. A horizontal section at a height no groove reaches
is the outline as it is, so that is where it is taken.

World units are treated as millimetres, like the rest of flatcut.
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import bmesh
from mathutils import Vector

Point2 = Tuple[float, float]


@dataclass
class Groove:
    """One straight groove, as a V-bit would cut it"""
    start: Point2          # centre line at the mouth, first end
    end: Point2            # centre line at the mouth, second end
    width: float           # width of the mouth
    depth: float           # from the face the groove opens into to its deepest point
    from_top: bool         # opens into the top face (False: the bottom face)
    closed_start: bool = False  # this end stops inside the board rather than running out
    closed_end: bool = False
    floor_width: float = 0.0    # width of the flat floor at its deepest point (0: a sharp V)

    @property
    def length(self) -> float:
        return math.hypot(self.end[0] - self.start[0], self.end[1] - self.start[1])


@dataclass
class GroovedBoard:
    """What was measured on one board"""
    z_bottom: float
    z_top: float
    grooves: List[Groove]
    outline: List[List[Point2]]      # closed contours, first point not repeated
    section_z: Optional[float]       # where the outline was taken
    warnings: List[str] = field(default_factory=list)

    @property
    def thickness(self) -> float:
        return self.z_top - self.z_bottom

    @property
    def front_grooves(self) -> List[Groove]:
        return [g for g in self.grooves if g.from_top]

    @property
    def back_grooves(self) -> List[Groove]:
        return [g for g in self.grooves if not g.from_top]


class _Wall:
    """A connected set of coplanar tilted faces"""

    def __init__(self, faces, keys):
        area = sum(f.calc_area() for f in faces)
        normal = Vector((0.0, 0.0, 0.0))
        centre = Vector((0.0, 0.0, 0.0))
        for f in faces:
            a = f.calc_area()
            normal += f.normal * a
            centre += f.calc_center_median() * a
        self.normal = normal.normalized()
        self.point = centre / area if area > 0 else faces[0].verts[0].co.copy()
        self.coords = [v.co.copy() for f in faces for v in f.verts]
        self.keys = keys
        self.from_top = self.normal.z > 0
        horizontal = Vector((self.normal.x, self.normal.y))
        self.h_len = horizontal.length
        self.h = horizontal / self.h_len          # points into the groove, at the mouth
        self.axis = Vector((-self.h.y, self.h.x))
        self.d = self.normal.dot(self.point)

    def u_at(self, z: float) -> float:
        """Where the wall's plane is at height z, measured along h"""
        return (self.d - self.normal.z * z) / self.h_len

    def extent(self, axis: Vector) -> Tuple[float, float]:
        s = [axis.dot(Vector((c.x, c.y))) for c in self.coords]
        return min(s), max(s)


def _key(co, tol):
    return (round(co.x / tol), round(co.y / tol), round(co.z / tol))


def _world_bmesh(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    bm.normal_update()
    return bm


def _components(faces, joined):
    """Split faces into groups connected through edges for which joined(f1, f2) holds"""
    parent = {f: f for f in faces}

    def find(f):
        while parent[f] is not f:
            parent[f] = parent[parent[f]]
            f = parent[f]
        return f

    face_set = set(faces)
    for f in faces:
        for e in f.edges:
            for g in e.link_faces:
                if g is not f and g in face_set and joined(f, g):
                    parent[find(f)] = find(g)
    groups = {}
    for f in faces:
        groups.setdefault(find(f), []).append(f)
    return list(groups.values())


def _point_in_contours(contours, p: Point2) -> bool:
    """Even-odd rule"""
    inside = False
    x, y = p
    for contour in contours:
        n = len(contour)
        for i in range(n):
            x1, y1 = contour[i]
            x2, y2 = contour[i - 1]
            if (y1 > y) == (y2 > y):
                continue
            cross = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < cross:
                inside = not inside
    return inside


def _chain(segments, tol) -> List[List[Point2]]:
    """Join undirected 2D segments into closed loops"""
    def k(p):
        return (round(p[0] / tol), round(p[1] / tol))

    adjacency = {}
    points = {}
    for a, b in segments:
        ka, kb = k(a), k(b)
        if ka == kb:
            continue
        points[ka], points[kb] = a, b
        adjacency.setdefault(ka, []).append(kb)
        adjacency.setdefault(kb, []).append(ka)

    used = set()
    loops = []
    for start in adjacency:
        for first in adjacency[start]:
            if frozenset((start, first)) in used:
                continue
            loop = [start]
            prev, cur = start, first
            used.add(frozenset((start, first)))
            while cur != start:
                loop.append(cur)
                nxt = next((n for n in adjacency[cur]
                            if n != prev and frozenset((cur, n)) not in used), None)
                if nxt is None:
                    break
                used.add(frozenset((cur, nxt)))
                prev, cur = cur, nxt
            if cur == start and len(loop) >= 3:
                loops.append([points[p] for p in loop])
    return loops


def _drop_collinear(contour, tol):
    out = []
    n = len(contour)
    for i in range(n):
        ax, ay = contour[i - 1]
        bx, by = contour[i]
        cx, cy = contour[(i + 1) % n]
        cross = (bx - ax) * (cy - by) - (by - ay) * (cx - bx)
        span = math.hypot(cx - ax, cy - ay)
        if span > 0 and abs(cross) / span < tol:
            continue
        out.append((bx, by))
    return out if len(out) >= 3 else contour


def _section(obj, z, tol) -> List[List[Point2]]:
    """Horizontal section of the object at height z, as closed loops"""
    bm = _world_bmesh(obj)
    result = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                                    dist=tol * 0.1, plane_co=(0, 0, z), plane_no=(0, 0, 1))
    segments = []
    for e in result["geom_cut"]:
        if isinstance(e, bmesh.types.BMEdge):
            a, b = e.verts
            if abs(a.co.z - z) < tol and abs(b.co.z - z) < tol:
                segments.append(((a.co.x, a.co.y), (b.co.x, b.co.y)))
    bm.free()
    return [_drop_collinear(c, tol) for c in _chain(segments, tol)]


class _Snapper:
    """Maps points to the first point seen within dist of them"""

    def __init__(self, dist):
        self.dist = dist
        self.cells = {}

    def __call__(self, p):
        cx, cy = int(math.floor(p[0] / self.dist)), int(math.floor(p[1] / self.dist))
        for i in (cx - 1, cx, cx + 1):
            for j in (cy - 1, cy, cy + 1):
                for q in self.cells.get((i, j), ()):
                    if math.hypot(q[0] - p[0], q[1] - p[1]) <= self.dist:
                        return q
        self.cells.setdefault((cx, cy), []).append(p)
        return p


def _face_union(faces, tol) -> List[List[Point2]]:
    """Boundary of the union of coplanar, consistently wound faces

    Faces that only touch along a line (the two sides of a groove cut to the far face)
    may not share vertices there, so every edge is first split at any vertex lying on it;
    then each edge that is walked both ways is inside the union and cancels out.
    """
    # The solver leaves the corners where several pieces meet a few thousandths of a
    # millimetre apart, which rounding to a grid can put either side of a cell boundary:
    # gather each such cluster into one point instead.
    snap = _Snapper(10 * tol)
    loops = []
    for f in faces:
        loop = []
        for v in f.verts:
            p = snap((v.co.x, v.co.y))
            if not loop or loop[-1] != p:
                loop.append(p)
        if len(loop) > 1 and loop[0] == loop[-1]:
            loop.pop()
        if len(loop) >= 3:
            loops.append(loop)

    def k(p):
        return p

    all_points = {p: p for loop in loops for p in loop}

    edges = {}
    for loop in loops:
        for i in range(len(loop)):
            a, b = loop[i], loop[(i + 1) % len(loop)]
            ab = (b[0] - a[0], b[1] - a[1])
            length2 = ab[0] ** 2 + ab[1] ** 2
            if length2 < tol * tol:
                continue
            on = []
            for p in all_points.values():
                t = ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / length2
                if t <= 0 or t >= 1:
                    continue
                dx, dy = a[0] + ab[0] * t - p[0], a[1] + ab[1] * t - p[1]
                if dx * dx + dy * dy < snap.dist * snap.dist:
                    on.append((t, p))
            chain = [a] + [p for _, p in sorted(on)] + [b]
            for p, q in zip(chain, chain[1:]):
                kp, kq = k(p), k(q)
                if kp == kq:
                    continue
                if (kq, kp) in edges:
                    del edges[(kq, kp)]
                else:
                    edges[(kp, kq)] = (p, q)
    return [_drop_collinear(c, tol) for c in _chain(list(edges.values()), tol)]


def detect_grooves(obj, angle_tol_deg: float = 1.0) -> GroovedBoard:
    """Measure the grooves and the outline of a flat board lying in the XY plane"""
    bm = _world_bmesh(obj)
    zs = [v.co.z for v in bm.verts]
    z_bottom, z_top = min(zs), max(zs)
    thickness = z_top - z_bottom
    tol = max(1e-4, 1e-3 * thickness)
    key_tol = tol * 0.1
    cos_tol = math.cos(math.radians(angle_tol_deg))
    warnings = []

    tilted, floors, far_faces = [], [], {True: [], False: []}
    for f in bm.faces:
        nz = f.normal.z
        if abs(nz) > cos_tol:
            z = f.calc_center_median().z
            if abs(z - z_top) < tol:
                far_faces[False].append(f)     # the far face of back grooves
            elif abs(z - z_bottom) < tol:
                far_faces[True].append(f)      # the far face of front grooves
            else:
                floors.append(f)
        elif abs(nz) > math.sin(math.radians(angle_tol_deg)):
            tilted.append(f)

    def coplanar(f, g):
        return (f.normal.dot(g.normal) > cos_tol
                and abs(f.normal.dot(g.calc_center_median() - f.calc_center_median())) < tol)

    walls = []
    for group in _components(tilted, coplanar):
        keys = {_key(v.co, key_tol) for f in group for v in f.verts}
        walls.append(_Wall(group, keys))
    floor_groups = _components(floors, lambda f, g: True)
    floor_keys = [{_key(v.co, key_tol) for f in group for v in f.verts} for group in floor_groups]
    floor_z = [min(v.co.z for f in group for v in f.verts) for group in floor_groups]

    def mouth_z(wall):
        return z_top if wall.from_top else z_bottom

    def far_z(wall):
        return z_bottom if wall.from_top else z_top

    # A wall opens into the face it faces: one that leans downward but starts at the top
    # face is no back groove's wall. Such faces are the ends of grooves that stop short:
    # paper-model closes them with a face across the groove, and where the two guide lines
    # beside the crease end unevenly that face is not upright but leans either way.
    walls = [w for w in walls if any(abs(c.z - mouth_z(w)) < tol for c in w.coords)]

    def is_end_face(x):
        """Spans the gap between two opposite walls it touches, and goes no further"""
        touching = [w for w in walls if w is not x and x.keys & w.keys]
        for c in touching:
            for d in touching:
                if c.h.dot(d.h) > -cos_tol or c.from_top != d.from_top:
                    continue
                mz = mouth_z(c)
                lo, hi = sorted((c.u_at(mz), -d.u_at(mz)))
                us = [c.h.dot(Vector((p.x, p.y))) for p in x.coords]
                if lo - tol <= min(us) and max(us) <= hi + tol:
                    return True
        return False

    walls = [w for w in walls if not is_end_face(w)]

    def overlap(a, b):
        a0, a1 = a.extent(a.axis)
        b0, b1 = b.extent(a.axis)
        return min(a1, b1) - max(a0, b0) > -tol

    def deepest_keys(w):
        if w.from_top:
            z = min(c.z for c in w.coords)
            return {_key(c, key_tol) for c in w.coords if c.z < z + tol}
        z = max(c.z for c in w.coords)
        return {_key(c, key_tol) for c in w.coords if c.z > z - tol}

    def neighbours(a, b):
        """How a and b are joined across a groove: 0 by a ridge or a common floor, 1 only by
        meeting in one crease at the far face, None not at all

        Touching anywhere else is not enough: the end face of another groove can lean
        against a wall and face it as squarely as the wall's real partner does, and its
        plane can even pass through the same crease, so a wall that shares the groove's
        floor or ridge always wins over one that only lines up with it.
        """
        if deepest_keys(a) & deepest_keys(b):
            return 0
        if any(a.keys & fk and b.keys & fk for fk in floor_keys):
            return 0
        if abs(a.u_at(far_z(a)) + b.u_at(far_z(b))) < tol:
            return 1
        return None

    # each wall pairs with the nearest wall facing it across the groove, but never with one
    # that is joined more firmly to another
    choice = {}
    for i, a in enumerate(walls):
        best, best_rank = None, None
        for j, b in enumerate(walls):
            if i == j or a.from_top != b.from_top or a.h.dot(b.h) > -cos_tol:
                continue
            gap = -b.u_at(mouth_z(b)) - a.u_at(mouth_z(a))
            if gap <= tol or not overlap(a, b):
                continue
            joined = neighbours(a, b)
            if joined is None:
                continue
            if best_rank is None or (joined, gap) < best_rank:
                best, best_rank = j, (joined, gap)
        if best is not None:
            choice[i] = (best, best_rank[0])
    pairs = set()
    paired = set()
    for i, (j, joined) in choice.items():
        if joined > choice.get(j, (None, joined))[1]:
            continue
        pairs.add((min(i, j), max(i, j)))
        paired.update((i, j))

    raw = []
    for i, j in sorted(pairs):
        a, b = walls[i], walls[j]
        mz = mouth_z(a)
        lo, hi = a.u_at(mz), -b.u_at(mz)
        centre_u, width = (lo + hi) / 2, hi - lo
        deepest = [c.z for c in a.coords + b.coords]
        deepest += [z for fk, z in zip(floor_keys, floor_z) if a.keys & fk and b.keys & fk]
        zd = min(deepest) if a.from_top else max(deepest)
        floor = max(0.0, -b.u_at(zd) - a.u_at(zd))
        raw.append((a, centre_u, width, a.extent(a.axis), b.extent(a.axis), deepest, floor, False))

    for i, a in enumerate(walls):
        if i in paired:
            continue
        # a wall with nothing facing it: the groove runs along a cut edge of the board,
        # the other half of it is air. Its centre is where the wall reaches the far face.
        mz = mouth_z(a)
        far = a.u_at(far_z(a))
        width = 2 * (far - a.u_at(mz))
        deepest = [c.z for c in a.coords]
        raw.append((a, far, width, a.extent(a.axis), a.extent(a.axis), deepest, 0.0, True))

    grooves, lone = [], []
    for a, centre_u, width, ext_a, ext_b, zs_deep, floor, alone in raw:
        s0, s1 = min(ext_a[0], ext_b[0]), max(ext_a[1], ext_b[1])
        if a.from_top:
            depth = z_top - min(zs_deep)
        else:
            depth = max(zs_deep) - z_bottom
        base = a.h * centre_u
        p0, p1 = base + a.axis * s0, base + a.axis * s1
        g = Groove((p0.x, p0.y), (p1.x, p1.y), width, depth, a.from_top, floor_width=floor)
        (lone if alone else grooves).append(g)
    grooves = _merge_collinear(grooves, tol, cos_tol)
    grooves = _bridge_crossings(grooves, tol, cos_tol)

    # A wall with nothing facing it is a groove along a cut edge of the board, whose other
    # half is air, only if its centre line is that edge. Anything else is a stray tilted
    # face, such as the end of a groove cut off by another one.
    outline, section_z = _outline(obj, grooves + lone, z_bottom, z_top, far_faces, tol, [])
    if not outline:
        outline, section_z = _outline(obj, grooves, z_bottom, z_top, far_faces, tol, warnings)
    edge_tol = max(0.02 * thickness, 10 * tol)
    for g in lone:
        mid = ((g.start[0] + g.end[0]) / 2, (g.start[1] + g.end[1]) / 2)
        if outline and all(_distance_to_contours(outline, p) < edge_tol for p in (g.start, mid, g.end)):
            grooves.append(g)
        else:
            warnings.append(f"Ignored a tilted face at ({mid[0]:.2f}, {mid[1]:.2f}): no groove wall faces it "
                            "and it does not run along the board's edge")
    bm.free()

    if outline:
        step = max(0.05 * thickness, 10 * tol)
        for g in grooves:
            if g.length < tol:
                continue
            ux = (g.end[0] - g.start[0]) / g.length
            uy = (g.end[1] - g.start[1]) / g.length
            # an end is closed when there is board beyond it; running into another groove's
            # mouth is not board
            for attr, p in (("closed_start", (g.start[0] - ux * step, g.start[1] - uy * step)),
                            ("closed_end", (g.end[0] + ux * step, g.end[1] + uy * step))):
                setattr(g, attr, _point_in_contours(outline, p)
                        and not any(o is not g and o.from_top == g.from_top and _in_mouth(o, p, tol)
                                    for o in grooves))

    return GroovedBoard(z_bottom, z_top, grooves, outline, section_z, warnings)


def _distance_to_contours(contours, p) -> float:
    best = float('inf')
    for contour in contours:
        for i in range(len(contour)):
            ax, ay = contour[i - 1]
            bx, by = contour[i]
            dx, dy = bx - ax, by - ay
            length2 = dx * dx + dy * dy
            t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / length2))
            best = min(best, math.hypot(ax + dx * t - p[0], ay + dy * t - p[1]))
    return best


def _outline(obj, grooves, z_bottom, z_top, far_faces, tol, warnings):
    """The board's outline: a section clear of every groove, or else the far face of
    grooves that all open on one side"""
    top_reach = min([z_top - g.depth for g in grooves if g.from_top], default=z_top)
    bottom_reach = max([z_bottom + g.depth for g in grooves if not g.from_top], default=z_bottom)
    section_z = None
    if bottom_reach < top_reach - 2 * tol:
        section_z = (bottom_reach + top_reach) / 2
        outline = _section(obj, section_z, tol)
    elif not any(not g.from_top for g in grooves):
        section_z = z_bottom
        outline = _face_union(far_faces[True], tol)
    elif not any(g.from_top for g in grooves):
        section_z = z_top
        outline = _face_union(far_faces[False], tol)
    else:
        outline = []
        warnings.append("Front and back grooves overlap in depth: no height is clear of all "
                        "of them, so the outline could not be measured")
    return outline, section_z


def _merge_collinear(grooves, tol, cos_tol):
    """Pieces of one groove (split where another groove crosses it) back into one"""
    merged = []
    for g in grooves:
        dx, dy = g.end[0] - g.start[0], g.end[1] - g.start[1]
        length = math.hypot(dx, dy)
        if length < tol:
            continue
        ux, uy = dx / length, dy / length
        for m in merged:
            mx, my = m.end[0] - m.start[0], m.end[1] - m.start[1]
            ml = math.hypot(mx, my)
            vx, vy = mx / ml, my / ml
            if (m.from_top != g.from_top or abs(ux * vx + uy * vy) < cos_tol
                    or abs(m.width - g.width) > 10 * tol):
                continue
            # distance of g's ends from m's line
            off = [abs((p[0] - m.start[0]) * -vy + (p[1] - m.start[1]) * vx) for p in (g.start, g.end)]
            if max(off) > 10 * tol:
                continue
            ts = [((p[0] - m.start[0]) * vx + (p[1] - m.start[1]) * vy) for p in (g.start, g.end)]
            lo, hi = min(ts), max(ts)
            if lo > ml + tol or hi < -tol:
                continue
            lo, hi = min(lo, 0.0), max(hi, ml)
            m.start = (m.start[0] + vx * lo, m.start[1] + vy * lo)
            m.end = (m.start[0] + vx * (hi - lo), m.start[1] + vy * (hi - lo))
            m.depth = max(m.depth, g.depth)
            break
        else:
            merged.append(g)
    return merged


def _in_mouth(g, p, tol) -> bool:
    """Whether point p lies within the groove's mouth, seen from above"""
    length = g.length
    if length < tol:
        return False
    ux, uy = (g.end[0] - g.start[0]) / length, (g.end[1] - g.start[1]) / length
    rx, ry = p[0] - g.start[0], p[1] - g.start[1]
    along = rx * ux + ry * uy
    across = abs(-rx * uy + ry * ux)
    return -tol <= along <= length + tol and across <= g.width / 2 + tol


def _bridge_crossings(grooves, tol, cos_tol):
    """Rejoin the pieces of a groove that another, deeper groove cuts clean through

    Where a shallower groove crosses a deeper one, its walls are gone for the width of the
    deeper groove, so it is measured as two pieces with a gap between them. That gap is
    inside the other groove's mouth; the bit can run straight through it.
    """
    changed = True
    while changed:
        changed = False
        for i, a in enumerate(grooves):
            for j, b in enumerate(grooves):
                if i == j or a.from_top != b.from_top or abs(a.width - b.width) > 10 * tol:
                    continue
                la, lb = a.length, b.length
                if la < tol or lb < tol:
                    continue
                ux, uy = (a.end[0] - a.start[0]) / la, (a.end[1] - a.start[1]) / la
                vx, vy = (b.end[0] - b.start[0]) / lb, (b.end[1] - b.start[1]) / lb
                if abs(ux * vx + uy * vy) < cos_tol:
                    continue
                ts = [((p[0] - a.start[0]) * ux + (p[1] - a.start[1]) * uy) for p in (b.start, b.end)]
                off = [abs(-(p[0] - a.start[0]) * uy + (p[1] - a.start[1]) * ux) for p in (b.start, b.end)]
                if max(off) > 10 * tol or min(ts) < la:
                    continue  # not on a's line, or not beyond a's end
                gap_mid = ((la + min(ts)) / 2)
                mid = (a.start[0] + ux * gap_mid, a.start[1] + uy * gap_mid)
                if not any(o is not a and o is not b and o.from_top == a.from_top
                           and _in_mouth(o, mid, tol) for o in grooves):
                    continue
                far = max(ts)
                a.end = (a.start[0] + ux * far, a.start[1] + uy * far)
                a.depth = max(a.depth, b.depth)
                del grooves[j]
                changed = True
                break
            if changed:
                break
    return grooves
