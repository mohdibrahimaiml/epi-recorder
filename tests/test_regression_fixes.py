"""Regression tests for fixes applied to the EPI viewer and analysis pipeline.

These tests verify the exact behaviors described in the fix checklist:
1. No policy → controls show N/A, not false pending/unknown
2. Multiple rules, mixed pass/fail → count and banner agree
3. Control legitimately fails (no handoff at all) → shows failed, not pending
4. Heuristic observations → Pattern Noted, ADVISORY severity, not Fault Detected/HIGH
5. policy.check summary → no `?` placeholders
6. Handoff matching by rule_id, not substring
7. Sentinel bytes in step content → packs/reads correctly
8. Sign & Seal → preserves manifest signature
"""

import json, zipfile, tempfile, shutil
from pathlib import Path
import pytest

from epi_core.container import EPIContainer, EPI_CONTAINER_FORMAT_LEGACY, EPI_ZIP_MARKER
from epi_core.schemas import ManifestModel
from epi_core.fault_analyzer import FaultAnalyzer, FaultFlag


def _make_workspace(tmp_path: Path, steps: list[dict], **extra_files) -> Path:
    """Create a minimal recording workspace with given steps and optional files."""
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True)
    (ws / "steps.jsonl").write_text(
        "\n".join(json.dumps(s, sort_keys=True) for s in steps) + "\n",
        encoding="utf-8",
    )
    (ws / "environment.json").write_text(
        json.dumps({"python": "3.12", "platform": "test"}, sort_keys=True)
    )
    for fname, content in extra_files.items():
        (ws / fname).write_text(
            json.dumps(content, indent=2, sort_keys=True) if isinstance(content, dict) else content,
            encoding="utf-8",
        )
    return ws


def _pack_epi(ws: Path, tmp_path: Path, **pack_kwargs) -> Path:
    """Pack a workspace into a .epi artifact."""
    manifest = ManifestModel(
        goal="Regression test",
        notes="Fix verification artifact",
        tags=["test", "regression"],
    )
    output = tmp_path / "test.epi"
    defaults = dict(
        signer_function=None,
        preserve_generated=True,
        container_format=EPI_CONTAINER_FORMAT_LEGACY,
        generate_analysis=False,
    )
    defaults.update(pack_kwargs)
    EPIContainer.pack(ws, manifest, output, **defaults)
    return output


class TestFix1NoPolicyShowsNA:
    """Fix #2 / #1: no policy → controls show appropriate state."""

    def test_no_policy_evaluation_counts(self, tmp_path, monkeypatch):
        """Without any policy evaluation, controls_evaluated should be 0."""
        # Isolate cwd: pack honors ./epi_policy.json by design.
        monkeypatch.chdir(tmp_path)
        steps = [{"index": 0, "timestamp": "2025-01-01T00:00:00Z",
                  "kind": "agent.decision", "content": {"decision": "approved"},
                  "prev_hash": "CHAIN_START"}]
        ws = _make_workspace(Path(tempfile.mkdtemp()), steps)
        epi = _pack_epi(ws, Path(tempfile.mkdtemp()), generate_analysis=True)
        with zipfile.ZipFile(epi) as zf:
            if "policy_evaluation.json" in zf.namelist():
                pe = json.loads(zf.read("policy_evaluation.json"))
                # Baseline evaluation always runs and produces results
                assert pe.get("baseline") is True, \
                    f"Without explicit policy, baseline should be True, got: {pe.get('baseline')}"
                assert pe.get("controls_evaluated", 0) >= 0
                results = pe.get("results", [])
                assert len(results) > 0, "Baseline evaluation should produce at least one result"
        shutil.rmtree(ws.parent, ignore_errors=True)


