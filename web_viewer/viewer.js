/**
 * EPI Forensic Reasoning Engine v4.0.3
 * Combined with Brutalist Audit UI v4.0.2
 */
(function () {
  "use strict";

  const esc = (str) => {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  };

  const fmtT = (v) => {
    if (!v) return '00:00:00.000';
    const d = new Date(v);
    return isNaN(d.getTime()) ? '00:00:00.000' : d.toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit', fractionalSecondDigits: 3 });
  };

  // --- 2. PIPELINE ---

  async function initialize() {
    try {
      const data = loadArtifactData();
      if (!data) return;

      const trust = computeTrust(data);
      const graph = buildCausalGraph(data.steps || []);
      const faults = extractFaults(data, graph);
      const decision = deriveDecision(data, trust, faults);

      renderDocument(data, trust, graph, faults, decision);
      boot();

    } catch (err) {
      console.error("FATAL_REASONING_ERROR:", err);
      displayFatalError(err);
    }
  }

  function loadArtifactData() {
    const raw = document.getElementById('epi-data')?.textContent;
    let data = (raw && raw !== 'null') ? JSON.parse(raw) : null;
    
    const preloadedRaw = document.getElementById('epi-preloaded-cases')?.textContent;
    const preloaded = preloadedRaw ? JSON.parse(preloadedRaw) : null;
    
    if (preloaded && preloaded.cases && preloaded.cases.length > 0) {
      const pData = preloaded.cases[0];
      if (!data) {
        data = pData;
      } else {
        // Merge integrity and signature from preloaded CLI check into offline data!
        if (pData.integrity) data.integrity = pData.integrity;
        if (pData.signature) data.signature = pData.signature;
      }
      if (preloaded.ui) data.ui = preloaded.ui;
    }
    return data;
  }

  // --- 3. TRUST ENGINE ---

  function computeTrust(data) {
    const m = data.manifest || {};
    // If integrity is completely missing, it means we opened a local offline HTML copy
    const isUnverifiedLocal = data.integrity === undefined;
    const integrity = data.integrity || { ok: false, checked: 0, mismatches: [] };
    const sig = data.signature || { valid: false, reason: 'missing' };

    let score = 100;
    const reasons = [];

    const hasSig = !!(m.trust?.signature || m.signature || data.signature);
    if (!hasSig) { score -= 25; reasons.push("signature missing"); }
    else if (!sig.valid && !isUnverifiedLocal) { score -= 40; reasons.push(`signature invalid: ${sig.reason}`); }
    else if (hasSig) { reasons.push("cryptographic signature exists"); }

    if (!isUnverifiedLocal && !integrity.ok) { score -= 50; reasons.push("payload integrity failed"); }
    else if (!isUnverifiedLocal && integrity.mismatches?.length > 0) {
      const p = Math.min(30, integrity.mismatches.length * 10);
      score -= p;
      reasons.push(`${integrity.mismatches.length} file hash mismatches`);
    } else if (!isUnverifiedLocal) { reasons.push("payload hashes matched manifest"); }

    const steps = data.steps || [];
    const sequenceOk = steps.every((s, i) => i === 0 || s.prev_hash);
    if (!sequenceOk) { score -= 15; reasons.push("chain sequence broken"); }
    else { reasons.push("event chain sequence complete"); }

    if (steps.length === 0 && !data.policy) { score -= 15; reasons.push("artifact content incomplete"); }

    let level = "verified";
    if (isUnverifiedLocal) level = "unverified_local";
    else if (score <= 0 || !integrity.ok) level = "tampered";
    else if (score < 30) level = "invalid";
    else if (score < 60) level = "partial";
    else if (score < 85) level = "unsigned";

    return { level, score, reasons, fatal: (level === "tampered" || level === "invalid") };
  }

  // --- 4. CAUSALITY GRAPH ALGORITHM ---

  function buildCausalGraph(steps) {
    const nodes = steps.map((s, i) => ({
      id: i,
      ts: s.timestamp,
      kind: (s.kind || 'step').toLowerCase(),
      actor: s.content?.model || s.content?.tool || s.content?.actor || 'system',
      summary: summarizeStep(s),
      raw: s,
      edges: []
    }));

    for (let i = 0; i < nodes.length - 1; i++) {
      nodes[i].edges.push({ to: i + 1, type: "sequential" });
    }

    nodes.forEach((node, i) => {
      const s = node.raw;
      if (s.kind?.includes('retry') || s.kind?.includes('correction') || s.content?.is_retry) {
        const trigger = findLast(nodes, i, n => n.kind.includes('error') || n.kind.includes('fail'));
        if (trigger) trigger.edges.push({ to: i, type: "reaction" });
      }
      if (s.kind === 'tool.call' || s.kind === 'tool_call') {
        const instructor = findLast(nodes, i, n => n.kind.includes('llm') || n.kind.includes('agent'));
        if (instructor) instructor.edges.push({ to: i, type: "tool_dependency" });
      }
      if (s.kind === 'validation' || s.kind?.includes('guard')) {
        const target = findLast(nodes, i, n => n.kind === 'llm.response' || n.kind === 'tool.result' || n.kind === 'output');
        if (target) target.edges.push({ to: i, type: "validation" });
      }
      if (s.kind === 'agent.decision' || s.kind === 'decision') {
        const relevant = nodes.slice(Math.max(0, i - 3), i);
        relevant.forEach(r => r.edges.push({ to: i, type: "decision_basis" }));
      }
    });

    return nodes;
  }

  function findLast(nodes, currentIdx, predicate) {
    for (let i = currentIdx - 1; i >= 0; i--) { if (predicate(nodes[i])) return nodes[i]; }
    return null;
  }

  // --- 5. FAULT EXTRACTION ---

  function extractFaults(data, graph) {
    const analysis = data.analysis || {};
    const pe = data.policy_evaluation || {};
    const faults = [];
    if (analysis.primary_fault) faults.push({ ...analysis.primary_fault, level: 'critical' });
    (analysis.secondary_flags || []).forEach(f => faults.push({ ...f, level: 'warning' }));
    graph.forEach(n => {
      const s = n.raw;
      const c = s.content || {};
      
      // Framework-specific Status Mapping (Guardrails/AGT)
      const isGuardrails = c.subtype === 'guardrails';
      const isFailed = c.status === 'fail' || c.status === 'error' || c.status === 'failed';
      const isCorrected = c.status === 'corrected' || c.correction?.applied;

      // Direct error kind
      if (n.kind.includes('error') || n.kind.includes('fail') || (isGuardrails && isFailed)) {
        faults.push({ step_id: n.id, type: 'EXECUTION_ERROR', msg: n.summary || 'Critical execution failure', level: 'warning' });
      }

      // Detection of Self-Correction (Transparency requirement)
      if (isCorrected) {
        faults.push({ step_id: n.id, type: 'SELF_CORRECTION', msg: 'Guardrails automatically corrected agent output', level: 'info' });
      }

      // Error inside content (Silent failure check)
      if (c.error || c.status === 'error' || (c.status === 'failed' && !isGuardrails)) {
        faults.push({ step_id: n.id, type: 'ERROR_CONTINUATION', msg: `Internal error detected: ${c.error || 'failed'}`, level: 'warning' });
      }
    });
    (pe.results || []).filter(r => r.status === 'failed').forEach(r => {
      faults.push({ type: 'POLICY_VIOLATION', rule_id: r.rule_id || r.control_id, msg: r.plain_english || 'Policy constraint violated', level: 'critical' });
    });
    return faults;
  }

  // --- 6. DECISION DERIVATION ---

  function deriveDecision(data, trust, faults) {
    const steps = data.steps || [];
    const agentStep = steps.find(s => s.kind === 'agent.decision' || s.kind === 'decision');

    let decision = "pending";
    let basis = "unattested";
    let explanation = "No human attestation recorded.";

    if (trust.level === "tampered" || trust.level === "invalid") {
      decision = trust.level; basis = "integrity_failure"; explanation = "Artifact trust score is below safety threshold.";
    } else if (faults.some(f => f.level === 'critical' && f.type === 'POLICY_VIOLATION')) {
      decision = "rejected"; basis = "policy_violation"; explanation = "Critical policy violations detected.";
    } else if (faults.some(f => f.level === 'critical' || f.type === 'EXECUTION_ERROR')) {
      decision = "escalated"; basis = "validation_failure"; explanation = "Unresolved execution errors require escalation.";
    }
    return { state: decision, basis, explanation, supporting_steps: faults.map(f => f.step_id).filter(id => id !== undefined) };
  }

  // --- 7. RENDERING ---

  function renderDocument(data, trust, graph, faults, decision) {
    const m = data.manifest || {};
    const pe = data.policy_evaluation || {};

    document.getElementById('meta-uuid').textContent = m.workflow_id || 'UNKNOWN';
    document.getElementById('meta-date').textContent = m.created_at || 'N/A';

    // NEW: Traffic-light verdict card
    renderVerdictCard(data, trust, faults);

    // NEW: Policy drift warning
    checkPolicyDrift(data);

    // TRUST BADGE
    const badge = document.getElementById('trust-badge');
    if (badge) {
      badge.style.display = 'inline-block';
      if (trust.level === 'verified') {
        badge.className = 'trust-badge verified';
        badge.textContent = '[ CRYPTOGRAPHICALLY SIGNED & VERIFIED ]';
      } else if (trust.level === 'unsigned' || trust.level === 'partial') {
        badge.className = 'trust-badge unsigned';
        badge.textContent = '[ UNSIGNED ARTIFACT - HASHES MATCH ]';
      } else if (trust.level === 'unverified_local') {
        badge.className = 'trust-badge unverified-local';
        badge.textContent = '[ UNVERIFIED LOCAL HTML COPY ]';
      } else {
        badge.className = 'trust-badge tampered';
        badge.textContent = '[ ⚠️ TAMPERED OR CORRUPT PAYLOAD ]';
      }
    }

    // 1.0 GOVERNANCE
    const rulebook = document.getElementById('rulebook-content');
    if (data.policy?.rules) {
      rulebook.innerHTML = data.policy.rules.map(r => {
        const res = pe.results?.find(res => (res.rule_id === r.id || res.control_id === r.id));
        return `
          <div class="policy-item ${res?.status === 'failed' ? 'failed' : 'passed'}">
            <div style="font-weight:900;">${esc(r.id)}: ${esc(r.name)} [${esc(r.severity || 'MEDIUM').toUpperCase()}]</div>
            <div class="policy-item-desc">${esc(r.description)}</div>
          </div>
        `;
      }).join('');
    }

    // 5.0 EVIDENCE
    const timeline = document.getElementById('evidence-table');
    const heatmap = document.getElementById('evidence-heatmap');
    const startTime = graph.length > 0 ? new Date(graph[0].ts).getTime() : 0;

    graph.forEach((node, idx) => {
      const row = document.createElement('div');
      const c = node.raw.content || {};
      const isGuardrails = c.subtype === 'guardrails';
      
      let rowClass = 'row';
      if (decision.supporting_steps.includes(node.id)) rowClass += ' highlighted';
      if (isGuardrails && c.status === 'corrected') rowClass += ' status-corrected';
      
      row.className = rowClass;
      const delta = startTime ? ((new Date(node.ts).getTime() - startTime) / 1000).toFixed(3) : '0.000';
      
      // Build summary with status badges
      let summaryHtml = `<strong>${node.actor.toUpperCase()}:</strong> ${node.summary}`;
      if (isGuardrails && c.status) {
        summaryHtml += ` <span class="indicator ${c.status}">${c.status.toUpperCase()}</span>`;
      }

      row.innerHTML = `
        <div class="row-ts">
          <span>${fmtT(node.ts)}</span>
          <span style="font-size:8px; color:#aaa;">+${delta}s</span>
          <span class="merkle-link">⛓️ <span class="merkle-chain-id">${(node.raw.prev_hash || 'START').substring(0, 8)}</span></span>
        </div>
        <div class="row-kind">${esc(node.kind)}</div>
        <div class="row-summary">
          ${summaryHtml}
          ${renderEdges(node)}
          ${renderFrameworkBlocks(node)}
        </div>
        <div class="row-json">${esc(JSON.stringify(node.raw, null, 2))}</div>
      `;
      row.onclick = () => row.classList.toggle('expanded');
      timeline.appendChild(row);

      if (heatmap) {
        const tick = document.createElement('div');
        tick.className = 'heatmap-tick ' + node.kind.toLowerCase().replace('.', '-');
        if (faults.some(f => f.step_id === node.id)) tick.classList.add('fault');
        tick.onclick = (e) => { e.stopPropagation(); row.scrollIntoView({ behavior: 'smooth' }); row.click(); };
        heatmap.appendChild(tick);
      }
    });

    // 5.0 APPENDIX
    document.getElementById('env-content').textContent = JSON.stringify(data.environment || {}, null, 2);
    document.getElementById('manifest-content').textContent = JSON.stringify(m, null, 2);
  }

  // --- 7b. VERDICT CARD RENDERER ---

  function renderVerdictCard(data, trust, faults) {
    const card = document.getElementById('verdict-card');
    if (!card) return;

    const analysis = data.analysis || {};
    const verdictShort = analysis.verdict_short || null;
    const verdictDetail = analysis.verdict || null;
    const faultDetected = analysis.fault_detected ||
      faults.some(f => f.level === 'critical' || f.type === 'POLICY_VIOLATION');
    const noPolicy = (analysis.mode === 'heuristic_only') || !data.policy;

    let icon, cls, shortText, detailText;

    if (trust.level === 'tampered' || trust.level === 'invalid') {
      icon = '\u{1F6A8}'; cls = 'tamper';
      shortText = '\u26a0\ufe0f Artifact Integrity Failed';
      detailText = 'This artifact may have been tampered with or corrupted. Do not rely on its content.';
    } else if (faultDetected) {
      icon = '\u274c'; cls = 'fail';
      shortText = verdictShort || '\u274c Compliance Failed';
      detailText = verdictDetail || 'A rule violation or execution error was detected in this run.';
    } else {
      icon = '\u2705'; cls = 'pass';
      shortText = verdictShort || '\u2705 No Fault Detected';
      detailText = verdictDetail || 'No rule violations or heuristic anomalies were flagged in this run.';
    }

    card.className = `verdict-card ${cls}`;
    card.style.display = 'flex';
    document.getElementById('verdict-icon').textContent = icon;
    document.getElementById('verdict-short').textContent = shortText;
    document.getElementById('verdict-detail').textContent = detailText;

    // Action button: scroll to relevant section
    const actionsEl = document.getElementById('verdict-actions');
    if (actionsEl) {
      const target = faultDetected ? '#governance-basis' : '#evidence-trace';
      const label = faultDetected ? 'View Violations' : 'View Evidence';
      actionsEl.innerHTML = `<a href="${target}" class="verdict-action-btn">${label}</a>`;
    }

    // No-policy notice
    if (noPolicy) {
      const notice = document.getElementById('no-policy-notice');
      if (notice) {
        notice.style.display = 'block';
        notice.innerHTML = '\u26a0\ufe0f <strong>No compliance policy was used for this run.</strong> ' +
          'EPI used heuristic analysis only (less precise). ' +
          'Run <code>epi policy init</code> to define rules for your workflow.';
      }
    }
  }

  // --- 7c. POLICY DRIFT WARNING ---

  function checkPolicyDrift(data) {
    const banner = document.getElementById('policy-drift-banner');
    if (!banner || !data.policy) return;

    const embeddedVersion = data.policy.policy_version;
    // The manifest may record the policy version at the time of packing
    const manifestPolicyVersion = data.manifest && data.manifest.policy &&
      data.manifest.policy.version;

    if (
      embeddedVersion &&
      manifestPolicyVersion &&
      embeddedVersion !== manifestPolicyVersion
    ) {
      banner.style.display = 'block';
      banner.textContent =
        '\u26a0\ufe0f Policy version mismatch: this artifact was recorded with policy v' +
        manifestPolicyVersion + ', but the embedded policy is v' + embeddedVersion +
        '. Compliance results may differ from the original analysis.';
    }
  }

  function summarizeStep(s) {
    const c = s.content || {};
    if (c.subtype === 'guardrails') {
      const statusStr = c.status?.toUpperCase() || 'STEP';
      const iterInfo = c.iteration_index !== undefined ? ` [Iter ${c.iteration_index}]` : '';
      return `${statusStr}: Guardrails validation${iterInfo}`;
    }
    if (s.kind === 'llm.request') return `Requested completion from ${c.model}`;
    if (s.kind === 'llm.response') return `Generated ${c.usage?.total_tokens || '?'} tokens`;
    if (s.kind === 'tool.call') return `Invoked ${c.tool}(${JSON.stringify(c.arguments)})`;
    if (s.kind === 'tool.result') return `Output: ${typeof c.output === 'string' ? c.output.substring(0, 100) : 'data'}`;
    if (s.kind === 'validation') return `${c.status.toUpperCase()} check on ${c.subject || 'output'}`;
    return c.summary || c.goal || c.status || 'Internal step';
  }

  function renderEdges(node) {
    if (!node.edges.length) return '';
    return `<div class="edge-list">${node.edges.map(e => `<span class="edge-tag ${e.type}">${e.type.replace('_', ' ')} → #${e.to}</span>`).join('')}</div>`;
  }

  function renderFrameworkBlocks(node) {
    const c = node.raw.content || {};
    if (c.subtype !== 'guardrails') return '';
    
    let html = '';
    
    // Correction Block
    if (c.correction?.applied) {
      html += `
        <div class="status-box status-corrected" style="padding:10px; margin-top:10px; font-size:10px;">
          <div class="box-label" style="margin-bottom:5px;">Self-Correction Applied</div>
          <div style="color:var(--pass); font-weight:900;">Output was automatically modified by Guardrails validators.</div>
          <div style="margin-top:5px; font-style:italic;">Target: ${esc(c.output?.guarded || 'Corrected data')}</div>
        </div>
      `;
    }

    // Validator Matrix
    if (c.validators && c.validators.length > 0) {
      html += `
        <table class="validator-matrix">
          <thead>
            <tr><th>Validator</th><th>Status</th><th>Rationale</th></tr>
          </thead>
          <tbody>
            ${c.validators.map(v => `
              <tr>
                <td>${esc(v.validator_name)}</td>
                <td class="status-${v.status}">${esc(v.status.toUpperCase())}</td>
                <td style="font-size:9px;">${esc(v.reason || 'No violation')}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;
    }
    
    return html;
  }

  async function boot() {
    const log = document.getElementById('boot-log');
    if (!log) return;
    const add = (m) => { const d = document.createElement('div'); d.textContent = m; log.appendChild(d); };
    add("BOOTING_FORENSIC_ENGINE_v4.0.3");
    await new Promise(r => setTimeout(r, 100));
    add("VERIFYING_CHAIN_INTEGRITY...");
    add("COMPUTING_CAUSAL_DAG...");
    await new Promise(r => setTimeout(r, 100));
    add("DERIVING_AUDIT_VERDICT...");
    add("RENDER_SUCCESS");
    setTimeout(() => document.getElementById('boot-overlay').style.display = 'none', 300);
  }

  function displayFatalError(err) {
    const root = document.getElementById('document-root');
    if (root) root.innerHTML = `<div class="status-box rejected" style="margin:50px;"><h1>FATAL_REASONING_ERROR</h1><pre>${err.stack}</pre></div>`;
  }

  window.addEventListener('DOMContentLoaded', initialize);

})();
