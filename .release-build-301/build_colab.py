"""
Build the premium investor demo Colab notebook.
Reads cell sources from _cells/ directory to avoid nested quoting issues.
"""
import nbformat as nbf
from pathlib import Path

nb = nbf.v4.new_notebook()
nb.metadata = {
    "colab": {"provenance": [], "name": "EPI Recorder - Investor Demo"},
    "kernelspec": {"name": "python3", "display_name": "Python 3"},
}

cells = []

def md(source):
    cells.append(nbf.v4.new_markdown_cell(source))

def code_from_file(filename):
    p = Path("_cells") / filename
    cells.append(nbf.v4.new_code_cell(p.read_text(encoding="utf-8")))

# Build all cells
md("# The $100,000 Loan Decision\n\nYour AI Agent Made This Call. Can You Prove It Was Fair?\n\n---\n\n> Click: **Runtime -> Run All** | Total time: 90 seconds")

md("---\n# Setup: Install EPI Recorder")
code_from_file("cell_setup.py")

md("---\n# The AI Agent: Fintech Underwriter\n\nProduction-grade code. Not a toy demo.\n- **Hybrid Logic**: Deterministic rules + AI reasoning\n- **Fair Lending Compliant**: No protected class data\n- **Demo/Live Mode**: Works with or without API key")
code_from_file("cell_agent.py")

md("---\n# LIVE: Record the AI Agent\n\nWatch EPI capture the Gemini API calls **automatically**.")
code_from_file("cell_record.py")

md("---\n# Inspect: What Did EPI Capture?\n\nWe captured the *exact prompts* and *AI responses* - including the Fair Lending system prompt.")
code_from_file("cell_inspect.py")

md("---\n# Verify: Cryptographic Proof\n\nEd25519 digital signature verification.\n\n**Same cryptography used by**: Signal, SSH, GitHub")
code_from_file("cell_verify.py")

md("---\n# Explore EPI Structure\n\nAn `.epi` file is a cryptographically sealed ZIP archive.")
code_from_file("cell_explore.py")

md("---\n# Interactive Viewer\n\nThe EPI file includes a **self-contained HTML viewer** that works offline.")
code_from_file("cell_viewer.py")

md("---\n# Download: Take It With You\n\nDownload the evidence viewer to your machine.")
code_from_file("cell_download.py")

md("---\n# Security Test: Can You Fake It?\n\nWe extract the `.epi` archive, modify the decision in `steps.jsonl`, repack it, and run `epi verify` on the tampered file.")
code_from_file("cell_tamper.py")

md("---\n# Interrogate the Evidence: EPI Chat\n\nAsk questions about any recorded workflow. The AI answers **FROM THE EVIDENCE**.")
code_from_file("cell_chat.py")

md("---\n# Works With What You Already Use\n\nEPI integrates with every major AI framework in **one line**.")
code_from_file("cell_integrations.py")

md("---\n# What You Just Witnessed\n\n| Step | What Happened | Why It Matters |\n|------|--------------|----------------|\n| **Agent** | AI processed $100K loan | Real production workflow |\n| **Capture** | Gemini calls auto-recorded | Zero integration effort |\n| **Signed** | Ed25519 signature applied | Tamper-proof evidence |\n| **Verified** | Cryptographic proof confirmed | Regulator-ready |\n| **Tamper** | Forgery instantly detected | Unfakeable |")
code_from_file("cell_cta.py")

nb.cells = cells

with open('investor_demo_colab.ipynb', 'w', encoding='utf-8') as f:
    nbf.write(nb, f)

print("Premium investor demo notebook generated successfully!")
print("Total cells: {}".format(len(cells)))