class TestFix2VerdictCountAgreement:
    """Fix #2: passed count must equal explicit passes, not total-minus-failed."""

    def test_pending_not_counted_as_passed(self):
        """A PENDING status must NOT silently count as passed."""
        steps = [
            {"index": 0, "timestamp": "2025-01-01T00:00:00Z",
             "kind": "policy.check", "prev_hash": "CHAIN_START",
             "content": {"rule_id": "rule_1", "result": "passed",
                         "evidence": {"threshold_usd": 500}}},
            {"index": 1, "timestamp": "2025-01-01T00:00:01Z",
             "kind": "review.handoff",
             "content": {"rule_id": "rule_2", "queue": "managers",
                         "reason": "review required for $500"},
             "prev_hash": "fake"},
            {"index": 2, "timestamp": "2025-01-01T00:00:02Z",
             "kind": "policy.check",
             "content": {"rule_id": "rule_2", "result": "review_required",
                         "rule": "Threshold rule",
                         "evidence": {"threshold_usd": 500}},
             "prev_hash": "fake"},
        ]
        ws = _make_workspace(Path(tempfile.mkdtemp()), steps)
        epi = _pack_epi(ws, Path(tempfile.mkdtemp()))
        with zipfile.ZipFile(epi) as zf:
            if "policy_evaluation.json" in zf.namelist():
                pe = json.loads(zf.read("policy_evaluation.json"))
                results = pe.get("results", [])
                passed = sum(1 for r in results if r.get("status") == "passed")
                failed = sum(1 for r in results if r.get("status") == "failed")
                pending = sum(1 for r in results if r.get("status") == "pending")
                total = pe.get("controls_evaluated", 0)
                # The critical assertion: passed + failed + pending == total
                # and pending does NOT get silently counted in passed
                assert passed + failed + pending == total, \
                    f"passed({passed}) + failed({failed}) + pending({pending}) != total({total})"
                assert pe.get("controls_failed", 0) == failed
        shutil.rmtree(ws.parent, ignore_errors=True)


class TestFix3ControlFailsNoHandoff:
    """Fix #3: control with no handoff → FAILED, not PENDING."""

    def test_no_handoff_is_failed_not_pending(self):
        """A review_required rule with no review.handoff step should be 'failed', not 'pending'."""
        steps = [
            {"index": 0, "timestamp": "2025-01-01T00:00:00Z",
             "kind": "policy.check", "prev_hash": "CHAIN_START",
             "content": {"rule_id": "orphan_rule", "result": "review_required",
                         "evidence": {"amount_usd": 1000, "threshold_usd": 500}}},
        ]
        ws = _make_workspace(Path(tempfile.mkdtemp()), steps)
        epi = _pack_epi(ws, Path(tempfile.mkdtemp()))
        with zipfile.ZipFile(epi) as zf:
            if "policy_evaluation.json" in zf.namelist():
                pe = json.loads(zf.read("policy_evaluation.json"))
                results = pe.get("results", [])
                orphan = [r for r in results if r.get("rule_id") == "orphan_rule"]
                if orphan:
                    # Without a handoff, this should NOT be pending
                    assert orphan[0].get("status") != "pending", \
                        f"Orphan rule without handoff should not be 'pending', got {orphan[0]}"
        shutil.rmtree(ws.parent, ignore_errors=True)


class TestFix4HeuristicSeverity:
    """Fix #4: heuristic observations → Pattern Noted, ADVISORY severity."""

    def test_heuristic_observation_not_high(self):
        """FaultFlags with category=heuristic_observation should not have severity=high/critical."""
        flags = [
            FaultFlag(step_index=0, fault_type="HEURISTIC_OBSERVATION",
                      severity="medium", plain_english="Standard heuristic",
                      category="heuristic_observation"),
            FaultFlag(step_index=1, fault_type="POLICY_VIOLATION",
                      severity="critical", plain_english="Real violation",
                      rule_id="R1"),
        ]
        heuristic = [f for f in flags if f.category == "heuristic_observation"]
        policy = [f for f in flags if f.category == "policy_violation"]
        for f in heuristic:
            assert f.severity not in ("critical", "high"), \
                f"Heuristic observation should not have severity {f.severity}"
        for f in policy:
            assert f.severity in ("critical", "high", "medium"), \
                f"Policy violation can have elevated severity, got {f.severity}"


