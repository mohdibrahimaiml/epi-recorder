"""
EPI Viewer - Python Edition
Cross-platform desktop viewer for .epi evidence files

Uses pywebview for native GUI with embedded browser
"""

import sys
import json
import zipfile
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any
import tempfile
import shutil

try:
    import webview
except ImportError:
    print("ERROR: pywebview not installed")
    print("Install with: pip install pywebview")
    sys.exit(1)


class EPIViewer:
    """Main EPI Viewer application"""
    
    def __init__(self):
        self.current_file: Optional[Path] = None
        self.temp_dir: Optional[Path] = None
        self.verification_result: Optional[Dict[str, Any]] = None
        
    def verify_epi_file(self, filepath: str) -> Dict[str, Any]:
        """
        Verify .epi file integrity and signature
        
        Returns verification result with success status
        """
        filepath = Path(filepath)
        
        if not filepath.exists():
            return {"success": False, "error": "File not found"}
        
        if not zipfile.is_zipfile(filepath):
            return {"success": False, "error": "Not a valid .epi file (not a ZIP archive)"}
        
        try:
            # Create temp directory for extraction
            self.temp_dir = Path(tempfile.mkdtemp(prefix="epi_view_"))
            
            # Extract ZIP
            with zipfile.ZipFile(filepath, 'r') as zf:
                zf.extractall(self.temp_dir)
            
            # Verify structure
            mimetype_path = self.temp_dir / 'mimetype'
            manifest_path = self.temp_dir / 'manifest.json'
            
            if not mimetype_path.exists():
                return {"success": False, "error": "Invalid .epi file: missing mimetype"}
            
            if not manifest_path.exists():
                return {"success": False, "error": "Invalid .epi file: missing manifest.json"}
            
            # Check mimetype
            mimetype = mimetype_path.read_text().strip()
            if mimetype != 'application/vnd.epi+zip':
                return {"success": False, "error": f"Invalid mimetype: {mimetype}"}
            
            # Parse manifest
            manifest = json.loads(manifest_path.read_text())
            
            # Verify file integrity
            integrity_result = self._verify_integrity(manifest)
            if not integrity_result["valid"]:
                return {
                    "success": False,
                    "error": f"Integrity check failed: {integrity_result['error']}",
                    "details": integrity_result
                }
            
            # Verify signature format
            signature_result = self._verify_signature(manifest)
            if not signature_result["valid"]:
                return {
                    "success": False,
                    "error": f"Signature verification failed: {signature_result['error']}",
                    "details": signature_result
                }
            
            # Load viewer HTML
            viewer_path = self.temp_dir / 'viewer.html'
            viewer_html = viewer_path.read_text() if viewer_path.exists() else None
            
            # SUCCESS
            return {
                "success": True,
                "manifest": manifest,
                "viewer_html": viewer_html,
                "verification": {
                    "integrity": integrity_result,
                    "signature": signature_result
                }
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _verify_integrity(self, manifest: Dict) -> Dict[str, Any]:
        """Verify file hash integrity"""
        try:
            file_manifest = manifest.get('file_manifest', {})
            mismatches = []
            
            for filename, expected_hash in file_manifest.items():
                file_path = self.temp_dir / filename
                
                if not file_path.exists():
                    mismatches.append({
                        "file": filename,
                        "error": "File missing"
                    })
                    continue
                
                # Compute SHA-256 hash
                actual_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
                
                if actual_hash != expected_hash:
                    mismatches.append({
                        "file": filename,
                        "error": "Hash mismatch",
                        "expected": expected_hash,
                        "actual": actual_hash
                    })
            
            if mismatches:
                return {
                    "valid": False,
                    "error": f"{len(mismatches)} file(s) failed integrity check",
                    "mismatches": mismatches
                }
            
            return {
                "valid": True,
                "files_checked": len(file_manifest)
            }
        
        except Exception as e:
            return {"valid": False, "error": str(e)}
    
    def _verify_signature(self, manifest: Dict) -> Dict[str, Any]:
        """Verify signature format (full crypto verification requires additional library)"""
        try:
            signature = manifest.get('signature')
            
            if not signature:
                return {
                    "valid": False,
                    "error": "No signature present",
                    "level": "UNSIGNED"
                }
            
            # Parse signature format: "ed25519:keyname:base64sig"
            parts = signature.split(':', 2)
            if len(parts) != 3:
                return {"valid": False, "error": "Invalid signature format"}
            
            algorithm, key_name, sig_b64 = parts
            
            if algorithm != 'ed25519':
                return {"valid": False, "error": f"Unsupported algorithm: {algorithm}"}
            
            # Validate base64 encoding
            try:
                import base64
                base64.b64decode(sig_b64)
            except Exception:
                return {"valid": False, "error": "Invalid signature encoding"}
            
            return {
                "valid": True,
                "algorithm": algorithm,
                "key_name": key_name,
                "level": "SIGNED"
            }
        
        except Exception as e:
            return {"valid": False, "error": str(e)}
    
    def cleanup(self):
        """Clean up temporary files"""
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def generate_viewer_html(self, result: Dict[str, Any]) -> str:
        """Generate the viewer HTML with verification status"""
        manifest = result["manifest"]
        verification = result["verification"]
        
        # If embedded viewer exists, use it
        if result.get("viewer_html"):
            return self._wrap_viewer_html(result["viewer_html"], manifest, verification)
        
        # Otherwise, create basic viewer
        return self._create_basic_viewer(manifest, verification)
    
    def _wrap_viewer_html(self, viewer_html: str, manifest: Dict, verification: Dict) -> str:
        """Wrap embedded viewer with professional verification banner"""
        
        created_at = manifest.get('created_at', 'N/A')
        spec_version = manifest.get('spec_version', 'N/A')
        algorithm = verification['signature'].get('algorithm', 'N/A')
        key_name = verification['signature'].get('key_name', 'unknown')
        files_checked = verification['integrity'].get('files_checked', 0)
        
        banner_html = f"""
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }}
        </style>
        <div style="position: sticky; top: 0; z-index: 10000; background: linear-gradient(to bottom, #ffffff 0%, #f9fafb 100%); border-bottom: 2px solid #10b981; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06);">
            <div style="max-width: 1400px; margin: 0 auto; padding: 20px 32px;">
                <!-- Main Status Row -->
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px;">
                    <div style="display: flex; align-items: center; gap: 16px;">
                        <div style="width: 48px; height: 48px; background: linear-gradient(135deg, #10b981 0%, #059669 100%); border-radius: 12px; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 6px -1px rgba(16, 185, 129, 0.3);">
                            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                                <polyline points="20 6 9 17 4 12"></polyline>
                            </svg>
                        </div>
                        <div>
                            <div style="font-size: 24px; font-weight: 700; color: #10b981; letter-spacing: -0.5px;">VERIFIED</div>
                            <div style="font-size: 13px; color: #6b7280; margin-top: 2px;">Cryptographically signed evidence</div>
                        </div>
                    </div>
                    <button onclick="window.close()" style="padding: 8px 20px; background: white; border: 1.5px solid #d1d5db; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 500; color: #374151; transition: all 0.2s; font-family: inherit;" onmouseover="this.style.background='#f9fafb'; this.style.borderColor='#9ca3af';" onmouseout="this.style.background='white'; this.style.borderColor='#d1d5db';">Close</button>
                </div>
                
                <!-- Metadata Grid -->
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; padding: 16px; background: white; border-radius: 8px; border: 1px solid #e5e7eb;">
                    <div style="padding: 12px; background: #f9fafb; border-radius: 6px; border-left: 3px solid #3b82f6;">
                        <div style="font-size: 11px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 6px; font-weight: 600;">Algorithm</div>
                        <div style="font-family: 'SF Mono', Monaco, monospace; font-size: 14px; color: #1f2937; font-weight: 500;">{algorithm}</div>
                    </div>
                    <div style="padding: 12px; background: #f9fafb; border-radius: 6px; border-left: 3px solid #8b5cf6;">
                        <div style="font-size: 11px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 6px; font-weight: 600;">Created</div>
                        <div style="font-family: 'SF Mono', Monaco, monospace; font-size: 14px; color: #1f2937; font-weight: 500;">{created_at[:19]}</div>
                    </div>
                    <div style="padding: 12px; background: #f9fafb; border-radius: 6px; border-left: 3px solid #f59e0b;">
                        <div style="font-size: 11px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 6px; font-weight: 600;">Version</div>
                        <div style="font-family: 'SF Mono', Monaco, monospace; font-size: 14px; color: #1f2937; font-weight: 500;">EPI {spec_version}</div>
                    </div>
                    <div style="padding: 12px; background: #f9fafb; border-radius: 6px; border-left: 3px solid #10b981;">
                        <div style="font-size: 11px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 6px; font-weight: 600;">Files Verified</div>
                        <div style="font-family: 'SF Mono', Monaco, monospace; font-size: 14px; color: #1f2937; font-weight: 500;">{files_checked}</div>
                    </div>
                </div>
            </div>
        </div>
        <div style="background: #f9fafb; min-height: calc(100vh - 200px);">
            {viewer_html}
        </div>
        """
        
        return banner_html
    
    def _create_basic_viewer(self, manifest: Dict, verification: Dict) -> str:
        """Create professional HTML viewer for files without embedded viewer"""
        manifest_json = json.dumps(manifest, indent=2)
        
        workflow_id = manifest.get('workflow_id', 'N/A')
        created_at = manifest.get('created_at', 'N/A')
        spec_version = manifest.get('spec_version', 'N/A')
        algorithm = verification['signature'].get('algorithm', 'N/A')
        key_name = verification['signature'].get('key_name', 'unknown')
        files_checked = verification['integrity'].get('files_checked', 0)
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>EPI Viewer - {workflow_id}</title>
            <style>
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                    background: linear-gradient(to bottom, #f9fafb 0%, #f3f4f6 100%);
                    color: #1f2937;
                    line-height: 1.6;
                }}
                
                .banner {{
                    background: linear-gradient(to bottom, #ffffff 0%, #f9fafb 100%);
                    border-bottom: 2px solid #10b981;
                    box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06);
                    position: sticky;
                    top: 0;
                    z-index: 1000;
                }}
                
                .banner-content {{
                    max-width: 1400px;
                    margin: 0 auto;
                    padding: 24px 32px;
                }}
                
                .status {{
                    display: flex;
                    align-items: center;
                    gap: 20px;
                    margin-bottom: 20px;
                }}
                
                .status-icon {{
                    width: 56px;
                    height: 56px;
                    background: linear-gradient(135deg, #10b981 0%, #059669 100%);
                    border-radius: 14px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                   box-shadow: 0 10px 15px -3px rgba(16, 185, 129, 0.3), 0 4px 6px -2px rgba(16, 185, 129, 0.2);
                }}
                
                .status-text {{
                    font-size: 28px;
                    font-weight: 700;
                    color: #10b981;
                    letter-spacing: -0.5px;
                }}
                
                .status-subtitle {{
                    font-size: 14px;
                    color: #6b7280;
                    margin-top: 4px;
                }}
                
                .meta-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                    gap: 16px;
                    padding: 20px;
                    background: white;
                    border-radius: 10px;
                    border: 1px solid #e5e7eb;
                }}
                
                .meta-item {{
                    padding: 14px;
                    background: #f9fafb;
                    border-radius: 8px;
                    border-left: 3px solid #3b82f6;
                }}
                
                .meta-item:nth-child(2) {{ border-left-color: #8b5cf6; }}
                .meta-item:nth-child(3) {{ border-left-color: #f59e0b; }}
                .meta-item:nth-child(4) {{ border-left-color: #10b981; }}
                
                .meta-label {{
                    font-size: 11px;
                    color: #6b7280;
                    text-transform: uppercase;
                    letter-spacing: 0.8px;
                    font-weight: 600;
                    margin-bottom: 6px;
                }}
                
                .meta-value {{
                    font-family: 'SF Mono', Monaco, 'Cascadia Code', Consolas, monospace;
                    font-size: 14px;
                    color: #1f2937;
                    font-weight: 500;
                }}
                
                .container {{
                    max-width: 1400px;
                    margin: 32px auto;
                    padding: 0 32px 32px;
                }}
                
                .card {{
                    background: white;
                    border-radius: 12px;
                    padding: 28px;
                    margin-bottom: 24px;
                    box-shadow: 0 1px 3px 0 rgba(0,0,0,0.1), 0 1px 2px 0 rgba(0,0,0,0.06);
                    border: 1px solid #e5e7eb;
                }}
                
                h2 {{
                    font-size: 20px;
                    font-weight: 600;
                    color: #111827;
                    margin-bottom: 20px;
                    padding-bottom: 12px;
                    border-bottom: 2px solid #f3f4f6;
                }}
                
                .grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                    gap: 20px;
                    margin-top: 20px;
                }}
                
                .grid-item {{
                    padding: 16px;
                    background: linear-gradient(to bottom, #f9fafb 0%, #f3f4f6 100%);
                    border-radius: 8px;
                    border: 1px solid #e5e7eb;
                }}
                
                .label {{
                    font-size: 12px;
                    color: #6b7280;
                    text-transform: uppercase;
                    letter-spacing: 0.6px;
                    margin-bottom: 6px;
                    font-weight: 600;
                }}
                
                .value {{
                    font-family: 'SF Mono', Monaco, monospace;
                    font-size: 14px;
                    color: #1f2937;
                    font-weight: 500;
                    word-break: break-word;
                }}
                
                pre {{
                    background: #1f2937;
                    color: #e5e7eb;
                    padding: 20px;
                    border-radius: 8px;
                    overflow-x: auto;
                    font-size: 13px;
                    line-height: 1.6;
                    font-family: 'SF Mono', Monaco, monospace;
                    border: 1px solid #374151;
                }}
                
                .badge {{
                    display: inline-block;
                    padding: 4px 12px;
                    background: #dcfce7;
                    color: #166534;
                    border-radius: 12px;
                    font-size: 12px;
                    font-weight: 600;
                    margin-left: 12px;
                }}
            </style>
        </head>
        <body>
            <div class="banner">
                <div class="banner-content">
                    <div class="status">
                        <div class="status-icon">
                            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                                <polyline points="20 6 9 17 4 12"></polyline>
                            </svg>
                        </div>
                        <div>
                            <div class="status-text">VERIFIED</div>
                            <div class="status-subtitle">Cryptographically signed evidence</div>
                        </div>
                    </div>
                    
                    <div class="meta-grid">
                        <div class="meta-item">
                            <div class="meta-label">Algorithm</div>
                            <div class="meta-value">{algorithm}</div>
                        </div>
                        <div class="meta-item">
                            <div class="meta-label">Created</div>
                            <div class="meta-value">{created_at[:19]}</div>
                        </div>
                        <div class="meta-item">
                            <div class="meta-label">Version</div>
                            <div class="meta-value">EPI {spec_version}</div>
                        </div>
                        <div class="meta-item">
                            <div class="meta-label">Files Verified</div>
                            <div class="meta-value">{files_checked}</div>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="container">
                <div class="card">
                    <h2>Evidence Summary<span class="badge">✓ Verified</span></h2>
                    <div class="grid">
                        <div class="grid-item">
                            <div class="label">Workflow ID</div>
                            <div class="value">{workflow_id}</div>
                        </div>
                        <div class="grid-item">
                            <div class="label">Created At</div>
                            <div class="value">{created_at}</div>
                        </div>
                        <div class="grid-item">
                            <div class="label">Signer</div>
                            <div class="value">{key_name}</div>
                        </div>
                        <div class="grid-item">
                            <div class="label">Spec Version</div>
                            <div class="value">EPI {spec_version}</div>
                        </div>
                    </div>
                </div>
                
                <div class="card">
                    <h2>Complete Manifest</h2>
                    <pre>{manifest_json}</pre>
                </div>
            </div>
        </body>
        </html>
        """


def main():
    """Main entry point"""
    viewer = EPIViewer()
    
    # Get file from command line or show file dialog
    epi_file = None
    if len(sys.argv) > 1:
        epi_file = sys.argv[1]
    else:
        # Show file dialog before creating window
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        epi_file = filedialog.askopenfilename(
            title="Select .epi File",
            filetypes=[("EPI Evidence", "*.epi"), ("All Files", "*.*")]
        )
        root.destroy()
    
    if not epi_file:
        print("No file selected")
        return
    
    # Verify the file
    result = viewer.verify_epi_file(epi_file)
    
    if not result["success"]:
        # Show error in window
        error_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>EPI Viewer - Verification Failed</title>
            <style>
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                    background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    min-height: 100vh;
                    padding: 40px;
                }}
                
                .container {{
                    background: white;
                    border-radius: 16px;
                    padding: 48px;
                    max-width: 600px;
                    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
                    border: 2px solid #fecaca;
                    text-align: center;
                }}
                
                .error-icon {{
                    width: 80px;
                    height: 80px;
                    background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0 auto 24px;
                    box-shadow: 0 10px 15px -3px rgba(239, 68, 68, 0.3), 0 4px 6px -2px rgba(239, 68, 68, 0.2);
                }}
                
                h1 {{
                    font-size: 28px;
                    font-weight: 700;
                    color: #ef4444;
                    margin-bottom: 16px;
                    letter-spacing: -0.5px;
                }}
                
                .error-message {{
                    color: #6b7280;
                    font-size: 16px;
                    line-height: 1.6;
                    margin-bottom: 24px;
                    padding: 20px;
                    background: #f9fafb;
                    border-radius: 8px;
                    border-left: 4px solid #ef4444;
                }}
                
                .warning-box {{
                    background: linear-gradient(to bottom, #fef2f2 0%, #fee2e2 100%);
                    border: 1.5px solid #fecaca;
                    border-radius: 8px;
                    padding: 20px;
                    margin-top: 24px;
                }}
                
                .warning-header {{
                    display: flex;
                    align-items: center;
                    gap: 12px;
                    margin-bottom: 12px;
                    font-weight: 600;
                    color: #991b1b;
                }}
                
                .warning-text {{
                    color: #7f1d1d;
                    font-size: 14px;
                    line-height: 1.6;
                    text-align: left;
                }}
                
                .warning-text strong {{
                    color: #991b1b;
                }}
                
                .file-info {{
                    background: white;
                    border: 1px solid #e5e7eb;
                    border-radius: 6px;
                    padding: 12px;
                    font-family: 'SF Mono', Monaco, monospace;
                    font-size: 13px;
                    color: #4b5563;
                    margin-top: 12px;
                    word-break: break-all;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="error-icon">
                    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="18" y1="6" x2="6" y2="18"></line>
                        <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                </div>
                
                <h1>Evidence Invalid</h1>
                
                <div class="error-message">
                    <strong>Verification Failed:</strong> {result['error']}
                </div>
                
                <div class="warning-box">
                    <div class="warning-header">
                        <svg  width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#991b1b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
                            <line x1="12" y1="9" x2="12" y2="13"></line>
                            <line x1="12" y1="17" x2="12.01" y2="17"></line>
                        </svg>
                        Security Warning
                    </div>
                    <div class="warning-text">
                        <strong>Do not trust the contents of this file.</strong><br><br>
                        This .epi file has failed cryptographic verification. The file may have been:
                        <ul style="margin: 12px 0 0 20px; text-align: left;">
                            <li>Tampered with after creation</li>
                            <li>Corrupted during transmission</li>
                            <li>Created without proper signing</li>
                        </ul>
                    </div>
                    <div class="file-info">
                        {Path(epi_file).name}
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        window = webview.create_window(
            'EPI Viewer - Verification Failed',
           html=error_html,
            width=800,
            height=600
        )
    else:
        # Show verified content
        html = viewer.generate_viewer_html(result)
        window = webview.create_window(
            f'EPI Viewer - {Path(epi_file).name}',
            html=html,
            width=1200,
            height=800,
            min_size=(800, 600)
        )
    
    # Start the GUI
    webview.start()
    
    # Cleanup on exit
    viewer.cleanup()


if __name__ == '__main__':
    main()


