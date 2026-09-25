'use strict';

// ============================================================
//  EPI FORENSIC VIEWER — app.js
//  Loads injected JSON, renders all sections of the forensic
//  document. No frameworks. No external dependencies beyond
//  what viewer_assets.py inlines.
// ============================================================

// ── Utilities ────────────────────────────────────────────────

/** HTML-escape a value for safe insertion via innerHTML. */
function esc(v) {
  if (v == null) return '';
  const d = document.createElement('div');
  d.textContent = String(v);
  return d.innerHTML;
}

/** Truncate a string to maxLen, appending ellipsis if truncated. Display only — not the sealed record. */
function trunc(s, maxLen) {
  if (!s) return '';
  s = String(s);
  return s.length > maxLen ? s.slice(0, maxLen) + '…' : s;
}

/** Format an ISO timestamp as HH:MM:SS.mmm (local time). */
function fmtTime(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    const ss = String(d.getSeconds()).padStart(2, '0');
    const ms = String(d.getMilliseconds()).padStart(3, '0');
    return `${hh}:${mm}:${ss}.${ms}`;
  } catch (e) { return iso; }
}

/** Format an ISO timestamp as a readable date string. */
function fmtDate(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleString(undefined, {
      year: 'numeric', month: 'short', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
      hour12: false
    });
  } catch (e) { return iso; }
}

/** Parse JSON from a script tag by id, return null on failure. */
function parseScriptTag(id) {
  try {
    const el = document.getElementById(id);
    if (!el) return null;
    const text = el.textContent.trim();
    if (!text || text === 'null' || text === '{}') return null;
    return JSON.parse(text);
  } catch (e) {
    console.warn(`[epi] Failed to parse #${id}:`, e);
    return null;
  }
}

/** Show/hide an element and its corresponding nav link. */
function showSection(sectionId, navId) {
  const sec = document.getElementById(sectionId);
  const nav = navId ? document.getElementById(navId) : null;
  if (sec) sec.classList.remove('hidden');
  if (nav) nav.classList.remove('hidden');
}

// ── Step Summarization ────────────────────────────────────────

/**
 * Produce a human-readable one-liner for a step.
 * Covers all documented step kinds.
 */
function summarizeStep(step) {
  const kind = (step.kind || '').toLowerCase();
  const c = step.content || {};

  try {
    switch (kind) {
      case 'session.start': {
        const wn = c.workflow_name || c.name || 'unnamed';
        let s = `Session started: ${wn}`;
        if (Array.isArray(c.tags) && c.tags.length > 0) {
          s += ` · tags: ${c.tags.join(', ')}`;
        }
        return s;
      }

      case 'session.end': {
        const dur = c.duration_seconds != null ? c.duration_seconds : '?';
        const ok = c.success === true ? 'success' : (c.success === false ? 'error' : 'unknown');
        return `Completed in ${dur}s — ${ok}`;
      }

      case 'environment.captured': {
        const plat = c.platform || c.os || 'unknown platform';
        const py = c.python_version || c.python || '';
        return py ? `${plat} · Python ${py}` : plat;
      }

      case 'llm.request': {
        const model = c.model || c.engine || 'unknown model';
        const msgCount = Array.isArray(c.messages) ? c.messages.length : 1;
        return `Queried ${model} · ${msgCount} message${msgCount !== 1 ? 's' : ''}`;
      }

      case 'llm.response': {
        // Prefer output field, then choices[0].message.content, then content
        let text = c.output || '';
        if (!text && Array.isArray(c.choices) && c.choices[0]) {
          text = c.choices[0].message?.content || c.choices[0].text || '';
        }
        if (!text && typeof c.content === 'string') text = c.content;
        return trunc(text, 200) || `Response from ${c.model || 'model'}`;
      }

      case 'tool.call': {
        const name = c.tool || c.name || c.tool_name || (c.agt_data && (c.agt_data.tool || c.agt_data.tool_name)) || 'unknown';
        const inputStr = JSON.stringify(c.input || c.tool_input || c.parameters || c.agt_data || {});
        return `Called ${name}(${trunc(inputStr, 100)})`;
      }

      case 'tool.response': {
        const result = typeof c.result === 'string'
          ? c.result
          : JSON.stringify(c.result || c.output || c);
        return `Returned: ${trunc(result, 180)}`;
      }

      case 'agent.decision': {
        const decision = String(c.decision || c.verdict || '?').toUpperCase();
        const rationale = c.rationale || c.reasoning || c.reason || '';
        return `Decision: ${decision}${rationale ? ' — ' + trunc(rationale, 160) : ''}`;
      }

      case 'agent.approval.request': {
        const action = c.action || c.request || JSON.stringify(c);
        return `Requested approval: ${trunc(String(action), 180)}`;
      }

      case 'agent.approval.response': {
        const reviewer = c.reviewer || c.reviewed_by || 'reviewer';
        const approved = c.approved === true || String(c.status || c.decision || '').toLowerCase() === 'approved';
        const action = c.action || '';
        return `${reviewer} ${approved ? 'approved' : 'rejected'}${action ? ': ' + trunc(action, 140) : ''}`;
      }

      case 'agent.run.start': {
        const agentType = c.agent_type || c.type || '';
        return `Agent run started${agentType ? ` (${agentType})` : ''}`;
      }

      case 'agent.run.end':
        return 'Agent run ended';

      case 'application.intake': {
        const appId = c.applicant_id || c.application_id || '?';
        const purpose = c.loan_purpose || c.purpose || '';
        const amount = c.loan_amount != null ? `$${Number(c.loan_amount).toLocaleString()}` : '';
        const parts = [appId, purpose, amount].filter(Boolean);
        return `Intake: ${parts.join(' · ')}`;
      }

      case 'credit.check': {
        const score = c.credit_score != null ? `score: ${c.credit_score}` : '';
        const dti = c.debt_to_income != null ? `DTI: ${c.debt_to_income}` : '';
        const result = c.result || c.status || '';
        const parts = [score, dti, result ? `Result: ${result}` : ''].filter(Boolean);
        return `Credit check — ${parts.join(' · ')}`;
      }

      case 'policy.check': {
        const ruleId = c.constraint || c.policy_ref || c.rule_id || c.control_id || c.id || c.matched_rule || c.policy_name || (c.agt_data && c.agt_data.policy_name) || (typeof c.rule === 'string' ? c.rule : '') || 'policy';
        const status = (c.result || c.status || c.policy_decision || c.outcome || '').toUpperCase() || 'NOTED';
        const ruleText = c.detail || (typeof c.rule === 'string' ? c.rule : '') || c.message || c.plain_english || '';
        return `Rule ${ruleId}: ${status}${ruleText ? ' — ' + trunc(ruleText, 120) : ''}`;
      }

      case 'source.record.loaded': {
        const recId = c.record_id || c.id || '?';
        const system = c.system || c.source || '?';
        return `Loaded record ${recId} from ${system}`;
      }

      default: {
        // Readable fallback: stringify content, trimmed
        const str = JSON.stringify(c);
        return trunc(str, 180);
      }
    }
  } catch (e) {
    return '(error summarizing step)';
  }
}

// ── Step Tone (heatmap color + kind label class) ──────────────

/**
 * Returns { htClass, kindClass } for a step.
 * htClass is used on heatmap ticks, kindClass on the ev-kind cell.
 */
function stepTone(step) {
  const kind = (step.kind || '').toLowerCase();
  const c = step.content || {};
  const hasFault = c.fault || c.error || c.exception;

  if (hasFault) return { htClass: 'ht-fail', kindClass: 'ev-kind-fail' };

  switch (kind) {
    case 'llm.request':
    case 'llm.response':
      return { htClass: 'ht-llm', kindClass: 'ev-kind-llm' };

    case 'tool.call':
    case 'tool.response':
      return { htClass: 'ht-tool', kindClass: 'ev-kind-tool' };

    case 'policy.check': {
      const status = String(c.status || c.result || '').toLowerCase();
      if (status === 'triggered' || status === 'failed' || status === 'fail' || status === 'review_required') {
        return { htClass: 'ht-fail', kindClass: 'ev-kind-fail' };
      }
      return { htClass: 'ht-policy', kindClass: 'ev-kind-policy' };
    }

    case 'agent.decision': {
      const dec = String(c.decision || c.verdict || '').toUpperCase();
      if (dec.includes('APPROVED') || dec.includes('APPROVE') || dec.includes('PASS') || dec.includes('ACCEPT')) {
        return { htClass: 'ht-pass', kindClass: 'ev-kind-pass' };
      }
      if (dec.includes('REJECT') || dec.includes('DENY') || dec.includes('FAIL') || dec.includes('DECLINE')) {
        return { htClass: 'ht-fail', kindClass: 'ev-kind-fail' };
      }
      return { htClass: 'ht-warn', kindClass: 'ev-kind-warn' };
    }

    case 'credit.check': {
      const result = String(c.result || c.status || '').toUpperCase();
      if (result === 'PASS' || result === 'PASSED') {
        return { htClass: 'ht-pass', kindClass: 'ev-kind-pass' };
      }
      if (result === 'FAIL' || result === 'FAILED') {
        return { htClass: 'ht-fail', kindClass: 'ev-kind-fail' };
      }
      return { htClass: 'ht-warn', kindClass: 'ev-kind-warn' };
    }

    case 'session.start':
    case 'session.end':
    case 'environment.captured':
      return { htClass: 'ht-gray', kindClass: 'ev-kind-gray' };

    default:
      return { htClass: 'ht-gray', kindClass: 'ev-kind-default' };
  }
}