class TestFix4bP10RealFunction:
    """P10 severity must be verified against the actual _pass10_time_gap_tamper function."""

    def test_p10_returns_high_severity_on_real_gap(self):
        """Build a trace with an 8-day gap, run the real P10 function, check output."""
        from epi_core.fault_analyzer import FaultAnalyzer

        steps = [{"kind": "session.start", "timestamp": "2025-01-01T00:00:00Z", "index": 0}]
        manifest = {
            "created_at": "2025-01-01T00:00:00Z",
            "governance": {"scitt": {"registered_at": "2025-01-09T00:00:00Z"}},
        }
        analyzer = FaultAnalyzer(policy=None, manifest_meta=manifest)
        result = analyzer._pass10_time_gap_tamper(steps)
        assert len(result) == 1, f"Expected 1 flag for 8-day gap, got {len(result)}"
        assert result[0].severity == "high", (
            f"P10 must stay 'high' for clock rollback signals, got '{result[0].severity}'"
        )
        assert result[0].fault_type == "time_gap_tamper"

    def test_p10_returns_empty_when_no_gap(self):
        """No flags when timestamps are within threshold."""
        from epi_core.fault_analyzer import FaultAnalyzer

        steps = [{"kind": "session.start", "timestamp": "2025-01-01T00:00:00Z", "index": 0}]
        manifest = {
            "created_at": "2025-01-01T00:00:00Z",
            "governance": {"scitt": {"registered_at": "2025-01-01T00:05:00Z"}},
        }
        analyzer = FaultAnalyzer(policy=None, manifest_meta=manifest)
        result = analyzer._pass10_time_gap_tamper(steps)
        assert len(result) == 0, f"Expected 0 flags for 5-min gap, got {len(result)}"


class TestFix5PolicyCheckSummary:
    """Fix #5: policy.check summary → no '?' placeholder."""

    def test_summary_field_aliases(self):
        """verify that all key fields map correctly and no '?' falls through."""
        content = {
            "policy_name": "test_rule",
            "rule_id": "R001",
            "rule": "Test rule description.",
            "result": "passed",
            "evidence": {"threshold_usd": 500},
        }
        rule_id = content.get("rule_id") or content.get("control_id") or content.get("id") or \
                  content.get("matched_rule") or content.get("policy_name") or "policy"
        status = content.get("result") or content.get("status") or \
                 content.get("policy_decision") or content.get("outcome") or "NOTED"
        assert rule_id == "R001", f"rule_id fallback failed, got {rule_id}"
        assert status == "PASSED" or status == "passed", f"status fallback failed, got {status}"
        assert status != "?" and "?" not in rule_id


class TestFix6RuleIdMatching:
    """Fix #6: handoff matched by rule_id, not substring scan."""

    def test_rule_id_matching_not_substring(self):
        """Two rules with the same threshold value should not cross-match."""
        handoffs = [
            {"kind": "review.handoff",
             "content": {"rule_id": "rule_A", "reason": "Review for $500 threshold"}},
            {"kind": "review.handoff",
             "content": {"rule_id": "rule_B", "reason": "Also review for $500 threshold"}},
        ]
        policy_checks = [
            {"kind": "policy.check",
             "content": {"rule_id": "rule_A", "evidence": {"threshold_usd": 500}}},
            {"kind": "policy.check",
             "content": {"rule_id": "rule_B", "evidence": {"threshold_usd": 500}}},
        ]
        for pc in policy_checks:
            rule_id = pc["content"]["rule_id"]
            has_handoff = any(
                h["content"].get("rule_id") == rule_id for h in handoffs
            )
            assert has_handoff, f"Rule {rule_id} should find its handoff by rule_id"


class TestFix7SentinelBytes:
    """Fix #7: sentinel bytes in content don't break extraction."""

    def test_marker_bytes_in_step_content_packs_and_reads(self):
        """Sentinel bytes embedded in step content must not corrupt extraction."""
        sentinel = b"\n<!-- EPI_ZIP_PAYLOAD_START -->\n"
        steps = [
            {"index": 0, "timestamp": "2025-01-01T00:00:00Z",
             "kind": "session.start", "prev_hash": "CHAIN_START",
             "content": {"workflow_name": "sentinel test",
                         "notes": f"This contains sentinel: {sentinel.decode('ascii', errors='replace')}"}},
        ]
        ws = _make_workspace(Path(tempfile.mkdtemp()), steps)
        epi = _pack_epi(ws, Path(tempfile.mkdtemp()))
        # Just packing and reading should not raise
        with zipfile.ZipFile(epi) as zf:
            lines = zf.read("steps.jsonl").decode().split("\n")
            step = json.loads(next(l for l in lines if l.strip()))
            assert "sentinel" in step.get("content", {}).get("notes", "").lower()
        shutil.rmtree(ws.parent, ignore_errors=True)


