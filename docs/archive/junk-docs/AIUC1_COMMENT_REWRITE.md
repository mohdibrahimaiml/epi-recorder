# AIUC-1 Comment — Corrected Version (Ready to Post)

---

Following up from my April comment — EPI Recorder is now v4.1.0 with SCITT (IETF) transparency support, which directly addresses the format vs. storage discussion above.

@arian-gogani and @agentauditAI both named the right distinction: a tamper-evident format proves internal consistency; tamper-proof storage proves the artifact wasn't retroactively replaced. EPI handles both without blockchain.

**Format layer:** Ed25519 signature over SHA-256 canonical manifest. Any post-seal modification breaks the signature. The `prev_hash` chain across `steps.jsonl` catches insertion or deletion of individual entries.

**Anchoring layer:** SCITT (IETF draft-ietf-scitt-architecture) transparency receipts. When `EPI_SCITT_AUTO_ANCHOR=1` is set, the manifest hash is automatically submitted to a SCITT Transparency Service — an append-only log that neither EPI nor the producing organization can alter retroactively. An auditor verifies the receipt cryptographically against the service's public key (fetched from the service or cached locally) without contacting the artifact producer.

This provides the same "cannot be regenerated" guarantee as on-chain anchoring with different properties: no blockchain dependency, works in EU enterprise environments without cryptocurrency association, verifiable offline via the embedded Ed25519 signature when the Transparency Service is unreachable, and IETF-standardized with a regulatorily readable reference specification.

For Article 12 specifically: EPI produces a portable `.epi` artifact — a single signed file containing the full execution trace, input/output pairs at each step, model identifiers, human oversight decisions, policy evaluation, and environment snapshot. The embedded `viewer.html` opens in any browser without installing anything — relevant for regulators who need to inspect evidence without vendor tooling or an active backend.

```python
from epi_recorder.integrations.langchain import EPICallbackHandler

handler = EPICallbackHandler(workflow_name="credit-decision-agent")
result = chain.invoke(input_data, config={"callbacks": [handler]})
# → credit-decision-agent.epi signed, sealed, SCITT-anchored (when auto-anchor enabled)
```

```bash
epi verify --strict credit-decision-agent.epi
# Trust Level: HIGH | Signature: VALID | Chain: INTACT | SCITT: VERIFIED
```

v4.1.0 — MIT — Python 3.11+
PyPI: pypi.org/project/epi-recorder
GitHub: github.com/mohdibrahimaiml/epi-recorder