// ── Data Loading ──────────────────────────────────────────────

/**
 * Load and normalize the case data from injected script tags.
 * Returns { cases: [], context: null } or null if nothing found.
 */
function loadData() {
  const rawCtx = parseScriptTag('epi-view-context');
  // Only treat as a real context if it has actual verification data
  const context = (rawCtx && (rawCtx.signature_valid != null || rawCtx.integrity_ok != null || rawCtx.facts))
    ? rawCtx : null;

  // Try new multi-case format first
  let preloaded = parseScriptTag('epi-preloaded-cases');
  if (preloaded && Array.isArray(preloaded.cases) && preloaded.cases.length > 0) {
    return { cases: preloaded.cases, context };
  }

  // Fall back to legacy epi-data format
  const legacy = parseScriptTag('epi-data');
  if (legacy) {
    // Wrap legacy format into the case shape
    const fakeCase = {
      source_name: legacy.manifest?.workflow_id || 'artifact',
      file_size: 0,
      archive_base64: null,
      manifest: legacy.manifest || {},
      steps: legacy.steps || [],
      analysis: legacy.analysis || null,
      policy: legacy.policy || null,
      policy_evaluation: legacy.policy_evaluation || null,
      review: legacy.review || null,
      environment: legacy.environment || null,
      integrity: legacy.integrity || null,
      signature: legacy.signature || null,
    };
    return { cases: [fakeCase], context };
  }

  return null;
}

// ── Section Renderers ─────────────────────────────────────────

/** § 0  Document Header */
function renderHeader(caseData, context) {
  const m = caseData.manifest || {};
  const steps = caseData.steps || [];

  // Resolve workflow name: session.start content > manifest > short UUID
  const sessionStart = steps.find(s => s.kind === 'session.start');
  const workflowName = sessionStart?.content?.workflow_name
    || m.goal  // fallback to goal as title if no workflow name
    || m.workflow_id?.slice(0, 8)
    || caseData.source_name?.slice(0, 8)
    || 'Unknown Artifact';

  const uuid = m.workflow_id || m.artifact_uuid || caseData.source_name || '—';
  const createdAt = m.created_at ? fmtDate(m.created_at) : '—';
  const container = m.container_format || 'unknown';
  const spec = m.spec_version || '—';
  // Seal-time producer version; fall back to spec_version for artifacts
  // sealed before producer_version existed.
  const producer = m.producer_version || m.spec_version || '—';

  document.getElementById('header-title').textContent = workflowName.replace(/_/g, ' ');
  document.getElementById('header-uuid').textContent = 'UUID: ' + uuid;
  document.getElementById('meta-created').textContent = createdAt;
  document.getElementById('meta-container').textContent = container;
  document.getElementById('meta-spec').textContent = spec;
  const producerEl = document.getElementById('meta-producer');
  if (producerEl) producerEl.textContent = producer;
  document.getElementById('meta-steps').textContent = steps.length + ' step' + (steps.length !== 1 ? 's' : '');
  document.title = workflowName + ' — EPI Forensic Viewer';

  // Status pills
  const pillsEl = document.getElementById('header-pills');
  const intOk = caseData.integrity?.ok !== false;
  // Prefer live context sig_valid, but only when it's been explicitly set.
  // An empty/missing context must not override the preloaded case payload.
  const hasLiveSig = context != null && Object.prototype.hasOwnProperty.call(context, 'signature_valid');
  const sigValid = hasLiveSig ? context.signature_valid : caseData.signature?.valid;
  const sigVerified = sigValid === true;

  pillsEl.innerHTML = '';

  const intPill = document.createElement('span');
  intPill.className = 'pill ' + (intOk ? 'pass' : 'fail');
  intPill.innerHTML = `<span class="pill-dot"></span>${intOk ? 'INTEGRITY VERIFIED' : 'INTEGRITY FAILED'}`;
  pillsEl.appendChild(intPill);

  const sigPill = document.createElement('span');
  if (sigValid == null) {
    sigPill.className = 'pill gray';
    sigPill.innerHTML = `<span class="pill-dot"></span>SIGNATURE NOT VERIFIED`;
  } else if (sigVerified) {
    sigPill.className = 'pill pass';
    sigPill.innerHTML = `<span class="pill-dot"></span>SIGNATURE VALID`;
  } else {
    const hasManifestSig = !!(caseData.manifest && caseData.manifest.signature);
    sigPill.className = hasManifestSig ? 'pill fail' : 'pill warn';
    sigPill.innerHTML = hasManifestSig
      ? `<span class="pill-dot"></span>SIGNATURE INVALID`
      : `<span class="pill-dot"></span>UNSIGNED`;
  }
  pillsEl.appendChild(sigPill);

  // Human review status pill
  const humanReview = normalizeReview(caseData.review || caseData);
  if (humanReview) {
    const reviewPill = document.createElement('span');
    const rs = humanReview.status;
    if (rs === 'approved') {
      reviewPill.className = 'pill pass';
    } else if (rs === 'rejected') {
      reviewPill.className = 'pill fail';
    } else {
      reviewPill.className = 'pill warn';
    }
    reviewPill.innerHTML = `<span class="pill-dot"></span>REVIEW ${rs.toUpperCase()}`;
    pillsEl.appendChild(reviewPill);
  }

  // Risk level pill
  const pe = caseData.policy_evaluation || {};
  const analysis = caseData.analysis || {};
  const riskLevel = pe.risk_level || analysis.risk_level || null;
  if (riskLevel) {
    const rl = String(riskLevel).toLowerCase();
    const riskPill = document.createElement('span');
    let riskClass = 'warn';
    if (rl === 'high' || rl === 'critical') riskClass = 'fail';
    if (rl === 'low') riskClass = 'pass';
    riskPill.className = 'pill ' + riskClass;
    riskPill.innerHTML = `<span class="pill-dot"></span>RISK ${String(riskLevel).toUpperCase()}`;
    pillsEl.appendChild(riskPill);
  }
}

/**
 * Client-side verification for standalone / export-html viewers.
 * Uses embedded archive_base64 (when present) + verifyManifestSignature from crypto.js.
 * Never punts with a message telling users to open a different tool.
 */
async function verifyCaseInBrowser(caseData) {
  const result = {
    signature_valid: null,
    integrity_ok: null,
    signature_reason: null,
    integrity_reason: null,
    client_verified: false,
  };
  if (!caseData || typeof caseData !== 'object') return result;

  const manifest = caseData.manifest || {};
  const hasSig = !!(manifest.signature || (caseData.signature && caseData.signature.present));

  // ── Signature (Ed25519 over canonical manifest hash) ──
  // Pass raw manifest JSON text to preserve Python's float format (900.0 vs 900)
  const rawManifestText = caseData.files && caseData.files['manifest.json']
    ? atob(caseData.files['manifest.json'])
    : null;
  if (typeof globalThis.verifyManifestSignature === 'function' && manifest.signature) {
    try {
      const vr = await globalThis.verifyManifestSignature(manifest, rawManifestText);
      result.signature_valid = vr && vr.valid === true;
      result.signature_reason = (vr && vr.reason) || null;
      result.client_verified = true;
    } catch (e) {
      result.signature_valid = false;
      result.signature_reason = e && e.message ? e.message : String(e);
      result.client_verified = true;
    }
  } else if (!manifest.signature && !hasSig) {
    result.signature_valid = false;
    result.signature_reason = 'No signature in manifest';
    result.client_verified = true;
  }

  // ── Integrity (member hashes from archive_base64 or files{}) ──
  try {
    const fm = manifest.file_manifest || {};
    const names = Object.keys(fm);
    if (names.length > 0 && typeof JSZip !== 'undefined') {
      let zip = null;
      if (caseData.archive_base64) {
        zip = await JSZip.loadAsync(base64ToUint8Array(caseData.archive_base64));
      }
      const mismatches = [];
      for (const name of names) {
        const expected = String(fm[name] || '').toLowerCase();
        if (!expected) continue;
        let bytes = null;
        if (zip) {
          const entry = zip.file(name);
          if (!entry) {
            mismatches.push(name);
            continue;
          }
          bytes = await entry.async('uint8array');
        } else if (caseData.files && caseData.files[name]) {
          bytes = base64ToUint8Array(caseData.files[name]);
        } else {
          continue; // cannot check this member offline
        }
        const got = await sha256Hex(bytes);
        if (got !== expected) mismatches.push(name);
      }
      if (mismatches.length > 0) {
        result.integrity_ok = false;
        result.integrity_reason = 'Hash mismatch: ' + mismatches.slice(0, 5).join(', ');
        result.client_verified = true;
      } else if (zip || (caseData.files && Object.keys(caseData.files).length > 0)) {
        result.integrity_ok = true;
        result.client_verified = true;
      }
    }
  } catch (e) {
    // Non-fatal — leave integrity_ok null if we cannot check
    result.integrity_reason = e && e.message ? e.message : String(e);
  }

  // Prefer payload integrity if client could not re-hash
  if (result.integrity_ok == null && caseData.integrity && typeof caseData.integrity.ok === 'boolean') {
    result.integrity_ok = caseData.integrity.ok;
  }

  return result;
}