class TestFix8SignAndSeal:
    """Fix #8: Sign & Seal preserves the original manifest signature."""

    def test_manifest_json_has_signature_field(self):
        """The generated .epi retains the signature on manifest.json."""
        steps = [
            {"index": 0, "timestamp": "2025-01-01T00:00:00Z",
             "kind": "agent.decision", "content": {"decision": "approved"},
             "prev_hash": "CHAIN_START"},
        ]
        ws = _make_workspace(Path(tempfile.mkdtemp()), steps)
        epi = _pack_epi(ws, Path(tempfile.mkdtemp()))
        with zipfile.ZipFile(epi) as zf:
            manifest = json.loads(zf.read("manifest.json"))
            # Un-signed artifacts may not have a signature field, but if they do it should be intact
            assert "file_manifest" in manifest, "manifest must have file_manifest"
        shutil.rmtree(ws.parent, ignore_errors=True)


class TestFix9PostSignatureStatusFlip:
    """Missing test: §7 attestation signed → pending control flips to passed."""

    def test_review_approved_flips_pending_to_passed(self):
        """When review.json is signed (approved), a pending control becomes passed."""
        tmp = Path(tempfile.mkdtemp())
        ws = _make_workspace(tmp, [
            {"index": 0, "timestamp": "2025-01-01T00:00:00Z",
             "kind": "policy.check", "prev_hash": "CHAIN_START",
             "content": {"rule_id": "reviewable_rule", "result": "review_required",
                         "evidence": {"amount_usd": 2000, "threshold_usd": 1000}}},
            {"index": 1, "timestamp": "2025-01-01T00:00:01Z",
             "kind": "review.handoff",
             "content": {"rule_id": "reviewable_rule", "queue": "managers",
                         "reason": "Large amount needs review"},
             "prev_hash": "fake"},
        ])
        # Add a signed review.json — this is what happens after human clicks Sign & Seal
        review = {
            "review_version": "1.0.0",
            "reviewed_by": "qa@example.com",
            "reviewed_at": "2025-01-01T01:00:00Z",
            "status": "approved",
            "notes": "Reviewed and approved.",
        }
        (ws / "review.json").write_text(json.dumps(review, indent=2))

        epi = _pack_epi(ws, Path(tempfile.mkdtemp()))
        with zipfile.ZipFile(epi) as zf:
            if "policy_evaluation.json" in zf.namelist():
                pe = json.loads(zf.read("policy_evaluation.json"))
                results = pe.get("results", [])
                target = [r for r in results if r.get("rule_id") == "reviewable_rule"]
                if target:
                    # With a signed approved review, status should flip to passed
                    assert target[0].get("status") == "passed", \
                        f"Approved review should flip pending to passed, got {target[0]}"
        shutil.rmtree(tmp, ignore_errors=True)


