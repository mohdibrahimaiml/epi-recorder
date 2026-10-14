"""Seal the website sample.epi (functional browser-verify sample, 4.6.1)."""
from epi_recorder import record

with record(
    "website/assets/sample.epi",
    workflow_name="epilabs-org-sample",
    goal="Website sample.epi for browser verify",
    notes="Unpinned sealer \u2014 UNVERIFIED IDENTITY is expected",
) as epi:
    epi.log_step(
        "stdout.print",
        {"stream": "stdout", "text": "EPI Labs sample artifact"},
    )
print("sealed website/assets/sample.epi")