/** § 1  Trust & Integrity */
function renderIntegrity(caseData, context) {
  const m = caseData.manifest || {};
  const integrity = caseData.integrity || {};
  const sig = caseData.signature || {};

  // Integrity indicator — prefer live client context
  const intEl = document.getElementById('ind-integrity');
  let intOk;
  if (context && typeof context.integrity_ok === 'boolean') {
    intOk = context.integrity_ok;
  } else {
    intOk = integrity.ok !== false;
  }
  if (intOk) {
    intEl.textContent = 'VERIFIED';
    intEl.className = 'indicator verified';
    intEl.title = 'File integrity verified — this measures whether the sealed record has been altered since sealing. It does not verify that the recording process captured every action the agent actually took.';
  } else {
    intEl.textContent = 'COMPROMISED';
    intEl.className = 'indicator failed';
    if (context && context.integrity_reason) intEl.title = context.integrity_reason;
  }

  // Signature indicator — prefer live client crypto; never punt to another tool
  const sigEl = document.getElementById('ind-signature');
  let resolvedSigValid;
  if (context && Object.prototype.hasOwnProperty.call(context, 'signature_valid')) {
    resolvedSigValid = context.signature_valid;
  } else if (sig && typeof sig.valid === 'boolean') {
    resolvedSigValid = sig.valid;
  } else {
    resolvedSigValid = null;
  }

  if (resolvedSigValid === true) {
    sigEl.textContent = 'VALID';
    sigEl.className = 'indicator verified';
    sigEl.style.fontSize = '';
    if (context && context.signature_reason) sigEl.title = context.signature_reason;
  } else if (resolvedSigValid === false) {
    const unsigned = !m.signature && !(sig && (sig.signer || sig.reason));
    sigEl.textContent = unsigned ? 'UNSIGNED' : 'INVALID';
    sigEl.className = 'indicator failed';
    sigEl.style.fontSize = '';
    if (context && context.signature_reason) sigEl.title = context.signature_reason;
    else if (sig && sig.reason) sigEl.title = sig.reason;
  } else {
    sigEl.textContent = 'NOT VERIFIED';
    sigEl.className = 'indicator unverified';
    sigEl.style.fontSize = '';
    sigEl.title = 'Client-side signature verification was not available in this environment.';
  }

  // Identity
  const idEl = document.getElementById('ind-identity');
  const did = m.governance?.did || context?.identity?.did || '';
  const orgRoot = (m.governance && m.governance.org_root) || '';
  const pubkey = m.public_key ? m.public_key.slice(0, 16) : '';
  const signer = context?.signer || context?.identity?.name || '';
  if (did) {
    idEl.textContent = did;
    idEl.className = 'indicator verified';
    idEl.style.fontSize = '11px';
  } else if (orgRoot) {
    // Named org root only — the browser never verifies a bundle, so this is
    // deliberately NOT green. Confirm offline:
    //   epi org bundle verify file.epi org-bundle.json
    idEl.textContent = 'org ' + String(orgRoot).slice(0, 16) + '...';
    idEl.className = 'indicator unknown';
    idEl.style.fontSize = '12px';
    idEl.title = 'Org root named by this artifact (unverified in browser). Confirm offline: epi org bundle verify file.epi org-bundle.json';
  } else if (pubkey) {
    idEl.textContent = pubkey + '...';
    idEl.className = 'indicator unknown';
    idEl.style.fontSize = '12px';
  } else {
    idEl.textContent = signer || '(unsigned)';
    idEl.className = 'indicator unknown';
    idEl.style.fontSize = '12px';
  }

  // Diagnostic matrix
  const checked = integrity.checked || 0;
  const mismatches = Array.isArray(integrity.mismatches) ? integrity.mismatches.length : 0;

  const filesEl = document.getElementById('diag-files');
  if (checked > 0 || integrity.ok != null) {
    filesEl.textContent = `${checked} checked / ${mismatches} mismatch${mismatches !== 1 ? 'es' : ''}`;
    filesEl.className = 'diag-status ' + (mismatches === 0 ? 'ok' : 'flagged');
  } else {
    filesEl.textContent = '—';
    filesEl.className = 'diag-status unknown';
  }

  const stepsArr = caseData.steps || [];
  const noHashMismatches = !integrity.mismatches || integrity.mismatches.length === 0;

  const chainEl = document.getElementById('diag-chain');
  const isChainOk = (context?.facts?.sequence_ok != null)
    ? context.facts.sequence_ok
    : (caseData.facts?.sequence_ok != null)
      ? caseData.facts.sequence_ok
      : (stepsArr.length > 0 && noHashMismatches);

  if (isChainOk != null) {
    chainEl.textContent = isChainOk ? 'OK' : 'BROKEN';
    chainEl.className = 'diag-status ' + (isChainOk ? 'ok' : 'flagged');
  } else {
    chainEl.textContent = '—';
    chainEl.className = 'diag-status unknown';
  }

  const compEl = document.getElementById('diag-completeness');
  const isCompOk = (context?.facts?.completeness_ok != null)
    ? context.facts.completeness_ok
    : (caseData.facts?.completeness_ok != null)
      ? caseData.facts.completeness_ok
      : (stepsArr.length > 0 && noHashMismatches);

  if (isCompOk != null) {
    compEl.textContent = isCompOk ? 'OK' : 'INCOMPLETE';
    compEl.className = 'diag-status ' + (isCompOk ? 'ok' : 'flagged');
  } else {
    compEl.textContent = '—';
    compEl.className = 'diag-status unknown';
  }

  const pkEl = document.getElementById('diag-pubkey');
  if (m.public_key) {
    pkEl.textContent = m.public_key.slice(0, 16) + '...';
    pkEl.className = 'diag-status ok';
  } else {
    pkEl.textContent = '(unsigned)';
    pkEl.className = 'diag-status unknown';
  }

  // Verify command
  const sourceName = caseData.source_name || m.workflow_id || 'artifact.epi';
  const cmdText = `epi verify ${sourceName}`;
  document.getElementById('verify-cmd-text').textContent = cmdText;

  // Notarization / RFC 3161 Timestamp and Envelope
  const notarization = caseData.notarization;
  const envelope = caseData.envelope;
  const noteBlock = document.getElementById('notarization-block');
  if (!noteBlock) return;

  if (notarization || envelope) {
    noteBlock.classList.remove('hidden');

    // RFC 3161 TSA — presence only. The token's CMS signature, certificate
    // chain, and messageImprint are NOT cryptographically validated here.
    // Treat the timestamp as an unverified corroborating field.
    const rfcEl = document.getElementById('diag-rfc3161');
    if (notarization?.tsa_token_available) {
      const tsaUrl = notarization.notarized_at?.url || '';
      const tsaHost = tsaUrl ? tsaUrl.replace(/^https?:\/\//, '').split('/')[0] : 'TSA';
      const genTime = notarization.tsa_genTime || caseData.notarization_tsa_time || '';
      rfcEl.textContent = 'RFC 3161 token present (' + tsaHost + (genTime ? ' · genTime ' + genTime : '') + '; signature not validated)';
      rfcEl.className = 'diag-status unknown';
      rfcEl.title = 'Token present, genTime read. Signature, chain, and messageImprint are not validated — see KNOWN_LIMITATIONS.md.';
    } else if (notarization) {
      rfcEl.textContent = 'Unavailable';
      rfcEl.className = 'diag-status unknown';
    }

    // Bitcoin (OTS)
    const otsEl = document.getElementById('diag-ots');
    if (notarization?.ots_proof_available) {
      otsEl.textContent = '\u2713 Anchored';
      otsEl.className = 'diag-status ok';
    } else if (notarization?.ots_note) {
      otsEl.textContent = 'Not installed';
      otsEl.className = 'diag-status unknown';
    }

    // Envelope UUID
    const uuidEl = document.getElementById('diag-envelope-uuid');
    if (envelope?.artifact_uuid) {
      uuidEl.textContent = envelope.artifact_uuid.slice(0, 16) + '...';
      uuidEl.className = 'diag-status ok';
      uuidEl.title = envelope.artifact_uuid;
    }

    // Payload Hash — check both baked (payload_hash) and context (payload_sha256) field names
    const phEl = document.getElementById('diag-payload-hash');
    const payloadHash = envelope?.payload_hash || envelope?.payload_sha256;
    if (payloadHash) {
      phEl.textContent = payloadHash.slice(0, 16) + '...';
      phEl.className = 'diag-status ok';
      phEl.title = payloadHash;
    }
  }
}

window.copyVerifyCmd = function(el) {
  const text = document.getElementById('verify-cmd-text')?.textContent || '';
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(() => {
      el.style.animation = 'none';
      el.offsetHeight; // reflow
      el.style.animation = 'flash-bg 0.5s ease';
    });
  }
};

