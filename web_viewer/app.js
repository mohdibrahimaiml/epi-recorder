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

/** Truncate a string to maxLen, appending ellipsis if truncated. */
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
        const name = c.name || c.tool_name || 'unknown';
        const inputStr = JSON.stringify(c.input || c.tool_input || c.parameters || {});
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
        const approved = c.approved === true || c.status === 'approved';
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
        const ruleId = c.rule_id || c.id || '?';
        const status = c.status || '?';
        const note = c.note || c.message || '';
        return `Rule ${ruleId}: ${status}${note ? ' — ' + trunc(note, 120) : ''}`;
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
      const status = String(c.status || '').toLowerCase();
      if (status === 'triggered' || status === 'failed' || status === 'fail') {
        return { htClass: 'ht-fail', kindClass: 'ev-kind-fail' };
      }
      return { htClass: 'ht-policy', kindClass: 'ev-kind-policy' };
    }

    case 'agent.decision': {
      const dec = String(c.decision || c.verdict || '').toUpperCase();
      if (dec === 'APPROVED' || dec === 'PASS' || dec === 'PASSED') {
        return { htClass: 'ht-pass', kindClass: 'ev-kind-pass' };
      }
      if (dec === 'REJECTED' || dec === 'FAIL' || dec === 'FAILED' || dec === 'DENY' || dec === 'DENIED') {
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

  document.getElementById('header-title').textContent = workflowName.replace(/_/g, ' ');
  document.getElementById('header-uuid').textContent = 'UUID: ' + uuid;
  document.getElementById('meta-created').textContent = createdAt;
  document.getElementById('meta-container').textContent = container;
  document.getElementById('meta-spec').textContent = spec;
  document.getElementById('meta-steps').textContent = steps.length + ' step' + (steps.length !== 1 ? 's' : '');
  document.title = workflowName + ' — EPI Forensic Viewer';

  // Status pills
  const pillsEl = document.getElementById('header-pills');
  const intOk = caseData.integrity?.ok !== false;
  // Prefer live context sig_valid, fall back to case payload signature.valid
  const sigValid = context != null ? context.signature_valid : caseData.signature?.valid;
  const sigVerified = sigValid === true;

  pillsEl.innerHTML = '';

  const intPill = document.createElement('span');
  intPill.className = 'pill ' + (intOk ? 'pass' : 'fail');
  intPill.innerHTML = `<span class="pill-dot"></span>${intOk ? 'INTEGRITY VERIFIED' : 'INTEGRITY FAILED'}`;
  pillsEl.appendChild(intPill);

  const sigPill = document.createElement('span');
  if (sigValid == null) {
    sigPill.className = 'pill gray';
    sigPill.innerHTML = `<span class="pill-dot"></span>SIGNATURE UNVERIFIED`;
  } else if (sigVerified) {
    sigPill.className = 'pill pass';
    sigPill.innerHTML = `<span class="pill-dot"></span>SIGNED`;
  } else {
    sigPill.className = 'pill warn';
    sigPill.innerHTML = `<span class="pill-dot"></span>UNSIGNED`;
  }
  pillsEl.appendChild(sigPill);
}

/** § 1  Trust & Integrity */
function renderIntegrity(caseData, context) {
  const m = caseData.manifest || {};
  const integrity = caseData.integrity || {};
  const sig = caseData.signature || {};

  // Integrity indicator
  const intEl = document.getElementById('ind-integrity');
  const intOk = integrity.ok !== false && (context ? context.integrity_ok !== false : true);
  if (intOk) {
    intEl.textContent = 'VERIFIED';
    intEl.className = 'indicator verified';
  } else {
    intEl.textContent = 'COMPROMISED';
    intEl.className = 'indicator failed';
  }

  // Signature indicator — prefer live context, fall back to case payload sig
  const sigEl = document.getElementById('ind-signature');
  const resolvedSigValid = context != null ? context.signature_valid : sig.valid;
  if (resolvedSigValid === true) {
    sigEl.textContent = 'VALID';
    sigEl.className = 'indicator verified';
  } else if (resolvedSigValid === false && sig.valid === false && !context) {
    // Baked viewer — can't verify without epi view
    sigEl.textContent = 'OPEN VIA EPI VIEW TO VERIFY';
    sigEl.className = 'indicator unverified';
    sigEl.style.fontSize = '11px';
  } else if (resolvedSigValid === false) {
    sigEl.textContent = 'INVALID';
    sigEl.className = 'indicator failed';
  } else {
    sigEl.textContent = 'NOT VERIFIED';
    sigEl.className = 'indicator unverified';
  }

  // Identity
  const idEl = document.getElementById('ind-identity');
  const did = m.governance?.did || context?.identity?.did || '';
  const pubkey = m.public_key ? m.public_key.slice(0, 16) : '';
  const signer = context?.signer || context?.identity?.name || '';
  if (did) {
    idEl.textContent = did;
    idEl.className = 'indicator verified';
    idEl.style.fontSize = '11px';
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

  const chainEl = document.getElementById('diag-chain');
  if (context?.facts?.sequence_ok != null) {
    const ok = context.facts.sequence_ok;
    chainEl.textContent = ok ? 'OK' : 'BROKEN';
    chainEl.className = 'diag-status ' + (ok ? 'ok' : 'flagged');
  } else {
    chainEl.textContent = '—';
    chainEl.className = 'diag-status unknown';
  }

  const compEl = document.getElementById('diag-completeness');
  if (context?.facts?.completeness_ok != null) {
    const ok = context.facts.completeness_ok;
    compEl.textContent = ok ? 'OK' : 'INCOMPLETE';
    compEl.className = 'diag-status ' + (ok ? 'ok' : 'flagged');
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

  // Find last agent.decision step
  let decisionStep = null;
  for (let i = steps.length - 1; i >= 0; i--) {
    if (steps[i].kind === 'agent.decision') { decisionStep = steps[i]; break; }
  }

  const decisionContent = decisionStep?.content || {};
  const rawDecision = String(decisionContent.decision || decisionContent.verdict || '').toUpperCase();

  // Determine verdict class and display text
  let verdictClass = 'pending';
  let verdictDisplay = 'PENDING';

  if (rawDecision) {
    verdictDisplay = rawDecision;
    if (['APPROVED', 'PASS', 'PASSED', 'ACCEPT', 'ACCEPTED'].includes(rawDecision)) {
      verdictClass = 'approved';
    } else if (['REJECTED', 'REJECT', 'DENY', 'DENIED', 'FAIL', 'FAILED', 'DECLINE', 'DECLINED'].includes(rawDecision)) {
      verdictClass = 'rejected';
    } else {
      verdictClass = 'pending';
    }
  } else if (analysis) {
    // Fall back to analysis fault detection
    if (analysis.fault_detected === true) {
      verdictClass = 'failed';
      verdictDisplay = 'FAILED';
    } else if (analysis.fault_detected === false) {
      verdictClass = 'passed';
      verdictDisplay = 'PASSED';
    }
  }

  const verdictEl = document.getElementById('verdict-text');
  verdictEl.textContent = verdictDisplay;
  verdictEl.className = 'verdict-text ' + verdictClass;

  // Compliance stats
  if (pe) {
    const total = pe.controls_evaluated || 0;
    const failed = pe.controls_failed || 0;
    const passed = total - failed;
    document.getElementById('compliance-stats').textContent =
      `${passed}/${total} GOVERNANCE CONTROL${total !== 1 ? 'S' : ''} SATISFIED`;
  }

  // Analysis note
  const noteEl = document.getElementById('verdict-note');
  const headline = analysis?.summary?.headline;
  const rationale = decisionContent.rationale || decisionContent.reasoning;
  if (rationale) {
    noteEl.textContent = trunc(rationale, 300);
  } else if (headline) {
    noteEl.textContent = headline;
  }

  // 4-pass diagnostic matrix
  const diagEl = document.getElementById('verdict-diag');
  if (analysis) {
    const allFlags = [
      ...(analysis.primary_fault ? [analysis.primary_fault] : []),
      ...(analysis.secondary_flags || [])
    ];

    const hasFaultType = (type) => allFlags.some(f =>
      f.fault_type === type || f.category === type
    );

    const checks = [
      { label: 'P1: Error_Continuation',  key: 'ERROR_CONTINUATION' },
      { label: 'P2: Constraint_Violation', key: 'CONSTRAINT_VIOLATION' },
      { label: 'P3: Sequence_Violation',   key: 'SEQUENCE_VIOLATION' },
      { label: 'P4: Context_Drop',         key: 'CONTEXT_DROP' },
    ];

    diagEl.innerHTML = checks.map(ch => {
      const flagged = hasFaultType(ch.key);
      return `
        <div class="diag-item">
          <span class="diag-label">${esc(ch.label)}</span>
          <span class="diag-status ${flagged ? 'flagged' : 'ok'}">${flagged ? 'FLAGGED' : 'OK'}</span>
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

  if (!policy?.rules || policy.rules.length === 0) return;

  showSection('governance-basis', 'nav-governance');

  const html = policy.rules.map(rule => {
    const res = (pe.results || []).find(r => r.rule_id === rule.id);
    const status = res?.status || 'unknown';
    const isPassed = status === 'passed' || status === 'pass';
    const isFailed = status === 'failed' || status === 'fail';
    const severity = (rule.severity || 'medium').toLowerCase();

    return `
      <div class="policy-item ${isPassed ? 'passed' : isFailed ? 'failed' : ''}">
        <div class="policy-item-header">
          <span class="policy-item-name">
            ${esc(rule.id)}: ${esc(rule.name)}
            <span class="risk-badge ${severity}">${esc(severity.toUpperCase())}</span>
          </span>
          <span class="policy-item-status ${isPassed ? 'passed' : isFailed ? 'failed' : ''}">
            ${esc(status.toUpperCase())}
          </span>
        </div>
        ${rule.description ? `<div class="policy-item-desc">${esc(rule.description)}</div>` : ''}
      </div>`;
  }).join('');

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
  if (analysis.fault_detected === false) {
    html += `<div class="no-fault-block">&#10003; ${esc(headline || 'No faults detected.')}</div>`;
  } else if (analysis.fault_detected === true) {
    html += `<div class="fault-block">
      <div class="fault-block-title">Fault Detected</div>
      <div class="fault-detail">${esc(headline)}</div>
    </div>`;
  }

  // Primary fault
  const pf = analysis.primary_fault;
  if (pf) {
    html += `
      <div class="fault-block" style="margin-top:14px;">
        <div class="fault-block-title">Primary Fault: ${esc(pf.fault_type || '?')}</div>
        <div class="fault-detail">
          Severity: <strong>${esc(String(pf.severity || '?').toUpperCase())}</strong>
          ${pf.step_index != null ? ` · At step index: ${esc(pf.step_index)}` : ''}
          ${pf.category ? ` · Category: ${esc(pf.category)}` : ''}
          ${pf.description ? `<br>${esc(pf.description)}` : ''}
        </div>
      </div>`;
  }

  // Secondary flags
  const flags = analysis.secondary_flags || [];
  if (flags.length > 0) {
    html += `<div class="secondary-flags">
      <div style="font-size:10px; font-weight:900; text-transform:uppercase; color:var(--text-faint); margin-bottom:8px; letter-spacing:1px;">Secondary Flags (${flags.length})</div>`;
    flags.forEach(f => {
      html += `
        <div class="flag-item">
          <strong>${esc(f.fault_type || f.type || '?')}</strong>
          ${f.severity ? ` <span class="risk-badge ${f.severity.toLowerCase()}">${esc(f.severity.toUpperCase())}</span>` : ''}
          ${f.step_index != null ? ` · Step ${esc(f.step_index)}` : ''}
          ${f.description ? `<br><span style="font-size:10px; color:#555;">${esc(f.description)}</span>` : ''}
        </div>`;
    });
    html += '</div>';
  }

  // 4-pass analysis diagnostic matrix
  const allFlags = [
    ...(pf ? [pf] : []),
    ...flags
  ];

  if (allFlags.length > 0) {
    const checks = [
      { label: 'P1: Error_Continuation',  key: 'ERROR_CONTINUATION' },
      { label: 'P2: Constraint_Violation', key: 'CONSTRAINT_VIOLATION' },
      { label: 'P3: Sequence_Violation',   key: 'SEQUENCE_VIOLATION' },
      { label: 'P4: Context_Drop',         key: 'CONTEXT_DROP' },
    ];

    html += `<div class="analysis-diag-matrix">` + checks.map(ch => {
      const flagged = allFlags.some(f => f.fault_type === ch.key || f.category === ch.key);
      return `
        <div class="diag-item">
          <span class="diag-label">${esc(ch.label)}</span>
          <span class="diag-status ${flagged ? 'flagged' : 'ok'}">${flagged ? 'FLAGGED' : 'OK'}</span>
        </div>`;
    }).join('') + '</div>';
  }

  document.getElementById('analysis-content').innerHTML = html;
}

/** § 7  Human Attestation */
function renderAttestation(caseData) {
  const review = caseData.review;

  if (review && review.reviewed_by) {
    // Show completed review
    document.getElementById('review-display').classList.remove('hidden');
    document.getElementById('review-form').classList.add('hidden');

    const status = (review.status || 'unknown').toLowerCase();
    const seal = document.getElementById('review-seal');
    seal.textContent = status.toUpperCase();
    seal.className = 'verdict-seal ' + status;

    document.getElementById('review-content').textContent =
      review.notes || review.comment || 'No notes provided.';
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

    setTimeout(() => {
      const review = {
        reviewed_by: reviewer,
        reviewed_at: new Date().toISOString(),
        status: _selectedVerdict,
        notes: notes || 'No additional notes provided.',
      };
      // Apply to caseData so the display reflects the seal
      caseData.review = review;
      renderAttestation(caseData);
      statusEl.textContent = '';
    }, 1200);
  });
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

function init() {
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
  const context = data.context;

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
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
