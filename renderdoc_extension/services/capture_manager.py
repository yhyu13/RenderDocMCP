"""
Capture management service for RenderDoc.
"""

import renderdoc as rd


class CaptureManager:
    """Capture management service"""

    def __init__(self, ctx, invoke_fn):
        self.ctx = ctx
        self._invoke = invoke_fn

    def get_capture_status(self):
        """Check if a capture is loaded and get API info"""
        if not self.ctx.IsCaptureLoaded():
            return {"loaded": False}

        result = {"loaded": True, "api": None, "filename": None}

        try:
            result["filename"] = self.ctx.GetCaptureFilename()
        except Exception:
            pass

        # Get API type via replay
        def callback(controller):
            try:
                props = controller.GetAPIProperties()
                result["api"] = str(props.pipelineType)
            except Exception:
                pass

        self._invoke(callback)
        return result

    def list_captures(self, directory):
        """
        List all .rdc files in the specified directory.

        Args:
            directory: Directory path to search

        Returns:
            dict with 'captures' list containing file info
        """
        import os
        import datetime

        # Validate directory exists
        if not os.path.isdir(directory):
            raise ValueError("Directory not found: %s" % directory)

        captures = []

        try:
            for filename in os.listdir(directory):
                if filename.lower().endswith(".rdc"):
                    filepath = os.path.join(directory, filename)
                    if os.path.isfile(filepath):
                        stat = os.stat(filepath)
                        # Format timestamp as ISO 8601
                        mtime = datetime.datetime.fromtimestamp(stat.st_mtime)
                        captures.append({
                            "filename": filename,
                            "path": filepath,
                            "size_bytes": stat.st_size,
                            "modified_time": mtime.isoformat(),
                        })
        except Exception as e:
            raise ValueError("Failed to list directory: %s" % str(e))

        # Sort by modified time (newest first)
        captures.sort(key=lambda x: x["modified_time"], reverse=True)

        return {
            "directory": directory,
            "count": len(captures),
            "captures": captures,
        }

    def open_capture(self, capture_path):
        """
        Open a capture file in RenderDoc.

        Args:
            capture_path: Full path to the .rdc file

        Returns:
            dict with success status and capture info
        """
        import os

        # Validate file exists
        if not os.path.isfile(capture_path):
            raise ValueError("Capture file not found: %s" % capture_path)

        # Validate extension
        if not capture_path.lower().endswith(".rdc"):
            raise ValueError("Invalid file type. Expected .rdc file: %s" % capture_path)

        # Create ReplayOptions with defaults
        opts = rd.ReplayOptions()

        # Open the capture
        # LoadCapture will automatically close any existing capture
        try:
            self.ctx.LoadCapture(
                capture_path,   # captureFile
                opts,           # ReplayOptions
                capture_path,   # origFilename (same as capture path)
                False,          # temporary (False = permanent load)
                True,           # local (True = local file)
            )
        except Exception as e:
            raise ValueError("Failed to open capture: %s" % str(e))

        # Verify the capture was loaded
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("Failed to load capture (unknown error)")

        # Get capture info
        result = {
            "success": True,
            "capture_path": capture_path,
            "filename": os.path.basename(capture_path),
        }

        # Get API type if possible (may require replay thread)
        try:
            api_result = {"api": None}

            def callback(controller):
                try:
                    props = controller.GetAPIProperties()
                    api_result["api"] = str(props.pipelineType)
                except Exception:
                    pass

            self._invoke(callback)
            if api_result["api"]:
                result["api"] = api_result["api"]
        except Exception:
            pass

        return result

    def close_capture(self):
        if not self.ctx.IsCaptureLoaded():
            return {"success": True, "closed": False, "note": "no capture loaded"}
        try:
            self.ctx.CloseCapture()
        except Exception as e:
            raise ValueError("Failed to close capture: %s" % str(e))
        return {"success": True, "closed": True}

    def save_capture(self, capture_path):
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        if not capture_path:
            raise ValueError("capture_path is required")
        try:
            ok = self.ctx.SaveCaptureTo(capture_path)
        except Exception as e:
            raise ValueError("SaveCaptureTo failed: %s" % str(e))
        if ok is False:
            raise ValueError("SaveCaptureTo returned False")
        mods = None
        try:
            mods = str(self.ctx.GetCaptureModifications())
        except Exception:
            mods = None
        return {
            "success": True,
            "path": capture_path,
            "modifications": mods,
            "note": "shader/resource replacements are stored in the saved .rdc",
        }

    def _capture_file(self):
        from ..utils.capture_access import pick_capture_access

        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        cap, reason = pick_capture_access(self.ctx)
        if cap is None:
            raise ValueError(reason)
        return cap

    def _result_details(self, details, what):
        ok = True
        msg = ""
        try:
            ok = bool(details.OK())
            msg = details.Message() if not ok else ""
        except Exception:
            ok = details is not False and details is not None
        if not ok:
            raise ValueError("%s failed: %s" % (what, msg or "unknown"))
        return msg

    def embed_dependencies(self):
        """Embed shader-debug files into the capture (makes debug_* portable)."""
        try:
            details = self.ctx.EmbedDependentFiles()
            self._result_details(details, "EmbedDependentFiles")
            return {
                "success": True,
                "embedded": True,
                "note": "shader debug files stored in the capture; save_capture to persist a copy",
            }
        except Exception:
            pass
        cap = self._capture_file()
        try:
            details = cap.EmbedDependenciesIntoCapture()
        except Exception as e:
            raise ValueError("EmbedDependenciesIntoCapture failed: %s" % str(e))
        self._result_details(details, "EmbedDependenciesIntoCapture")
        return {
            "success": True,
            "embedded": True,
            "note": "shader debug files stored in the capture; save_capture to persist a copy",
        }

    def remove_dependencies(self):
        """Remove previously embedded shader-debug files from the capture."""
        try:
            details = self.ctx.RemoveDependentFiles()
            self._result_details(details, "RemoveDependentFiles")
            return {"success": True, "embedded": False}
        except Exception:
            pass
        cap = self._capture_file()
        try:
            details = cap.RemoveDependenciesFromCapture()
        except Exception as e:
            raise ValueError("RemoveDependenciesFromCapture failed: %s" % str(e))
        self._result_details(details, "RemoveDependenciesFromCapture")
        return {"success": True, "embedded": False}

    def list_capture_formats(self):
        from ..utils.capture_access import pick_capture_access

        formats = []
        items = None
        cap, _reason = pick_capture_access(self.ctx)
        if cap is not None:
            getter = getattr(cap, "GetCaptureFileFormats", None)
            if getter is not None:
                try:
                    items = getter()
                except Exception:
                    items = None
        if items is None:
            try:
                tmp = rd.OpenCaptureFile()
                items = tmp.GetCaptureFileFormats()
                try:
                    tmp.Shutdown()
                except Exception:
                    pass
            except Exception as e:
                raise ValueError("GetCaptureFileFormats unavailable: %s" % str(e))
        for fmt in items:
            formats.append({
                "extension": getattr(fmt, "extension", ""),
                "name": getattr(fmt, "name", ""),
                "open_supported": bool(getattr(fmt, "openSupported", False)),
                "convert_supported": bool(getattr(fmt, "convertSupported", False)),
            })
        return {"count": len(formats), "formats": formats}

    def _find_capture_format(self, want):
        """Return a live CaptureFileFormat whose extension matches `want`."""
        items = None
        cap = None
        try:
            cap = self._capture_file()
        except Exception:
            cap = None
        if cap is not None:
            getter = getattr(cap, "GetCaptureFileFormats", None)
            if getter is not None:
                try:
                    items = getter()
                except Exception:
                    items = None
        tmp = None
        if items is None:
            try:
                tmp = rd.OpenCaptureFile()
                items = tmp.GetCaptureFileFormats()
            except Exception:
                items = None
        found = None
        for item in items or []:
            ext = (getattr(item, "extension", "") or "").lower().lstrip(".")
            if ext == want:
                found = item
                break
        if tmp is not None:
            try:
                tmp.Shutdown()
            except Exception:
                pass
        return found

    def convert_capture(self, filename, filetype="rdc"):
        """Export/convert the open capture to another representation on disk."""
        if not filename:
            raise ValueError("filename is required")
        try:
            cap = self._capture_file()
        except Exception:
            cap = None
        if cap is not None and hasattr(cap, "Convert"):
            try:
                details = cap.Convert(filename, filetype or "rdc", None, None)
            except TypeError:
                details = cap.Convert(filename, filetype or "rdc", None)
            self._result_details(details, "Convert")
        else:
            want = (filetype or "rdc").lower().lstrip(".")
            fmt = self._find_capture_format(want)
            if fmt is None:
                raise ValueError("unknown capture filetype: %s" % filetype)
            try:
                self.ctx.ExportCapture(fmt, filename)
            except Exception as e:
                raise ValueError("ExportCapture failed: %s" % str(e))
        return {
            "success": True,
            "path": filename,
            "filetype": filetype or "rdc",
        }

    def set_event(self, event_id, force=True):
        if not self.ctx.IsCaptureLoaded():
            raise ValueError("No capture loaded")
        try:
            self.ctx.SetEventID([], int(event_id), int(event_id), bool(force))
        except TypeError:
            self.ctx.SetEventID([], int(event_id), int(event_id))
        except Exception as e:
            raise ValueError("SetEventID failed: %s" % str(e))
        return {
            "success": True,
            "event_id": int(event_id),
            "current_event": int(self.ctx.CurEvent()) if hasattr(self.ctx, "CurEvent") else int(event_id),
        }