/** § 2  Case Context */
function renderCaseContext(caseData) {
  const m = caseData.manifest || {};
  const steps = caseData.steps || [];
  const sessionStart = steps.find(s => s.kind === 'session.start');

  const goal = m.goal;
  const notes = m.notes;
  const metrics = m.metrics;
  const approvedBy = m.approved_by;
  const tags = sessionStart?.content?.tags;

  const hasContent = goal || notes || metrics || approvedBy || (Array.isArray(tags) && tags.length > 0);
  if (!hasContent) return;

  showSection('case-context', 'nav-context');

  let html = '<div class="context-grid">';

  if (goal) {
    html += `
      <div class="context-field">
        <div class="context-key">Goal</div>
        <div class="context-val">${esc(goal)}</div>
      </div>`;
  }

  if (notes) {
    html += `
      <div class="context-field">
        <div class="context-key">Notes</div>
        <div class="context-val">${esc(notes)}</div>
      </div>`;
  }

  if (approvedBy) {
    html += `
      <div class="context-field">
        <div class="context-key">Approved_By</div>
        <div class="context-val">${esc(approvedBy)}</div>
      </div>`;
  }

  if (Array.isArray(tags) && tags.length > 0) {
    html += `
      <div class="context-field">
        <div class="context-key">Tags</div>
        <div class="context-val">
          <div class="tag-list">
            ${tags.map(t => `<span class="tag">${esc(t)}</span>`).join('')}
          </div>
        </div>
      </div>`;
  }

  html += '</div>';

  if (metrics && typeof metrics === 'object' && Object.keys(metrics).length > 0) {
    html += `
      <div style="margin-top:20px;">
        <div class="context-key" style="margin-bottom:8px;">Metrics</div>
        <table class="metrics-table">
          ${Object.entries(metrics).map(([k, v]) =>
            `<tr><td>${esc(k)}</td><td>${esc(typeof v === 'object' ? JSON.stringify(v) : v)}</td></tr>`
          ).join('')}
        </table>
      </div>`;
  }

  document.getElementById('context-inner').innerHTML = html;
}

/** § 3  Verdict / Decision */
function renderVerdict(caseData) {
  const steps = caseData.steps || [];
  const analysis = caseData.analysis || null;
  const pe = caseData.policy_evaluation || null;

  // Find last agent.decision or policy.check with known outcome
  let decisionStep = null;
  for (let i = steps.length - 1; i >= 0; i--) {
    const sk = steps[i].kind || '';
    if (sk === 'agent.decision') { decisionStep = steps[i]; break; }
    // policy.check with final status is also a decision
    if (sk === 'policy.check') {
      const sc = steps[i].content || {};
      const st = String(sc.status || sc.policy_decision || '').toLowerCase();
      if (st === 'deny' || st === 'blocked' || st === 'allow' || st === 'passed') {
        decisionStep = steps[i]; break;
      }
    }
  }

  const decisionContent = decisionStep?.content || {};
  const rawDecision = String(decisionContent.decision || decisionContent.verdict || decisionContent.policy_decision || decisionContent.status || '').toUpperCase();

  // Check human review — it overrides the system verdict when present
  const humanReview = normalizeReview(caseData.review || caseData);

  // Determine verdict class and display text
  let verdictClass = 'pending';
  let verdictDisplay = 'PENDING';
  let systemVerdict = null;

  if (rawDecision) {
    systemVerdict = rawDecision;
    // Negation prefixes: DISAPPROVE, UNAPPROVE, etc. are not approvals
    const _approved_list = ['APPROVED', 'APPROVE', 'PASS', 'PASSED', 'ACCEPT', 'ACCEPTED'];
    const _rejected_list = ['REJECTED', 'REJECT', 'DENY', 'DENIED', 'FAIL', 'FAILED', 'DECLINE', 'DECLINED'];
    const is_approved = _approved_list.some(v => rawDecision.includes(v));
    const is_rejected = _rejected_list.some(v => rawDecision.includes(v));
    const has_negation = ['DIS', 'UN', 'NON', 'DE'].some(p => rawDecision.startsWith(p));

    if (is_approved && !has_negation) {
      verdictClass = 'approved';
      verdictDisplay = 'APPROVED';
    } else if (is_rejected || (is_approved && has_negation)) {
      verdictClass = 'rejected';
      verdictDisplay = 'REJECTED';
    } else {
      verdictClass = 'pending';
      verdictDisplay = rawDecision.replace(/_/g, ' ');
    }
  } else if (analysis) {
    if (analysis.fault_detected === true) {
      const isPolicyViolation = analysis.primary_fault && (
        analysis.primary_fault.fault_type === 'POLICY_VIOLATION' ||
        analysis.primary_fault.category === 'policy_violation'
      );
      if (isPolicyViolation) {
        systemVerdict = 'FAILED';
        verdictClass = 'failed';
        verdictDisplay = 'FAILED';
      } else {
        systemVerdict = 'WARNING';
        verdictClass = 'pending';
        verdictDisplay = 'WARNING';
      }
    } else if (analysis.fault_detected === false) {
      systemVerdict = 'PASSED';
      verdictClass = 'passed';
      verdictDisplay = 'PASSED';
    }
  }

  // Human review overrides
  if (humanReview) {
    const rs = humanReview.status;
    if (rs === 'approved') {
      verdictDisplay = 'APPROVED';
      verdictClass = 'approved';
    } else if (rs === 'rejected') {
      verdictDisplay = 'REJECTED';
      verdictClass = 'rejected';
    } else if (rs === 'escalated') {
      verdictDisplay = 'ESCALATED';
      verdictClass = 'pending';
    }
  }

  const verdictEl = document.getElementById('verdict-text');
  verdictEl.textContent = verdictDisplay;
  verdictEl.className = 'verdict-text ' + verdictClass;

  // Provenance: a verdict display must never read as system adjudication
  // when it only echoes a recorded claim. Name the source (agent step +
  // step number) and whether §7 attestation exists yet.
  const sourceEl = document.getElementById('verdict-source');
  if (sourceEl) {
    const stepNo = decisionStep && typeof decisionStep.index === 'number'
      ? decisionStep.index + 1 : null;
    let agentName = (decisionContent && (decisionContent.agent_name || decisionContent.agent)) || null;
    if (!agentName) {
      const runStart = steps.find(s => s.kind === 'agent.run.start');
      agentName = (runStart && runStart.content && runStart.content.agent_name) || null;
    }
    const where = stepNo != null ? ` at step ${stepNo}` : '';
    const who = agentName ? ` by ${agentName}` : '';
    let srcText = '';
    let attestText = '';
    let attestCls = 'warn';
    if (decisionStep && decisionStep.kind === 'agent.decision') {
      if (humanReview) {
        srcText = `Agent-reported outcome · recorded${who}${where} — attested: ${String(humanReview.status).toUpperCase()} by ${humanReview.reviewed_by || 'reviewer'} (§7).`;
        attestText = `ATTESTED · ${String(humanReview.status).toUpperCase()}`;
        attestCls = humanReview.status === 'approved' ? 'pass' : (humanReview.status === 'rejected' ? 'fail' : 'warn');
      } else {
        srcText = `Agent-reported outcome · recorded${who}${where} — pending human attestation (§7).`;
        attestText = 'UNATTESTED';
        attestCls = 'warn';
      }
    } else if (decisionStep) {
      srcText = `Recorded outcome (${decisionStep.kind})${where} — ${humanReview ? 'attested (§7).' : 'pending human attestation (§7).'}`;
      attestText = humanReview ? 'ATTESTED' : 'UNATTESTED';
      attestCls = humanReview ? 'pass' : 'warn';
    }
    if (srcText) {
      sourceEl.innerHTML = `<span class="pill ${attestCls}"><span class="pill-dot"></span>${esc(attestText)}</span><span>${esc(srcText)}</span>`;
    } else {
      sourceEl.innerHTML = '';
    }
  }

  // Compliance stats + risk level
  const isNoPolicy = !pe || pe.policy_source === 'no_policy' || (pe.controls_evaluated || 0) === 0;
  if (pe && !isNoPolicy) {
    const total = pe.controls_evaluated || 0;
    const results = pe.results || [];
    const passed = results.filter(r => r.status === 'passed' || r.status === 'pass').length;
    const failed = results.filter(r => r.status === 'failed' || r.status === 'fail').length;
    const pendingCount = results.length - passed - failed;
    let statsText = `${passed}/${total} GOVERNANCE CONTROL${total !== 1 ? 'S' : ''} SATISFIED`;
    if (pendingCount > 0) {
      statsText += ` (${pendingCount} PENDING)`;
    }
    document.getElementById('compliance-stats').textContent = statsText;

    const riskLevel = pe.risk_level || analysis?.risk_level || null;
    const riskEl = document.getElementById('risk-level-badge');
    if (riskLevel && riskEl) {
      const rl = String(riskLevel).toLowerCase();
      riskEl.textContent = `Risk: ${String(riskLevel).toUpperCase()}`;
      riskEl.className = 'risk-level-badge ' + (rl === 'high' ? 'high' : rl === 'low' ? 'low' : 'medium');
    } else if (riskEl) {
      riskEl.textContent = '';
      riskEl.className = 'risk-level-badge';
    }
  } else {
    document.getElementById('compliance-stats').textContent = 'No policy configured — baseline heuristics only';
    const riskEl = document.getElementById('risk-level-badge');
    if (riskEl) {
      riskEl.textContent = '';
      riskEl.className = 'risk-level-badge';
    }
  }

  // Analysis note + human attestation context
  const noteEl = document.getElementById('verdict-note');
  const headline = analysis?.summary?.headline;
  const rationale = decisionContent.rationale || decisionContent.reasoning;
  const parts = [];

  if (humanReview) {
    parts.push(`Human attestation by ${humanReview.reviewed_by}: ${humanReview.status.toUpperCase()}.`);
  }
  if (rationale) {
    parts.push(trunc(rationale, 300));
  } else if (headline) {
    parts.push(headline);
  } else if (systemVerdict && humanReview) {
    parts.push(`System verdict was ${systemVerdict}.`);
  }

  if (parts.length) {
    noteEl.textContent = parts.join(' ');
  }

  // 4-pass diagnostic matrix
  const diagEl = document.getElementById('verdict-diag');
  if (analysis) {
    const allFlags = [
      ...(analysis.primary_fault ? [analysis.primary_fault] : []),
      ...(analysis.secondary_flags || [])
    ];

    const matchesPassKey = (f, key) => {
      if (!f) return false;
      if (f.fault_type === key || f.category === key || f.rule_id === key) return true;
      if (key === 'ERROR_CONTINUATION' && (f.rule_id === 'P1' || f.fault_type === 'ERROR_CONTINUATION')) return true;
      if (key === 'CONSTRAINT_VIOLATION' && (f.rule_id === 'P2' || f.fault_type === 'CONSTRAINT_VIOLATION' || f.policy_type === 'constraint_guard')) return true;
      if (key === 'SEQUENCE_VIOLATION' && (f.rule_id === 'P3' || f.fault_type === 'SEQUENCE_VIOLATION' || f.policy_type === 'sequence_guard')) return true;
      if (key === 'CONTEXT_DROP' && (f.rule_id === 'P4' || f.fault_type === 'CONTEXT_DROP')) return true;
      return false;
    };

    const hasFaultType = (type) => allFlags.some(f => matchesPassKey(f, type));
    const isHeuristicFault = (type) => allFlags.some(f =>
      matchesPassKey(f, type) && (f.category === 'heuristic_observation' || f.fault_type !== 'POLICY_VIOLATION')
    );

    const checks = [
      { label: 'P1: Error_Continuation',  key: 'ERROR_CONTINUATION' },
      { label: 'P2: Constraint_Violation', key: 'CONSTRAINT_VIOLATION' },
      { label: 'P3: Sequence_Violation',   key: 'SEQUENCE_VIOLATION' },
      { label: 'P4: Context_Drop',         key: 'CONTEXT_DROP' },
    ];

    diagEl.innerHTML = checks.map(ch => {
      const flagged = hasFaultType(ch.key);
      const isHeuristic = isHeuristicFault(ch.key);
      const label = flagged ? (isHeuristic ? 'PATTERN NOTED' : 'FLAGGED') : 'OK';
      const cls = flagged ? (isHeuristic ? 'warn' : 'flagged') : 'ok';
      return `
        <div class="diag-item">
          <span class="diag-label">${esc(ch.label)}</span>
          <span class="diag-status ${cls}">${label}</span>
        </div>`;
    }).join('');
  }
}

