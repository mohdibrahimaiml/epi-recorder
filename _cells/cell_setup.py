# @title Install EPI Recorder { display-mode: "form" }
import sys, os, subprocess
from IPython.display import clear_output, display, HTML

# Install EPI Recorder
print("Installing EPI Recorder...")
subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "--upgrade",
                       "epi-recorder", "google-generativeai"])
clear_output()

import epi_recorder
print("=" * 65)
display(HTML(f'''
<div style="background: #0f172a; padding: 24px 30px; border-radius: 12px;
            font-family: -apple-system, sans-serif; color: white;">
  <h2 style="color: #34d399; margin: 0 0 12px 0;">
    ✅  EPI Recorder {epi_recorder.__version__} — Ready
  </h2>
  <p style="color: #94a3b8; margin: 0; font-size: 14px;">
    Evidence Packaged Infrastructure · Cryptographic AI Evidence
  </p>
</div>
'''))
print("=" * 65)

# Try to load an API key (optional — demo works without it)
api_key = None
try:
    from google.colab import userdata
    api_key = userdata.get('GOOGLE_API_KEY')
except Exception:
    pass

if not api_key:
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")

if api_key:
    os.environ["GOOGLE_API_KEY"] = api_key
    display(HTML('<p style="color: #34d399; font-weight: bold; margin: 8px 0;">🔑 API Key Found — Live Gemini mode enabled</p>'))
else:
    display(HTML('''
<div style="background: #1c1917; border-left: 4px solid #f59e0b;
            padding: 16px 20px; border-radius: 8px; margin: 12px 0;">
  <h4 style="color: #fbbf24; margin: 0 0 8px 0;">⚡ Demo Mode (no API key needed)</h4>
  <p style="color: #a8a29e; margin: 0; font-size: 14px;">
    The full demo runs with simulated AI responses.<br>
    To enable live Gemini calls: add <code>GOOGLE_API_KEY</code> in the Colab sidebar (🔑 icon).
  </p>
</div>
'''))
