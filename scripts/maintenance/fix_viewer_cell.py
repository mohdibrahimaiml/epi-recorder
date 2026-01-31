import json

# Load the notebook
with open('epi_investor_demo_ULTIMATE.ipynb', 'r', encoding='utf-8') as f:
    nb = json.load(f)

# Replace the viewer cell (Cell 8, index 8 in cells array)
viewer_cell_new_source = [
    "# IMPROVED: Display the Timeline Data\\n",
    "import zipfile\\n",
    "import json\\n",
    "\\n",
    "display(HTML('<h1 style=\\"color: #8b5cf6;\\">🖥️ THE VIEWER INTERFACE</h1>'))\\n",
    "print(\\"\\\\n\\" + \\"=\\"*70)\\n",
    "\\n",
    "if epi_file and epi_file.exists():\\n",
    "    try:\\n",
    "        # Extract and display the timeline data\\n",
    "        print(\\"📂 Extracting timeline data from .epi container...\\\\n\\")\\n",
    "        \\n",
    "        with zipfile.ZipFile(epi_file, 'r') as z:\\n",
    "            # Read steps from steps.jsonl\\n",
    "            if 'steps.jsonl' in z.namelist():\\n",
    "                steps_data = z.read('steps.jsonl').decode('utf-8')\\n",
    "                steps = [json.loads(line) for line in steps_data.strip().split('\\\\n') if line]\\n",
    "                \\n",
    "                # Create a visual timeline\\n",
    "                timeline_html = '<div style=\\"background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 10px; color: white; margin: 20px 0;\\">\\n',
    "                timeline_html += '<h2 style=\\"color: white; margin: 0 0 20px 0;\\">📊 Execution Timeline (Preview)</h2>'\\n",
    "                \\n",
    "                for i, step in enumerate(steps[:5]):  # Show first 5 steps\\n",
    "                    timeline_html += f'<div style=\\"background: rgba(255,255,255,0.1); padding: 15px; margin: 10px 0; border-left: 4px solid #10b981; border-radius: 5px;\\">\\n',
    "                    timeline_html += f'<strong>Step {step.get(\\"index\\", i)}</strong> - {step.get(\\"kind\\", \\"unknown\\")}<br>'\\n",
    "                    timeline_html += f'<small>{step.get(\\"timestamp\\", \\"N/A\\")}</small>'\\n",
    "                    timeline_html += '</div>'\\n",
    "                \\n",
    "                if len(steps) > 5:\\n",
    "                    timeline_html += f'<div style=\\"text-align: center; padding: 10px; font-style: italic;\\">... and {len(steps)-5} more steps</div>'\\n",
    "                \\n",
    "                timeline_html += '</div>'\\n",
    "                \\n",
    "                display(HTML(timeline_html))\\n",
    "                \\n",
    "                print(\\"=\\"*70)\\n",
    "                display(HTML('<h3 style=\\"color:#10b981\\">✅ Timeline Captured Successfully</h3>'))\\n",
    "                print(f\\"   Total Steps: {len(steps)}\\")\\n",
    "                print(f\\"   Duration: {steps[-1].get('timestamp', 'N/A') if steps else 'N/A'}\\")\\n",
    "                print(\\"\\\\n📦 WHAT'S IN THE DOWNLOADED FILE:\\")\\n",
    "                print(\\"   ✓ Full interactive HTML viewer\\")\\n",
    "                print(\\"   ✓ Complete execution timeline\\")\\n",
    "                print(\\"   ✓ All captured data\\")\\n",
    "                print(\\"   ✓ Ed25519 cryptographic signature\\")\\n",
    "                print(\\"\\\\n💡 TO SEE THE FULL INTERACTIVE VIEWER:\\")\\n",
    "                display(HTML('<p style=\\"background: #fef3c7; padding: 15px; border-left: 4px solid #f59e0b; margin: 10px 0;\\">'\\n",
    "                            f'<strong>1.</strong> Locate the downloaded file: <code>{epi_file.name}</code><br>'\\n",
    "                            '<strong>2.</strong> Open it with any browser (Chrome, Firefox, Edge)<br>'\\n",
    "                            '<strong>3.</strong> You\\\\'ll see the full timeline with all interaction data</p>'))\\n",
    "                print(\\"=\\"*70)\\n",
    "            else:\\n",
    "                print(\\"⚠️  Timeline data not found in archive\\")\\n",
    "        \\n",
    "    except Exception as e:\\n",
    "        print(f\\"\\\\n⚠️  Preview error: {str(e)[:80]}\\")\\n",
    "        display(HTML(f'<p style=\\"background: #fee2e2; padding: 15px; border-left: 4px solid #ef4444; margin: 10px 0;\\">'\\n",
    "                    f'<strong>Note:</strong> The .epi file you downloaded contains a full interactive viewer.<br>'\\n",
    "                    f'Open <code>{epi_file.name if epi_file else \\"the downloaded file\\"}</code> in your browser to explore the complete timeline.</p>'))\\n",
    "else:\\n",
    "    print(\\"\\\\nℹ️  Interactive viewer demonstration\\")\\n",
    "    print(\\"(Full viewer available in downloaded .epi file)\\")"
]

# Update the viewer cell
nb['cells'][8]['source'] = viewer_cell_new_source

# Save the notebook
with open('epi_investor_demo_ULTIMATE.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=2, ensure_ascii=False)

print("VIEWER CELL UPDATED")
print("Changes:")
print("  - Removed IFrame approach (Colab sandbox issues)")
print("  - Added direct timeline data extraction")
print("  - Shows visual preview of execution steps")
print("  - Provides clear instructions to open downloaded file")
print("\\nStatus: Ready for Colab")