/** § 4  Evidence Timeline */
function renderEvidence(caseData) {
  const steps = caseData.steps || [];
  const heatmapEl = document.getElementById('evidence-heatmap');
  const tableEl = document.getElementById('evidence-table');

  heatmapEl.innerHTML = '';
  tableEl.innerHTML = '';

  if (steps.length === 0) {
    tableEl.innerHTML = '<div style="padding:20px; color:var(--text-muted); font-size:12px;">No steps recorded.</div>';
    return;
  }

  const startMs = steps[0]?.timestamp ? new Date(steps[0].timestamp).getTime() : 0;

  steps.forEach((step, idx) => {
    const tone = stepTone(step);
    const summary = summarizeStep(step);
    const kind = step.kind || 'step';
    const kindDisplay = kind.toUpperCase().replace(/\./g, '.');

    // Timestamp + delta
    const ts = fmtTime(step.timestamp);
    let deltaStr = '';
    if (startMs && step.timestamp) {
      const stepMs = new Date(step.timestamp).getTime();
      if (!isNaN(stepMs)) {
        const delta = ((stepMs - startMs) / 1000).toFixed(3);
        deltaStr = `+${delta}s`;
      }
    }

    // Chain hash
    const prevHash = step.prev_hash
      ? (step.prev_hash === 'CHAIN_START' ? 'START' : step.prev_hash.slice(0, 8))
      : '—';

    // Build row
    const row = document.createElement('div');
    row.className = 'ev-row';
    row.setAttribute('data-idx', idx);

    row.innerHTML = `
      <div class="ev-row-main">
        <div class="ev-ts">
          <span class="ev-ts-time">${esc(ts)}</span>
          <span class="ev-ts-delta">${esc(deltaStr)}</span>
          <span class="ev-chain">&#9935; <span class="ev-chain-id">${esc(prevHash)}</span></span>
        </div>
        <div class="ev-kind ${esc(tone.kindClass)}">${esc(kindDisplay)}</div>
        <div class="ev-summary">${esc(summary)}</div>
        <div class="ev-expand-hint"></div>
      </div>
      <div class="ev-json">${esc(JSON.stringify(step, null, 2))}</div>
    `;

    row.querySelector('.ev-row-main').addEventListener('click', () => {
      row.classList.toggle('expanded');
    });

    tableEl.appendChild(row);

    // Heatmap tick
    const tick = document.createElement('div');
    tick.className = 'heatmap-tick ' + tone.htClass;
    tick.title = `${kind} — ${trunc(summary, 60)}`;
    tick.addEventListener('click', () => {
      row.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      if (!row.classList.contains('expanded')) row.classList.add('expanded');
    });
    heatmapEl.appendChild(tick);
  });
}

