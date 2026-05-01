#!/usr/bin/env python3
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.helpers.artifacts import rewrite_legacy_member

src = Path("demo_workflows/loan_decision.epi")
tampered = Path("demo_workflows/loan_decision_tampered.epi")
shutil.copy(src, tampered)
rewrite_legacy_member(tampered, "steps.jsonl", b'{"hack":true}\n')
print("Created tampered artifact:", tampered)
