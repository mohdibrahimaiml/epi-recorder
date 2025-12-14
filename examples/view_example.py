#!/usr/bin/env python3
"""
Example of viewing an EPI file in browser
"""

import webbrowser
import tempfile
import zipfile
from pathlib import Path

def view_epi_file(epi_file_path):
    """Extract and open the EPI file viewer in browser"""
    epi_path = Path(epi_file_path)
    
    if not epi_path.exists():
        print(f"❌ EPI file not found: {epi_path}")
        return
    
    try:
        # Create temp directory for viewer
        temp_dir = Path(tempfile.mkdtemp(prefix="epi_view_"))
        viewer_path = temp_dir / "viewer.html"
        
        # Extract viewer.html
        with zipfile.ZipFile(epi_path, "r") as zf:
            if "viewer.html" not in zf.namelist():
                print("❌ No viewer found in .epi file")
                return
            
            # Extract viewer
            zf.extract("viewer.html", temp_dir)
        
        # Open in browser
        file_url = viewer_path.as_uri()
        print(f"🌐 Opening viewer: {file_url}")
        
        success = webbrowser.open(file_url)
        
        if success:
            print("✅ Viewer opened in browser")
        else:
            print("⚠️  Could not open browser automatically")
            print(f"Open manually: {file_url}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    # View our example EPI file
    view_epi_file("my_complete_example.epi")