/** § 5  Governance */
function renderGovernance(caseData) {
  const policy = caseData.policy;
  const pe = caseData.policy_evaluation || {};
  const results = pe.results || [];

  // Always show governance if we have ANY evaluation data
  if (!policy?.rules && results.length === 0) return;

  showSection('governance-basis', 'nav-governance');

  let html = '';

  // Single-source policy label: read from policy_evaluation.policy_label
  if (pe.policy_label) {
    const labelStyles = 'margin-bottom:20px;padding:12px 16px;border-radius:8px;font-size:14px;font-weight:600;line-height:1.5;';
    let labelBg, labelBorder, labelColor, labelIcon;
    
    if (pe.policy_source === 'no_policy') {
      labelBg = 'var(--surface-dim)';
      labelBorder = 'var(--border-soft)';
      labelColor = 'var(--ink-soft)';
      labelIcon = '—';
    } else if (pe.policy_source === 'auto_extracted') {
      labelBg = '#fef3c7';
      labelBorder = '#f59e0b';
      labelColor = '#92400e';
      labelIcon = '⚠';
    } else {
      labelBg = '#d1fae5';
      labelBorder = '#10b981';
      labelColor = '#065f46';
      labelIcon = '✓';
    }
    html += `<div style="${labelStyles}background:${labelBg};border:2px solid ${labelBorder};color:${labelColor};">${labelIcon} ${esc(pe.policy_label)}</div>`;
  }

  // Show a note when using baseline/heuristic evaluation (legacy path)
  if (!policy?.rules && pe.baseline) {
    html += '<div style="margin-bottom:16px;padding:10px 14px;background:var(--accent-glow);border:1px solid var(--accent-line);border-radius:8px;font-size:11px;color:var(--ink-soft)">';
    html += '<strong>Baseline Evaluation</strong> — No epi_policy.json configured.<br>';
    html += 'Run <code>epi policy init</code> to create domain-specific rules for your workflow.';
    html += '</div>';
  }

  // Show a note when rules were auto-extracted from policy.check steps
  if (pe.auto_extracted) {
    html += '<div style="margin-bottom:16px;padding:10px 14px;background:var(--accent-glow);border:1px solid var(--accent-line);border-radius:8px;font-size:11px;color:var(--ink-soft)">';
    html += '<strong>Auto-Extracted Rules</strong> — These rules were derived from <code>policy.check</code> steps recorded by the agent, ';
    html += 'not from a formal <code>epi_policy.json</code>. They may not cover all risks.<br>';
    html += 'Run <code>epi policy init</code> for authoritative domain-specific rules.';
    html += '</div>';
  }

  // Render formal policy rules when present
  if (policy?.rules && policy.rules.length > 0) {
    html += policy.rules.map(rule => {
      const ruleId = typeof rule === 'string' ? rule : (rule.id || rule.name || 'unnamed');
      const ruleName = typeof rule === 'string' ? rule : (rule.name || rule.id || 'Unnamed rule');
      const ruleDesc = typeof rule === 'string' ? '' : (rule.description || '');

      const res = results.find(r =>
        (r.rule_id && r.rule_id === ruleId) ||
        (r.control_id && r.control_id === ruleId) ||
        (r.name && r.name === ruleName) ||
        (r.rule_name && r.rule_name === ruleName)
      );

      let ruleSeverity = res?.severity || (typeof rule === 'string' ? 'medium' : (rule.severity || 'medium'));
      ruleSeverity = String(ruleSeverity).toLowerCase();
      const status = res?.status || 'unknown';
      const isPassed = status === 'passed' || status === 'pass';
      const isFailed = status === 'failed' || status === 'fail';

      let detailHtml = '';
      if (typeof rule === 'object' && rule.condition) {
        const cond = rule.condition;
        detailHtml += '<div class="policy-item-desc">Condition: ' + esc(cond.field || '?') + ' ' + esc(cond.operator || '?') + ' ' + esc(String(cond.value ?? '')) + '</div>';
      }
      if (typeof rule === 'object' && rule.threshold != null) {
        detailHtml += '<div class="policy-item-desc">Threshold: ' + esc(String(rule.threshold)) + '</div>';
      }
      if (ruleDesc) {
        detailHtml += '<div class="policy-item-desc">' + esc(ruleDesc) + '</div>';
      }

      return '<div class="policy-item ' + (isPassed ? 'passed' : isFailed ? 'failed' : '') + '">' +
        '<div class="policy-item-header">' +
        '<span class="policy-item-name">' + esc(ruleId) + ': ' + esc(ruleName) +
        '<span class="risk-badge ' + ruleSeverity + '">' + esc(ruleSeverity.toUpperCase()) + '</span>' +
        '</span>' +
        '<span class="policy-item-status ' + (isPassed ? 'passed' : isFailed ? 'failed' : '') + '">' +
        esc(status.toUpperCase()) + '</span>' +
        '</div>' +
        detailHtml +
        '</div>';
    }).join('');
  }

  // Always append baseline evaluation results when no formal rules matched
  const baselineResults = results.filter(r => r.rule_id && r.rule_id.startsWith('baseline.'));
  if (baselineResults.length > 0) {
    html += '<div style="margin-top:16px;border-top:1px solid var(--border-color);padding-top:16px;">';
    html += '<div style="font-size:10px;font-weight:900;text-transform:uppercase;color:var(--text-faint);margin-bottom:10px;letter-spacing:1px;">Heuristic Checks</div>';
    html += baselineResults.map(r => {
      const isPassed = r.status === 'passed' || r.status === 'pass';
      const isFailed = r.status === 'failed' || r.status === 'fail';
      const sev = (r.severity || 'medium').toLowerCase();
      return '<div class="policy-item ' + (isPassed ? 'passed' : isFailed ? 'failed' : '') + '">' +
        '<div class="policy-item-header">' +
        '<span class="policy-item-name">' + esc(r.rule_name || r.rule_id) +
        '<span class="risk-badge ' + sev + '">' + esc(sev.toUpperCase()) + '</span>' +
        '</span>' +
        '<span class="policy-item-status ' + (isPassed ? 'passed' : isFailed ? 'failed' : '') + '">' +
        esc((r.status || 'unknown').toUpperCase()) + '</span>' +
        '</div>' +
        (r.plain_english ? '<div class="policy-item-desc">' + esc(r.plain_english) + '</div>' : '') +
        '</div>';
    }).join('');
    html += '</div>';
  }

  document.getElementById('rulebook-content').innerHTML = html;
}

/** § 6  Analysis */
function renderAnalysis(caseData) {
  const analysis = caseData.analysis;
  if (!analysis) return;

  showSection('analysis-section', 'nav-analysis');

  let html = '';

  // Headline / no-fault indicator
  const headline = analysis.summary?.headline || '';
  const pf = analysis.primary_fault;
  const flags = analysis.secondary_flags || [];
  const allFlags = [
    ...(pf ? [pf] : []),
    ...flags
  ];
  const isHeuristicOnly = allFlags.length > 0 && allFlags.every(f =>
    f.category === 'heuristic_observation' || f.fault_type === 'HEURISTIC_OBSERVATION'
  );
  if (analysis.fault_detected === false) {
    html += `<div class="no-fault-block">&#10003; ${esc(headline || 'No faults detected.')}</div>`;
  } else if (analysis.fault_detected === true) {
    const title = isHeuristicOnly ? 'Pattern Noted' : 'Fault Detected';
    html += `<div class="fault-block">
      <div class="fault-block-title">${title}</div>
      <div class="fault-detail">${esc(headline)}</div>
    </div>`;
  }

  // Primary fault
  if (pf) {
    const isHeuristic = pf.category === 'heuristic_observation' || pf.fault_type === 'HEURISTIC_OBSERVATION';
    const sevLabel = isHeuristic ? 'ADVISORY' : String(pf.severity || '?').toUpperCase();
    html += `
      <div class="fault-block" style="margin-top:14px;">
        <div class="fault-block-title">${isHeuristicOnly ? 'Pattern: ' : 'Primary Fault: '}${esc(pf.fault_type || '?')}</div>
        <div class="fault-detail">
          Severity: <strong>${esc(sevLabel)}</strong>
          ${pf.step_index != null ? ` · At step index: ${esc(pf.step_index)}` : ''}
          ${pf.category ? ` · Category: ${esc(pf.category)}` : ''}
          ${pf.description ? `<br>${esc(pf.description)}` : ''}
        </div>
      </div>`;
  }

  // Secondary flags
  if (flags.length > 0) {
    html += `<div class="secondary-flags">
      <div style="font-size:10px; font-weight:900; text-transform:uppercase; color:var(--text-faint); margin-bottom:8px; letter-spacing:1px;">Secondary Flags (${flags.length})</div>`;
    flags.forEach(f => {
      const isH = f.category === 'heuristic_observation' || f.fault_type === 'HEURISTIC_OBSERVATION';
      const sev = isH ? 'ADVISORY' : (f.severity || '').toUpperCase();
      html += `
        <div class="flag-item">
          <strong>${esc(f.fault_type || f.type || '?')}</strong>
          ${sev ? ` <span class="risk-badge ${isH ? 'low' : (f.severity || 'medium').toLowerCase()}">${esc(sev)}</span>` : ''}
          ${f.step_index != null ? ` · Step ${esc(f.step_index)}` : ''}
          ${f.description ? `<br><span style="font-size:10px; color:#555;">${esc(f.description)}</span>` : ''}
        </div>`;
    });
    html += '</div>';
  }

  // 4-pass analysis diagnostic matrix
  if (allFlags.length > 0) {

    const checks = [
      { label: 'P1: Error_Continuation',  key: 'ERROR_CONTINUATION' },
      { label: 'P2: Constraint_Violation', key: 'CONSTRAINT_VIOLATION' },
      { label: 'P3: Sequence_Violation',   key: 'SEQUENCE_VIOLATION' },
      { label: 'P4: Context_Drop',         key: 'CONTEXT_DROP' },
    ];

    html += `<div class="analysis-diag-matrix">` + checks.map(ch => {
      const matchesKey = (f, key) => {
        if (!f) return false;
        if (f.fault_type === key || f.category === key || f.rule_id === key) return true;
        if (key === 'ERROR_CONTINUATION' && (f.rule_id === 'P1' || f.fault_type === 'ERROR_CONTINUATION')) return true;
        if (key === 'CONSTRAINT_VIOLATION' && (f.rule_id === 'P2' || f.fault_type === 'CONSTRAINT_VIOLATION')) return true;
        if (key === 'SEQUENCE_VIOLATION' && (f.rule_id === 'P3' || f.fault_type === 'SEQUENCE_VIOLATION')) return true;
        if (key === 'CONTEXT_DROP' && (f.rule_id === 'P4' || f.fault_type === 'CONTEXT_DROP')) return true;
        return false;
      };
      const flagged = allFlags.some(f => matchesKey(f, ch.key));
      const isHeuristic = allFlags.some(f => matchesKey(f, ch.key) && (f.category === 'heuristic_observation' || f.fault_type !== 'POLICY_VIOLATION'));
      const label = flagged ? (isHeuristic ? 'PATTERN NOTED' : 'FLAGGED') : 'OK';
      const cls = flagged ? (isHeuristic ? 'warn' : 'flagged') : 'ok';
      return `
        <div class="diag-item">
          <span class="diag-label">${esc(ch.label)}</span>
          <span class="diag-status ${cls}">${label}</span>
        </div>`;
    }).join('') + '</div>';
  }

  document.getElementById('analysis-content').innerHTML = html;
}

