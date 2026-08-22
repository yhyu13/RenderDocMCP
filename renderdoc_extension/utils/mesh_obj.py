"""Tiny OBJ writer. Python 3.6 / no renderdoc import."""


def mesh_to_obj(positions, indices=None):
    """positions: list of [x,y,z,(w)]; indices: optional 0-based triangle list."""
    lines = ["# renderdoc-mcp mesh export"]
    for p in positions or []:
        if not p:
            continue
        x = float(p[0])
        y = float(p[1]) if len(p) > 1 else 0.0
        z = float(p[2]) if len(p) > 2 else 0.0
        lines.append("v %s %s %s" % (x, y, z))
    if indices and len(indices) >= 3:
        n = len(positions or [])
        i = 0
        while i + 2 < len(indices):
            a, b, c = int(indices[i]), int(indices[i + 1]), int(indices[i + 2])
            if 0 <= a < n and 0 <= b < n and 0 <= c < n:
                lines.append("f %d %d %d" % (a + 1, b + 1, c + 1))
            i += 3
    return "\n".join(lines) + "\n"
