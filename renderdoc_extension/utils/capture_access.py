"""Pick a CaptureFile / CaptureAccess handle. Python 3.6, duck-typed, no renderdoc.

Live MCP LoadCapture: CaptureContext.GetCaptureFile is missing/None.
The handle lives on ReplayManager: ctx.Replay().GetCaptureAccess()
or ctx.Replay().GetCaptureFile().
"""


def pick_capture_access(ctx):
    """Return (handle, source_name) or (None, reason)."""
    if ctx is None:
        return None, "no capture context"
    try:
        if not ctx.IsCaptureLoaded():
            return None, "no capture loaded"
    except Exception:
        pass

    replay = None
    try:
        replay = ctx.Replay()
    except Exception:
        replay = None

    if replay is not None:
        for method in ("GetCaptureAccess", "GetCaptureFile"):
            try:
                handle = getattr(replay, method)()
            except Exception:
                handle = None
            if handle is not None:
                return handle, "replay." + method

    for method in ("GetCaptureFile", "GetCaptureAccess"):
        try:
            handle = getattr(ctx, method)()
        except Exception:
            handle = None
        if handle is not None:
            return handle, "ctx." + method

    return None, "GetCaptureFile unavailable (ReplayManager handle is None)"