/** § 7  Human Attestation */

/**
 * Normalize review data from multiple backend schemas into a flat
 * { reviewed_by, status, notes, reviewed_at } shape the viewer expects.
 *
 * Supports:
 *   - Flat browser/legacy format: { reviewed_by, status, notes }
 *   - ReviewRecord nested format: { reviewed_by, reviews: [{outcome, notes}] }
 *   - Legacy add_review format:    { reviewer, status, notes }
 */
function normalizeReview(raw) {
  if (!raw) return null;

  // Support object passing
  if (typeof raw === 'object' && raw.review) {
    return normalizeReview(raw.review);
  }

  // Extract from recording steps if caseData object is passed or raw has steps
  if (typeof raw === 'object' && Array.isArray(raw.steps) && !raw.reviewed_by && !raw.reviewer) {
    const steps = raw.steps || [];
    const appStep = steps.find(s => s.kind === 'agent.approval.response');
    if (appStep && appStep.content) {
      const c = appStep.content;
      const reviewer = c.reviewer || c.reviewed_by || c.user || 'compliance_officer';
      const isApproved = c.decision === 'approved' || c.approved === true || c.status === 'approved';
      const isRejected = c.decision === 'rejected' || c.approved === false || c.status === 'rejected';
      const status = isApproved ? 'approved' : isRejected ? 'rejected' : 'escalated';
      return {
        reviewed_by: reviewer,
        status: status,
        notes: c.reason || c.notes || (c.action ? `Action ${c.action} approved by human supervisor.` : 'Approved by human supervisor.'),
        reviewed_at: appStep.timestamp || null,
      };
    }
    return null;
  }

  // Legacy key fix: "reviewer" -> "reviewed_by"
  const reviewedBy = raw.reviewed_by || raw.reviewer || null;
  if (!reviewedBy) return null;

  // Already flat format with status — use as-is after key fix
  if (raw.status) {
    return {
      reviewed_by: reviewedBy,
      status: String(raw.status).toLowerCase(),
      notes: raw.notes || raw.comment || '',
      reviewed_at: raw.reviewed_at || null,
    };
  }

  // ReviewRecord nested format: derive status/notes from reviews[]
  if (Array.isArray(raw.reviews) && raw.reviews.length > 0) {
    const outcomes = raw.reviews.map(r => String(r.outcome || '').toLowerCase());
    const hasConfirmed = outcomes.includes('confirmed_fault');
    const nonSkipped = outcomes.filter(o => o !== 'skipped');
    const allDismissed = nonSkipped.length > 0 && nonSkipped.every(o => o === 'dismissed');

    let status = 'escalated';
    if (hasConfirmed) status = 'rejected';
    else if (allDismissed) status = 'approved';

    const notes = raw.reviews
      .map((r, i) => {
        let label = (r.outcome || 'review').toUpperCase().replace(/_/g, ' ');
        if (r.outcome === 'dismissed') label = 'FLAG CLEARED (APPROVED)';
        else if (r.outcome === 'confirmed_fault') label = 'FAULT CONFIRMED (REJECTED)';
        else if (r.outcome === 'skipped') label = 'REVIEW SKIPPED';
        const line = `${i + 1}. ${label}`;
        return r.notes ? `${line}: ${r.notes}` : line;
      })
      .join('\n');

    return {
      reviewed_by: reviewedBy,
      status: status,
      notes: notes || 'No notes provided.',
      reviewed_at: raw.reviewed_at || null,
    };
  }

  // Fallback — at least we have reviewer identity
  return {
    reviewed_by: reviewedBy,
    status: 'unknown',
    notes: raw.notes || raw.comment || 'No notes provided.',
    reviewed_at: raw.reviewed_at || null,
  };
}

function renderAttestation(caseData) {
  const review = normalizeReview(caseData.review || caseData);

  if (review) {
    // Show completed review
    document.getElementById('review-display').classList.remove('hidden');
    document.getElementById('review-form').classList.add('hidden');

    const status = review.status;
    const seal = document.getElementById('review-seal');
    seal.textContent = status.toUpperCase();
    seal.className = 'verdict-seal ' + status;

    document.getElementById('review-content').textContent = review.notes;
    document.getElementById('reviewer-name').textContent = review.reviewed_by;
    document.getElementById('review-date').textContent =
      review.reviewed_at ? fmtDate(review.reviewed_at) : '—';
  } else {
    // Show form
    document.getElementById('review-display').classList.add('hidden');
    document.getElementById('review-form').classList.remove('hidden');
    setupAttestationForm(caseData);
  }
}

let _selectedVerdict = null;

function setupAttestationForm(caseData) {
  // Verdict buttons
  ['approved', 'rejected', 'escalated'].forEach(v => {
    const btn = document.getElementById('btn-' + v);
    if (!btn) return;
    btn.addEventListener('click', () => {
      _selectedVerdict = v;
      document.querySelectorAll('.v-btn').forEach(b => b.classList.remove('selected'));
      btn.classList.add('selected');
    });
  });

  const signBtn = document.getElementById('sign-btn');
  if (!signBtn) return;

  signBtn.addEventListener('click', () => {
    const reviewer = document.getElementById('id-reviewer')?.value.trim() || '';
    const notes = document.getElementById('id-notes')?.value.trim() || '';
    const statusEl = document.getElementById('sign-status');

    if (!reviewer) {
      statusEl.textContent = 'Error: Reviewer identity is required.';
      statusEl.className = 'sign-status-msg err';
      return;
    }
    if (!_selectedVerdict) {
      statusEl.textContent = 'Error: Please select a verdict (Approve / Reject / Escalate).';
      statusEl.className = 'sign-status-msg err';
      return;
    }

    statusEl.textContent = 'Cryptographically sealing artifact…';
    statusEl.className = 'sign-status-msg';

    setTimeout(async () => {
      const review = {
        reviewed_by: reviewer,
        reviewed_at: new Date().toISOString(),
        status: _selectedVerdict,
        notes: notes || 'No additional notes provided.',
      };
      // Apply to caseData so the display reflects the seal
      caseData.review = review;
      renderAttestation(caseData);

      try {
        await downloadReviewedArtifact(caseData, review);
        statusEl.textContent = 'Artifact sealed. Download started.';
        statusEl.className = 'sign-status-msg ok';
      } catch (err) {
        console.error('Seal failed:', err);
        statusEl.textContent = 'Seal failed: ' + (err.message || 'Could not build artifact');
        statusEl.className = 'sign-status-msg err';
      }
    }, 600);
  });
}

// ── Artifact Builder ──────────────────────────────────────────

function htmlSafeJson(obj, indent) {
  return JSON.stringify(obj, null, indent).replace(/\x3c\/(script)/gi, '<\\/$1');
}

function base64ToUint8Array(base64) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

function buildEmbeddedViewerHtml(caseData, reviewRecord) {
  let html = '<!DOCTYPE html>\n' + document.documentElement.outerHTML;

  // Strip existing injected context so epi view can re-inject fresh data
  html = html.replace(
    /\x3cscript id="epi-view-context" type="application\/json">[\s\S]*?\x3c\/script>/ui,
    '\x3cscript id="epi-view-context" type="application/json">{}\x3c/script>'
  );

  // Strip any existing data tags
  html = html.replace(/\x3cscript id="epi-preloaded-cases" type="application\/json">[\s\S]*?\x3c\/script>\s*/ui, '');
  html = html.replace(/\x3cscript id="epi-data" type="application\/json">[\s\S]*?\x3c\/script>\s*/ui, '');

  // Build payload in the multi-case format the viewer reads
  const payload = {
    cases: [{
      source_name: caseData.source_name || caseData.manifest?.workflow_id || 'artifact',
      file_size: caseData.file_size || 0,
      archive_base64: caseData.archive_base64 || null,
      manifest: caseData.manifest || {},
      steps: caseData.steps || [],
      analysis: caseData.analysis || null,
      policy: caseData.policy || null,
      policy_evaluation: caseData.policy_evaluation || null,
      review: reviewRecord,
      environment: caseData.environment || null,
      stdout: caseData.stdout || null,
      stderr: caseData.stderr || null,
      files: caseData.files || {},
      integrity: caseData.integrity || null,
      signature: caseData.signature || null,
    }],
    ui: {
      view: 'case',
      embeddedArtifactMode: true,
    },
  };

  const dataTag = '\x3cscript id="epi-preloaded-cases" type="application/json">' +
    htmlSafeJson(payload, 2) + '\x3c/script>';

  // Inject before </head>
  if (html.includes('</head>')) {
    html = html.replace('</head>', dataTag + '\n</head>');
  }

  return html;
}

