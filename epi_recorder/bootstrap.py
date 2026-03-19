"""
EPI Recorder Bootstrap - Initialize recording in child process.

This module is loaded via sitecustomize.py in the child process
to set up LLM patching and recording context.
"""

import os
import sys
import atexit
from pathlib import Path

_FINALIZER_REGISTERED = False


def _finalize_bootstrap_recording() -> None:
    """Finalize bootstrap recording context at process exit."""
    try:
        from epi_recorder.patcher import get_recording_context, set_recording_context
        context = get_recording_context()
        if context is not None:
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
        
        # Patch LLM libraries
        patch_results = patch_all()
        
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



 
