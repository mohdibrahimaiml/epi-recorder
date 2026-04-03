# @title Download Offline Viewer { display-mode: "form" }
from pathlib import Path
from IPython.display import display, HTML

viewer_file = Path('EPI_Evidence_Viewer.html')
epi_files = list(Path('.').glob('*.epi')) + list(Path('.').glob('epi-recordings/*.epi'))
epi_file = max(epi_files, key=lambda p: p.stat().st_mtime) if epi_files else None

if viewer_file.exists() and epi_file:
    print("=" * 70)
    display(HTML('<h2 style="color: #10b981;">Downloading Files...</h2>'))
    try:
        from google.colab import files
        files.download(str(epi_file))
        files.download(str(viewer_file))
        display(HTML(
            '<div style="background: #f0fdf4; border: 2px solid #10b981; padding: 20px; border-radius: 12px; margin: 20px 0;">'
            '<h3 style="color: #166534; margin: 0 0 15px 0;">Check your Downloads folder!</h3>'
            '<p style="color: #15803d; margin: 5px 0;"><b>1. *.epi</b> - The cryptographic evidence package</p>'
            '<p style="color: #15803d; margin: 5px 0;"><b>2. EPI_Evidence_Viewer.html</b> - Double-click to view in browser</p>'
            '</div>'
        ))
    except Exception as e:
        print("(Use the file panel to download: {} and {})".format(epi_file.name, viewer_file.name))
    print("=" * 70)
else:
    print("Run the viewer cell first")
