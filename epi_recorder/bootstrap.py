"""
EPI Recorder Bootstrap - Initialize recording in child process.

This module is loaded via sitecustomize.py in the child process
to set up LLM patching and recording context.
"""

import os
import sys
import atexit
import json
from pathlib import Path

_FINALIZER_REGISTERED = False
_BOOTSTRAP_STDOUT = None
_BOOTSTRAP_STDERR = None
_ORIGINAL_STDOUT = None
_ORIGINAL_STDERR = None


class _BootstrapStreamCapture:
    """Tee stdout/stderr while writing printable lines into bootstrap steps."""

    def __init__(self, context, stream, stream_name: str):
        self._context = context
        self._stream = stream
        self._stream_name = stream_name
        self._buffer = ""

    def write(self, data):
        text = data if isinstance(data, str) else str(data)
        written = self._stream.write(text)
        self._buffer += text

        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._emit_line(line.rstrip("\r"))
        return written

    def flush(self):
        self._stream.flush()

    def writable(self):
        return True

    def isatty(self):
        return bool(getattr(self._stream, "isatty", lambda: False)())

    def fileno(self):
        return self._stream.fileno()

    @property
    def encoding(self):
        return getattr(self._stream, "encoding", None)

    @property
    def errors(self):
        return getattr(self._stream, "errors", None)

    def __getattr__(self, item):
        return getattr(self._stream, item)

    def emit_pending(self):
        if self._buffer:
            self._emit_line(self._buffer.rstrip("\r"))
            self._buffer = ""

    def _emit_line(self, line: str) -> None:
        if not line.strip():
            return

        payload = {
            "stream": self._stream_name,
            "text": line,
        }
        try:
            parsed = json.loads(line)
            if isinstance(parsed, (dict, list)):
                payload["parsed"] = parsed
        except Exception:
            pass

        try:
            self._context.add_step("stdout.print", payload)
        except Exception:
            pass


def _install_stdio_capture(context) -> None:
    """Install bootstrap stdout capture for epi run mode."""
    global _BOOTSTRAP_STDOUT, _ORIGINAL_STDOUT, _ORIGINAL_STDERR

    capture_prints = os.environ.get("EPI_CAPTURE_PRINTS", "1") == "1"
    if not capture_prints or _BOOTSTRAP_STDOUT is not None:
        return

    _ORIGINAL_STDOUT = sys.stdout
    _ORIGINAL_STDERR = sys.stderr
    _BOOTSTRAP_STDOUT = _BootstrapStreamCapture(context, _ORIGINAL_STDOUT, "stdout")
    sys.stdout = _BOOTSTRAP_STDOUT


def _restore_stdio_capture() -> None:
    global _BOOTSTRAP_STDOUT, _BOOTSTRAP_STDERR, _ORIGINAL_STDOUT, _ORIGINAL_STDERR

    if _BOOTSTRAP_STDOUT is not None:
        _BOOTSTRAP_STDOUT.emit_pending()
    if _BOOTSTRAP_STDERR is not None:
        _BOOTSTRAP_STDERR.emit_pending()

    if _ORIGINAL_STDOUT is not None:
        sys.stdout = _ORIGINAL_STDOUT
    if _ORIGINAL_STDERR is not None:
        sys.stderr = _ORIGINAL_STDERR

    _BOOTSTRAP_STDOUT = None
    _BOOTSTRAP_STDERR = None
    _ORIGINAL_STDOUT = None
    _ORIGINAL_STDERR = None


def _finalize_bootstrap_recording() -> None:
    """Finalize bootstrap recording context at process exit."""
    try:
        from epi_recorder.patcher import get_recording_context, set_recording_context
        context = get_recording_context()
        if context is not None:
            _restore_stdio_capture()
            context.finalize()
            set_recording_context(None)
    except Exception:
        # Never fail process shutdown because of cleanup.
        pass


def initialize_recording():
    """
    Initialize EPI recording in child process.
    
    This is called automatically via sitecustomize.py when EPI_RECORD=1.
    """
    # Check if recording is enabled
    if os.environ.get("EPI_RECORD") != "1":
        return
    
    # Get recording parameters from environment
    steps_dir = os.environ.get("EPI_STEPS_DIR")
    enable_redaction = os.environ.get("EPI_REDACT", "1") == "1"
    
    if not steps_dir:
        print("Warning: EPI_STEPS_DIR not set, recording disabled", file=sys.stderr)
        return
    
    steps_path = Path(steps_dir)
    if not steps_path.exists():
        print(f"Warning: Steps directory {steps_path} does not exist", file=sys.stderr)
        return
    
    try:
        # Import recording modules
        from epi_recorder.patcher import RecordingContext, set_recording_context, patch_all
        
        # Create recording context
        context = RecordingContext(steps_path, enable_redaction=enable_redaction)
        set_recording_context(context)
        _install_stdio_capture(context)
        
        # Patch LLM libraries
        patch_all()
        
        global _FINALIZER_REGISTERED
        if not _FINALIZER_REGISTERED:
            atexit.register(_finalize_bootstrap_recording)
            _FINALIZER_REGISTERED = True

        # Optional: Print what was patched (for debugging)
        # for provider, success in patch_results.items():
        #     if success:
        #         print(f"EPI: Patched {provider}", file=sys.stderr)
    
    except Exception as e:
        print(f"Warning: Failed to initialize EPI recording: {e}", file=sys.stderr)


# Auto-initialize if EPI_RECORD is set
if os.environ.get("EPI_RECORD") == "1":
    initialize_recording()



 
