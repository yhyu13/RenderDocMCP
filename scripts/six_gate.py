"""Python 3.6-compatibility gate for the RenderDoc extension.

The extension runs inside RenderDoc's embedded Python 3.6 (stdlib only, no
post-3.6 syntax). `ast.parse(feature_version=(3, 6))` rejects walrus / match /
other post-3.6 grammar, but does NOT reject ``X | Y`` annotation unions (parse
as a plain BinOp even in 3.6). This gate does both: a 3.6 grammar parse PLUS a
walk that flags ``BinOp(BitOr)`` used in an annotation position.

Usage (importable, and also exercises the gate in the test suite):
    from six_gate import six_compat_errors
    errors = six_compat_errors(source, "mod.py")
"""

import ast


def _annotation_union(node):
    """Yield every ``a | b`` BinOp reachable from a type-annotation subtree."""
    out = []
    if node is None:
        return out
    stack = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr):
            out.append(n)
            # A union operand may itself be a union; walk both sides.
            stack.append(n.left)
            stack.append(n.right)
            continue
        for child in ast.iter_child_nodes(n):
            stack.append(child)
    return out


def six_compat_errors(source, filename="<string>"):
    """Return a list of (lineno, message) for post-3.6 syntax / annotations."""
    try:
        tree = ast.parse(source, filename=filename, feature_version=(3, 6))
    except SyntaxError as e:
        return [(getattr(e, "lineno", 0), "syntax: %s" % (e.msg or e))]

    errors = []
    for node in ast.walk(tree):
        ann = None
        if isinstance(node, ast.AnnAssign):
            ann = node.annotation
        elif isinstance(node, ast.arg):
            ann = node.annotation
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            ann = node.returns
        if ann is None:
            continue
        for bad in _annotation_union(ann):
            errors.append(
                (
                    getattr(bad, "lineno", 0),
                    "post-3.6 annotation union `|` (not valid in Py3.6): use Optional/Union",
                )
            )

    seen = set()
    uniq = []
    for e in errors:
        if e not in seen:
            seen.add(e)
            uniq.append(e)
    return uniq