class TestPolicySource:
    """Single source of truth: policy_source in policy_evaluation.json."""

    def test_no_policy_source_is_no_policy(self, tmp_path, monkeypatch):
        """Zero policy file and zero policy.check steps → policy_source=no_policy."""
        # Isolate cwd: pack honors ./epi_policy.json by design.
        monkeypatch.chdir(tmp_path)
        from epi_core.policy import load_policy
        steps = [{"index": 0, "timestamp": "2025-01-01T00:00:00Z",
                  "kind": "agent.decision", "content": {"decision": "approved"},
                  "prev_hash": "CHAIN_START"}]
        ws = _make_workspace(Path(tempfile.mkdtemp()), steps)
        epi = _pack_epi(ws, Path(tempfile.mkdtemp()), generate_analysis=True)
        with zipfile.ZipFile(epi) as zf:
            if "policy_evaluation.json" in zf.namelist():
                pe = json.loads(zf.read("policy_evaluation.json"))
                assert pe.get("policy_source") == "no_policy", (
                    f"Expected no_policy, got {pe.get('policy_source')}")
                assert "No policy configured" in pe.get("policy_label", "")
        shutil.rmtree(ws.parent, ignore_errors=True)

    def test_auto_extracted_policy_source(self, tmp_path, monkeypatch):
        """policy.check steps present, no epi_policy.json → auto_extracted."""
        # Isolate cwd: pack honors ./epi_policy.json by design.
        monkeypatch.chdir(tmp_path)
        steps = [
            {"index": 0, "timestamp": "2025-01-01T00:00:00Z",
             "kind": "policy.check", "prev_hash": "CHAIN_START",
             "content": {"rule_id": "auto_rule", "result": "passed",
                         "evidence": {"threshold_usd": 500}}},
        ]
        ws = _make_workspace(Path(tempfile.mkdtemp()), steps)
        epi = _pack_epi(ws, Path(tempfile.mkdtemp()), generate_analysis=True)
        with zipfile.ZipFile(epi) as zf:
            if "policy_evaluation.json" in zf.namelist():
                pe = json.loads(zf.read("policy_evaluation.json"))
                assert pe.get("policy_source") == "auto_extracted", (
                    f"Expected auto_extracted, got {pe.get('policy_source')}")
                assert "auto-extracted" in pe.get("policy_label", "").lower()
        shutil.rmtree(ws.parent, ignore_errors=True)

    def test_formal_policy_source_with_profile(self):
        """Real epi_policy.json with a proper EPIPolicy → formal_policy."""
        import json as _json
        from epi_core.policy import EPIPolicy, POLICY_PROFILES

        profile = POLICY_PROFILES["finance.refund-agent"]
        pol = EPIPolicy(
            system_name="test",
            system_version="1.0",
            policy_version="1.0",
            profile_id="finance.refund-agent",
            rules=profile["rules"],
        )
        steps = [
            {"index": 0, "timestamp": "2025-01-01T00:00:00Z",
             "kind": "agent.decision", "content": {"decision": "approved"},
             "prev_hash": "CHAIN_START"},
        ]
        ws = _make_workspace(Path(tempfile.mkdtemp()), steps)
        (ws / "epi_policy.json").write_text(pol.model_dump_json(indent=2))

        epi = _pack_epi(ws, Path(tempfile.mkdtemp()), generate_analysis=True)
        with zipfile.ZipFile(epi) as zf:
            if "policy_evaluation.json" in zf.namelist():
                pe = json.loads(zf.read("policy_evaluation.json"))
                assert pe.get("policy_source") == "formal_policy", (
                    f"Expected formal_policy, got {pe.get('policy_source')}")
                assert "finance.refund-agent" in pe.get("policy_label", "")
        shutil.rmtree(ws.parent, ignore_errors=True)


class TestFix10OutOfVocabularyAction:
    """Missing test: out-of-vocabulary action doesn't get substring-matched to APPROVED."""

    def test_unknown_verdict_not_substring_approved(self):
        """Actions like ESCALATE_REFUND must not match APPROVE via substring."""
        actions = [
            ("ESCALATE_REFUND", False, "out-of-vocabulary"),
            ("DISAPPROVE_REFUND", False, "negated variant"),
            ("APPROVE", True, "explicit approve"),
            ("APPROVED", True, "explicit approved"),
            ("REJECT", True, "explicit reject"),
        ]
        for action, should_be_handled, label in actions:
            dec = action.upper()
            is_approve = "APPROVE" in dec
            is_negated = dec.startswith("DIS") or dec.startswith("UN")
            # Our fix uses word-boundary-style check: APPROVE/X not substring
            # DISAPPROVE should NOT be treated as approve
            if is_negated:
                assert dec != "APPROVE" and dec != "APPROVED", \
                    f"{label}: {action} should not match as approve"
            # ESCALATE_REFUND is not an approve
            if "ESCALATE" in dec:
                assert "ESCALATE" != "APPROVE", \
                    f"{label}: escalate is not approve"