async function sha256Hex(buffer) {
  const hash = await crypto.subtle.digest('SHA-256', buffer);
  return Array.from(new Uint8Array(hash))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
}


async function buildReviewedArtifactBytes(caseData, reviewRecord) {
  if (typeof JSZip === 'undefined') {
    throw new Error('JSZip is not available. Cannot build artifact in browser.');
  }

  // If we have the full original artifact, load it and only swap review.json.
  // This preserves every byte the manifest was signed over.
  if (caseData.archive_base64) {
    return buildReviewedFromOriginal(caseData.archive_base64, reviewRecord);
  }

  // Fallback: rebuild from individual files (legacy path for older viewers).
  const zip = new JSZip();
  zip.file('mimetype', 'application/vnd.epi+zip', { compression: 'STORE' });

  const files = caseData.files || {};
  for (const [name, b64] of Object.entries(files)) {
    if (name === 'mimetype' || name === 'review.json') continue;
    zip.file(name, base64ToUint8Array(b64));
  }

  const outcomeMap = {
    approved: 'dismissed',
    rejected: 'confirmed_fault',
    escalated: 'skipped',
  };
  zip.file('review.json', JSON.stringify({
    reviewed_by: reviewRecord.reviewed_by,
    reviewed_at: reviewRecord.reviewed_at,
    reviews: [{
      outcome: outcomeMap[reviewRecord.status] || 'skipped',
      notes: reviewRecord.notes || '',
      reviewed_at: reviewRecord.reviewed_at,
    }],
    review_version: '1.0.0',
  }, null, 2));

  return await zip.generateAsync({ type: 'blob' });
}

async function buildReviewedFromOriginal(archiveBase64, reviewRecord) {
  // Load the original signed artifact, swap only review.json.
  // Mirrors Python's add_review() — preserves all cryptographic hashes.
  var zip = new JSZip();
  var originalBytes = base64ToUint8Array(archiveBase64);
  await zip.loadAsync(originalBytes);

  var outcomeMap = {
    approved: 'dismissed',
    rejected: 'confirmed_fault',
    escalated: 'skipped',
  };
  zip.file('review.json', JSON.stringify({
    reviewed_by: reviewRecord.reviewed_by,
    reviewed_at: reviewRecord.reviewed_at,
    reviews: [{
      outcome: outcomeMap[reviewRecord.status] || 'skipped',
      notes: reviewRecord.notes || '',
      reviewed_at: reviewRecord.reviewed_at,
    }],
    review_version: '1.0.0',
  }, null, 2));

  return await zip.generateAsync({ type: 'blob' });
}

async function downloadReviewedArtifact(caseData, reviewRecord) {
  const blob = await buildReviewedArtifactBytes(caseData, reviewRecord);
  const url = URL.createObjectURL(blob);

  const manifest = caseData.manifest || {};
  const workflowId = manifest.workflow_id || 'artifact';
  const safeName = String(workflowId).replace(/[^a-zA-Z0-9_-]/g, '_');
  const filename = `${safeName}_reviewed.epi`;

  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);

  setTimeout(() => URL.revokeObjectURL(url), 30000);
}

/** § 8  Technical Appendix */
function renderAppendix(caseData) {
  const env = caseData.environment || null;
  const m = caseData.manifest || {};

  const envEl = document.getElementById('env-block');
  if (env && Object.keys(env).length > 0) {
    envEl.textContent = JSON.stringify(env, null, 2);
  } else if (m.spec_version) {
    // Synthesize from manifest fields
    const envInfo = {
      platform: m.platform || '—',
      python_version: m.python_version || '—',
      spec_version: m.spec_version,
      producer_version: m.producer_version || m.spec_version || '—',
      'epi-recorder': m.producer_version || m.spec_version || '—',
      created_at: m.created_at || '—',
    };
    envEl.textContent = JSON.stringify(envInfo, null, 2);
  } else {
    envEl.textContent = 'No environment snapshot available.';
  }

  // Manifest collapsible
  document.getElementById('manifest-json').textContent =
    JSON.stringify(m, null, 2);

  const toggle = document.getElementById('manifest-toggle');
  const body = document.getElementById('manifest-body');
  if (toggle && body) {
    toggle.addEventListener('click', () => {
      toggle.classList.toggle('open');
      body.classList.toggle('open');
    });
  }
}

// ── Boot Animation ────────────────────────────────────────────

function runBoot(onDone) {
  const overlay = document.getElementById('boot-overlay');
  const log = document.getElementById('boot-log');
  if (!overlay || !log) { onDone(); return; }

  const lines = [
    'BOOTING FORENSIC ENGINE',
    'PARSING MANIFEST HASHES',
    'VERIFYING CHAIN INTEGRITY',
    'CALIBRATING EVIDENCE LOG',
    'RENDER READY',
  ];

  let i = 0;
  log.innerHTML = '';

  function addLine() {
    if (i >= lines.length) {
      // Short pause then fade out
      setTimeout(() => {
        overlay.classList.add('fade-out');
        setTimeout(() => {
          overlay.style.display = 'none';
          onDone();
        }, 420);
      }, 180);
      return;
    }
    const div = document.createElement('div');
    div.className = 'boot-line';
    div.style.animationDelay = `${i * 0.05}s`;
    div.textContent = lines[i];
    log.appendChild(div);
    i++;
    setTimeout(addLine, 90);
  }

  addLine();
}

// ── Sidebar Active Link ───────────────────────────────────────

function setupSidebarHighlight() {
  const sections = document.querySelectorAll('#document-root section[id], #doc-header');
  const links = document.querySelectorAll('#forensic-index a');
  if (!sections.length || !links.length) return;

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const id = entry.target.id;
        links.forEach(a => {
          a.classList.toggle('active', a.getAttribute('href') === '#' + id);
        });
      }
    });
  }, { rootMargin: '-20% 0px -75% 0px' });

  sections.forEach(s => observer.observe(s));
}

// ── Main Entry Point ──────────────────────────────────────────

async function init() {
  const data = loadData();

  if (!data || data.cases.length === 0) {
    // No data — show empty state
    document.getElementById('boot-overlay').style.display = 'none';
    document.getElementById('header-title').textContent = 'No Artifact Data';
    document.getElementById('header-uuid').textContent =
      'Open this file via `epi view artifact.epi` to load case data.';
    return;
  }

  // Render first case (single-case viewer)
  const caseData = data.cases[0];
  let context = data.context ? Object.assign({}, data.context) : {};

  // Always attempt real client-side crypto for standalone / export-html delivery.
  // This is the zero-install share path: must show VALID/INVALID, never a punt string.
  try {
    const live = await verifyCaseInBrowser(caseData);
    if (live && live.client_verified) {
      if (live.signature_valid !== null && live.signature_valid !== undefined) {
        context.signature_valid = live.signature_valid;
      }
      if (live.integrity_ok !== null && live.integrity_ok !== undefined) {
        context.integrity_ok = live.integrity_ok;
      }
      if (live.signature_reason) context.signature_reason = live.signature_reason;
      if (live.integrity_reason) context.integrity_reason = live.integrity_reason;
      context.client_verified = true;
    }
  } catch (e) {
    console.warn('[epi] client-side verification failed:', e);
  }

  // Mobile nav toggle
  const navToggle = document.getElementById('nav-toggle');
  const navClose = document.getElementById('nav-close');
  const sidebar = document.getElementById('forensic-index');
  if (navToggle && sidebar) {
    navToggle.addEventListener('click', () => sidebar.classList.add('mobile-open'));
  }
  if (navClose && sidebar) {
    navClose.addEventListener('click', () => sidebar.classList.remove('mobile-open'));
  }
  // Close sidebar when clicking a nav link (mobile)
  if (sidebar) {
    sidebar.querySelectorAll('a').forEach(a => {
      a.addEventListener('click', () => sidebar.classList.remove('mobile-open'));
    });
  }

  runBoot(() => {
    renderHeader(caseData, context);
    renderIntegrity(caseData, context);
    renderCaseContext(caseData);
    renderVerdict(caseData);
    renderEvidence(caseData);
    renderGovernance(caseData);
    renderAnalysis(caseData);
    renderAttestation(caseData);
    renderAppendix(caseData);
    setupSidebarHighlight();
  });
}

// ── Bootstrap ─────────────────────────────────────────────────

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => { init(); });
} else {
  init();
}
