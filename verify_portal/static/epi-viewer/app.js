function loadJsonScript(id) {
    const node = document.getElementById(id);
    if (!node) {
        return null;
    }
    try {
        return JSON.parse(node.textContent || "{}");
    } catch (error) {
        console.error(`Failed to parse ${id}`, error);
        return null;
    }
}

function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value == null ? "" : String(value);
    return div.innerHTML;
}

function prettyDate(value) {
    if (!value) {
        return "Unknown";
    }
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString();
}

function flattenText(value) {
    if (value == null) {
        return "";
    }
    if (typeof value === "string") {
        return value;
    }
    try {
        return JSON.stringify(value);
    } catch {
        return String(value);
    }
}

function truncate(value, maxLength) {
    const text = value == null ? "" : String(value);
    return text.length <= maxLength ? text : `${text.slice(0, maxLength - 1)}...`;
}

function formatJson(value) {
    return JSON.stringify(value == null ? {} : value, null, 2);
}

function formatNumber(value) {
    if (typeof value !== "number") {
        return String(value);
    }
    return new Intl.NumberFormat("en-IN").format(value);
}

function formatMetricValue(label, value) {
    if (value == null) {
        return "Unavailable";
    }
    if (typeof value === "number") {
        if (label.toLowerCase() === "amount") {
            return formatNumber(value);
        }
        return String(value);
    }
    return String(value);
}

function getStepIndex(step, fallbackIndex = 0) {
    if (step && Number.isInteger(step.index)) {
        return step.index;
    }
    return fallbackIndex;
}

function getDisplayStepNumber(step, fallbackIndex = 0) {
    return getStepIndex(step, fallbackIndex) + 1;
}

function getStepTimestamp(step) {
    return (step && (step.timestamp || step.ts)) || null;
}

function normalizeStep(step, fallbackIndex = 0) {
    const normalized = step && typeof step === "object" ? { ...step } : {};
    normalized.index = getStepIndex(normalized, fallbackIndex);
    normalized.kind = normalized.kind || "unknown";
    normalized.content = normalized.content == null ? {} : normalized.content;
    normalized.timestamp = getStepTimestamp(normalized);
    return normalized;
}

function getReviewEntries(review) {
    return review && Array.isArray(review.reviews) ? review.reviews : [];
}

function getReviewableFindings(analysis) {
    const findings = [];
    if (analysis && analysis.primary_fault) {
        findings.push({ ...analysis.primary_fault, _source: "primary" });
    }
    if (analysis && Array.isArray(analysis.secondary_flags)) {
        analysis.secondary_flags
            .filter((flag) => flag && flag.fault_type === "POLICY_VIOLATION")
            .forEach((flag) => findings.push({ ...flag, _source: "secondary" }));
    }
    return findings;
}

function formatReviewOutcome(value) {
    const outcome = value == null ? "" : String(value);
    if (!outcome) {
        return "Pending review";
    }
    const normalized = outcome.toLowerCase();
    if (normalized === "confirmed_fault") {
        return "Confirmed issue";
    }
    if (normalized === "dismissed") {
        return "Dismissed after review";
    }
    if (normalized === "skipped") {
        return "Review skipped";
    }
    if (normalized === "reviewed") {
        return "Reviewed";
    }
    return outcome.replaceAll("_", " ");
}

function getTrustDisplayLabel(label) {
    if (label === "Signed") {
        return "Trusted";
    }
    if (label === "Unsigned") {
        return "Source not proven";
    }
    if (label === "Needs Verification") {
        return "Verify source";
    }
    if (label === "Tampered") {
        return "Do not use";
    }
    return label || "Unknown";
}

function sanitizeFilenamePart(value, fallback = "case") {
    const text = (value == null ? "" : String(value)).trim();
    const normalized = text.replace(/[^a-z0-9]+/gi, "_").replace(/^_+|_+$/g, "");
    return normalized || fallback;
}

function downloadTextFile(filename, content, mimeType = "text/plain;charset=utf-8") {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function getToolName(content) {
    return content.tool || content.name || "tool";
}

function getAgentName(content) {
    return content.agent_name || content.from_agent || "agent";
}

function isAgentStepKind(kind) {
    return kind.startsWith("agent.") || kind.startsWith("tool.");
}

function getAgentApprovalState(steps) {
    const requests = steps.filter((step) => step.kind === "agent.approval.request");
    const responses = steps.filter((step) => step.kind === "agent.approval.response");
    return {
        requests,
        responses,
        pending: requests.length > responses.length,
    };
}

function summarizeStep(step) {
    const kind = step.kind || "unknown";
    const content = step.content || {};

    if (kind === "agent.run.start") {
        const summaryParts = [`Started ${getAgentName(content)}`];
        if (content.user_input != null) {
            summaryParts.push(`for ${truncate(flattenText(content.user_input), 96)}`);
        }
        return `${summaryParts.join(" ")}.`;
    }
    if (kind === "agent.run.end") {
        const duration = content.duration_seconds != null ? ` in ${content.duration_seconds.toFixed ? content.duration_seconds.toFixed(2) : content.duration_seconds}s` : "";
        return `${content.success === false ? "Agent failed" : "Finished"} ${getAgentName(content)}${duration}.`;
    }
    if (kind === "agent.run.error") {
        return truncate(`${getAgentName(content)} error: ${content.error_message || content.error || flattenText(content)}`, 190);
    }
    if (kind === "agent.plan") {
        return truncate(`Plan: ${content.summary || flattenText(content.steps) || "Agent plan recorded."}`, 190);
    }
    if (kind === "agent.message") {
        return truncate(`${content.role || "message"}: ${flattenText(content.content)}`, 190);
    }
    if (kind === "agent.approval.request") {
        const action = content.action || "sensitive action";
        const risk = content.risk_level ? ` (${content.risk_level})` : "";
        return truncate(`Approval requested for ${action}${risk}${content.reason ? `: ${content.reason}` : ""}.`, 190);
    }
    if (kind === "agent.approval.response") {
        const action = content.action || "requested action";
        return truncate(`${content.approved ? "Approved" : "Rejected"} ${action}${content.reviewer ? ` by ${content.reviewer}` : ""}.`, 190);
    }
    if (kind === "agent.handoff") {
        return truncate(`Handed off from ${content.from_agent || getAgentName(content)} to ${content.to_agent || "another agent"}${content.reason ? `: ${content.reason}` : ""}.`, 190);
    }
    if (kind === "agent.memory.read") {
        return truncate(`Read memory ${content.memory_key || "entry"}${content.query ? ` using query ${content.query}` : ""}.`, 190);
    }
    if (kind === "agent.memory.write") {
        return truncate(`${content.operation || "set"} memory ${content.memory_key || "entry"}${content.destination ? ` in ${content.destination}` : ""}.`, 190);
    }
    if (kind === "agent.run.pause") {
        return truncate(`Paused ${getAgentName(content)}${content.waiting_for ? ` waiting for ${content.waiting_for}` : ""}${content.reason ? `: ${content.reason}` : ""}.`, 190);
    }
    if (kind === "agent.run.resume") {
        return truncate(`Resumed ${getAgentName(content)}${content.reason ? `: ${content.reason}` : ""}.`, 190);
    }
    if (kind === "agent.action") {
        return truncate(`${getAgentName(content)} chose tool ${content.tool || "unknown"} ${content.tool_input || ""}`.trim(), 190);
    }
    if (kind === "agent.finish") {
        return truncate(`${getAgentName(content)} finished ${flattenText(content.return_values || content.log || content)}`, 190);
    }
    if (kind === "tool.start" || kind === "tool.call") {
        return truncate(`${getToolName(content)} ${flattenText(content.input || content.tool_input || content)}`, 190);
    }
    if (kind === "tool.end" || kind === "tool.response") {
        return truncate(`${getToolName(content)} returned ${flattenText(content.output || content.result || content)}`, 190);
    }
    if (kind === "tool.error") {
        return truncate(`${getToolName(content)} error: ${content.error || flattenText(content)}`, 190);
    }
    if (kind === "llm.request") {
        return `Requested model ${content.model || "unknown"} with ${Array.isArray(content.messages) ? content.messages.length : 0} message(s).`;
    }
    if (kind === "llm.response") {
        return truncate(
            content.text ||
            content.content ||
            (content.choices && content.choices[0] && content.choices[0].message && content.choices[0].message.content) ||
            "LLM response recorded.",
            190
        );
    }
    if (kind === "llm.error" || kind === "http.error") {
        return truncate(content.error || content.message || flattenText(content), 190);
    }
    if (kind === "http.request") {
        return `${content.method || "GET"} ${truncate(content.url || "", 120)}`;
    }
    if (kind === "http.response") {
        return `HTTP ${content.status_code || "?"} ${truncate(content.url || "", 120)}`;
    }
    if (kind === "stdout.print" || kind === "stderr.print") {
        return truncate(content.text || content.line || flattenText(content), 190);
    }
    if (kind === "DECISION" || kind.toLowerCase().includes("decision")) {
        const decision = content.decision || "Unknown";
        const confidence = content.confidence != null ? ` with confidence ${content.confidence}` : "";
        return `Decision: ${decision}${confidence}.`;
    }
    return truncate(flattenText(content), 190) || "Recorded step.";
}

function computeTrustState(manifest, context) {
    if (context) {
        if (context.signature_valid === false || context.integrity_ok === false) {
            return {
                label: "Tampered",
                displayLabel: "Do not use",
                pillClass: "status-pill status-pill--bad",
                detailTone: "detail-card detail-card--bad",
                detail: context.mismatches_count
                    ? `${context.mismatches_count} mismatch(es) detected during verification.`
                    : "Verification failed.",
            };
        }
        if (!context.has_signature && context.integrity_ok) {
            return {
                label: "Unsigned",
                displayLabel: "Source not proven",
                pillClass: "status-pill status-pill--warn",
                detailTone: "detail-card detail-card--warn",
                detail: "The artifact is unsigned, but the sealed files still match the manifest.",
            };
        }
        if (context.signature_valid && context.integrity_ok) {
            return {
                label: "Signed",
                displayLabel: "Trusted",
                pillClass: "status-pill status-pill--good",
                detailTone: "detail-card detail-card--good",
                detail: context.signer
                    ? `Signature valid and integrity intact. Key: ${context.signer}.`
                    : "Signature valid and integrity intact.",
            };
        }
    }

    if (manifest && manifest.signature) {
        return {
            label: "Needs Verification",
            displayLabel: "Verify source",
            pillClass: "status-pill status-pill--warn",
            detailTone: "detail-card detail-card--warn",
            detail: "A signature is present, but this viewer session did not verify integrity. Open through EPI to verify trust.",
        };
    }

    return {
        label: "Unsigned",
        displayLabel: "Source not proven",
        pillClass: "status-pill status-pill--warn",
        detailTone: "detail-card detail-card--warn",
        detail: "No signature is present on this artifact.",
    };
}

function deriveCaseSummary(manifest, steps, trustState, analysis, policy, review, policyEvaluation) {
    const startStep = steps.find((step) => step.kind === "session.start");
    const agentStart = steps.find((step) => step.kind === "agent.run.start");
    const primaryFault = analysis && analysis.primary_fault ? analysis.primary_fault : null;
    const reviewEntries = getReviewEntries(review);
    const reviewOutcome = review && (review.outcome || (reviewEntries[0] && reviewEntries[0].outcome));
    const approvalState = getAgentApprovalState(steps);

    const title =
        manifest.goal ||
        (agentStart && agentStart.content && agentStart.content.goal) ||
        (agentStart && agentStart.content && agentStart.content.agent_name && `${agentStart.content.agent_name} run`) ||
        (startStep && startStep.content && startStep.content.workflow_name) ||
        manifest.notes ||
        "Decision Case File";

    const subtitleParts = [];
    if (agentStart && agentStart.content && agentStart.content.agent_name) {
        subtitleParts.push(`Agent ${agentStart.content.agent_name}`);
    }
    if (agentStart && agentStart.content && agentStart.content.task_id) {
        subtitleParts.push(`Task ${truncate(agentStart.content.task_id, 12)}`);
    }
    if (agentStart && agentStart.content && agentStart.content.attempt) {
        subtitleParts.push(`Attempt ${agentStart.content.attempt}`);
    }
    if (agentStart && agentStart.content && agentStart.content.resume_from) {
        subtitleParts.push(`Resumed from ${truncate(agentStart.content.resume_from, 12)}`);
    }
    if (startStep && startStep.content && startStep.content.workflow_name && manifest.goal) {
        subtitleParts.push(startStep.content.workflow_name);
    }
    if (manifest.created_at) {
        subtitleParts.push(`Created ${prettyDate(manifest.created_at)}`);
    }
    if (manifest.approved_by) {
        subtitleParts.push(`Approved by ${manifest.approved_by}`);
    }
    if (Array.isArray(manifest.tags) && manifest.tags.length) {
        subtitleParts.push(`Tags: ${manifest.tags.slice(0, 3).join(", ")}`);
    }

    const kpis = [
        ["Case status", trustState.displayLabel || getTrustDisplayLabel(trustState.label)],
        ["Steps", steps.length],
        ["Policy", policy && Array.isArray(policy.rules) ? `${policy.rules.length} rule(s)` : "None"],
        ["Review", formatReviewOutcome(reviewOutcome || (review ? "Reviewed" : ""))],
        ["Primary finding", primaryFault ? (primaryFault.rule_id || primaryFault.fault_type || "Detected") : "None"],
    ];
    if (agentStart && agentStart.content && agentStart.content.session_id) {
        kpis.push(["Agent session", truncate(agentStart.content.session_id, 12)]);
    }
    if (approvalState.requests.length) {
        kpis.push(["Approvals", approvalState.pending ? "Pending" : approvalState.responses.length]);
    }
    if (policyEvaluation && Number.isFinite(policyEvaluation.controls_failed)) {
        kpis.push(["Controls failed", policyEvaluation.controls_failed]);
    }

    if (manifest.metrics && typeof manifest.metrics === "object") {
        Object.entries(manifest.metrics).slice(0, 2).forEach(([label, value]) => {
            kpis.push([label, value]);
        });
    }

    return {
        title,
        subtitle: subtitleParts.join(" | "),
        kpis,
    };
}

function renderTrustBadge(trustState) {
    const host = document.getElementById("trust-badge");
    if (!host) {
        return;
    }
    host.innerHTML = `<span class="${trustState.pillClass}" title="${escapeHtml(trustState.label)}">${escapeHtml(trustState.displayLabel || getTrustDisplayLabel(trustState.label))}</span>`;
}

function renderGoalBanner(manifest) {
    const host = document.getElementById("goal-banner");
    if (!host) {
        return;
    }
    if (!manifest.goal) {
        host.hidden = true;
        return;
    }
    host.hidden = false;
    host.innerHTML = `
        <div class="section-label">Recording Goal</div>
        <p class="muted-text">${escapeHtml(manifest.goal)}</p>
    `;
}

function deriveReviewerVerdict(trustState, analysis, review) {
    const reviewEntry = review && Array.isArray(review.reviews) && review.reviews.length > 0 ? review.reviews[0] : null;
    const reviewOutcome = review && (review.outcome || (reviewEntry && reviewEntry.outcome));
    const hasPrimaryFault = Boolean(analysis && analysis.primary_fault);
    const reviewRequired = Boolean(hasPrimaryFault && analysis.primary_fault.review_required);

    if (trustState.label === "Tampered") {
        return {
            tone: "bad",
            headline: "Do not trust this evidence.",
            impact: "Integrity checks failed, so this artifact may have been modified after recording.",
            action: "Escalate and request the original sealed artifact before any business decision.",
        };
    }

    if (hasPrimaryFault && reviewOutcome === "confirmed_fault") {
        return {
            tone: "bad",
            headline: "Policy violation confirmed by human review.",
            impact: analysis.primary_fault.why_it_matters || "A critical policy rule was violated during execution.",
            action: "Block or remediate this decision path before production use.",
        };
    }

    if (hasPrimaryFault && reviewOutcome === "dismissed") {
        return {
            tone: "warn",
            headline: "Policy flag was reviewed and dismissed.",
            impact: "A rule trigger occurred, but the reviewer marked it as expected in this context.",
            action: "Keep the review note with the case record for audit defensibility.",
        };
    }

    if (hasPrimaryFault) {
        return {
            tone: reviewRequired ? "bad" : "warn",
            headline: reviewRequired ? "Review required before trusting this decision." : "Policy risk detected in this execution.",
            impact: analysis.primary_fault.why_it_matters || "A policy-linked issue was detected in the recorded run.",
            action: "Open Human Review and record a confirm or dismiss decision.",
        };
    }

    if (trustState.label === "Unsigned") {
        return {
            tone: "warn",
            headline: "This case looks intact, but the source is not proven.",
            impact: "No primary fault was detected, and integrity is intact, but the origin cannot be cryptographically confirmed.",
            action: "Use a signed record before external sharing, audit, or high-stakes approval.",
        };
    }

    return {
        tone: "good",
        headline: "No major issue was found in this case.",
        impact: "Recorded execution, trust checks, and embedded analysis do not show a high-risk policy breach.",
        action: "Continue the normal review or approval workflow.",
    };
}

function renderReviewerVerdict(trustState, analysis, review) {
    const host = document.getElementById("reviewer-verdict");
    if (!host) {
        return;
    }
    const verdict = deriveReviewerVerdict(trustState, analysis, review);
    host.hidden = false;
    host.className = `reviewer-verdict reviewer-verdict--${verdict.tone}`;
    host.innerHTML = `
        <div class="section-label">Decision Verdict</div>
        <h3 class="reviewer-verdict__title">${escapeHtml(verdict.headline)}</h3>
        <p class="reviewer-verdict__impact">${escapeHtml(verdict.impact)}</p>
        <div class="reviewer-verdict__meta">
            <span class="status-pill ${
                verdict.tone === "good"
                    ? "status-pill--good"
                    : verdict.tone === "bad"
                        ? "status-pill--bad"
                        : "status-pill--warn"
            }">${
                verdict.tone === "good"
                    ? "Low immediate risk"
                    : verdict.tone === "bad"
                        ? "High immediate risk"
                        : "Needs judgment"
            }</span>
            <span class="meta-pill"><span class="meta-pill__label">Recommended action</span><span>${escapeHtml(verdict.action)}</span></span>
        </div>
    `;
}

function renderSummary(summary, analysis, policy, review) {
    const title = document.getElementById("case-title");
    const subtitle = document.getElementById("case-subtitle");
    const faultBanner = document.getElementById("fault-banner");
    const notices = document.getElementById("summary-notices");
    const kpis = document.getElementById("case-kpis");

    if (title) {
        title.textContent = summary.title;
    }
    if (subtitle) {
        subtitle.textContent = summary.subtitle || "Case summary for offline review.";
    }
    if (faultBanner) {
        if (analysis && analysis.primary_fault) {
            const severity = (analysis.primary_fault.severity || "").toLowerCase();
            const bannerClass = severity === "critical" || severity === "high"
                ? "fault-banner fault-banner--critical"
                : "fault-banner fault-banner--warning";
            faultBanner.hidden = false;
            faultBanner.className = bannerClass;
            faultBanner.innerHTML = `
                <div class="section-label">Primary Fault</div>
                <h3 class="fault-banner__title">${escapeHtml(analysis.summary && analysis.summary.headline ? analysis.summary.headline : analysis.primary_fault.plain_english || "Potential fault detected")}</h3>
                <p class="card__subtitle">${escapeHtml(analysis.primary_fault.why_it_matters || "This execution should be reviewed before it is trusted.")}</p>
                <div class="fault-banner__meta">
                    <span class="status-pill ${analysis.primary_fault.review_required ? "status-pill--bad" : "status-pill--warn"}">${analysis.primary_fault.review_required ? "Human review required" : "Review recommended"}</span>
                    <span class="meta-pill"><span class="meta-pill__label">Severity</span><span>${escapeHtml(analysis.primary_fault.severity || "unknown")}</span></span>
                    <span class="meta-pill"><span class="meta-pill__label">Category</span><span>${escapeHtml((analysis.primary_fault.category || "execution_risk").replaceAll("_", " "))}</span></span>
                    <span class="meta-pill"><span class="meta-pill__label">Step</span><span>${escapeHtml(String(analysis.primary_fault.step_number || "?"))}</span></span>
                </div>
            `;
        } else {
            faultBanner.hidden = true;
        }
    }
    if (notices) {
        const items = [];
        if (summary && summary.kpis && summary.kpis.some(([label, value]) => label === "Steps" && Number(value) === 0)) {
            items.push("No execution data recorded - this artifact cannot support meaningful fault analysis");
        }
        if (!analysis) {
            items.push("No machine analysis included");
        }
        if (!policy) {
            items.push("No policy included");
        }
        if (!review) {
            items.push("No reviewer decision recorded yet");
        }
        notices.hidden = items.length === 0;
        notices.innerHTML = items.map((item) => `<span class="notice-pill">${escapeHtml(item)}</span>`).join("");
    }
    if (kpis) {
        kpis.innerHTML = summary.kpis.map(([label, value]) => `
            <div class="kpi-card">
                <div class="kpi-label">${escapeHtml(label)}</div>
                <div class="kpi-value">${escapeHtml(formatMetricValue(label, value))}</div>
            </div>
        `).join("");
    }
}

function renderTrustSummary(manifest, context, trustState, analysis, policy, policyEvaluation) {
    const host = document.getElementById("trust-summary");
    if (!host) {
        return;
    }

    const signatureValue = context
        ? (context.has_signature
            ? (context.signature_valid ? "Valid" : "Invalid")
            : "Missing")
        : (manifest.signature ? "Present (unverified)" : "Missing");

    const signatureTone = context && context.has_signature
        ? (context.signature_valid ? "detail-card detail-card--good" : "detail-card detail-card--bad")
        : "detail-card detail-card--warn";

    const details = [
        ["Case status", trustState.displayLabel || getTrustDisplayLabel(trustState.label), trustState.detailTone],
        ["Technical trust", trustState.label, trustState.detailTone],
        ["Integrity", context ? (context.integrity_ok ? "Intact" : "Compromised") : "Unknown", context && context.integrity_ok === false ? "detail-card detail-card--bad" : "detail-card"],
        ["Signature", signatureValue, signatureTone],
        ["Analysis", analysis ? "Embedded" : "Not embedded", analysis ? "detail-card detail-card--good" : "detail-card detail-card--warn"],
        ["Policy", policy ? "Embedded" : "Not embedded", policy ? "detail-card detail-card--good" : "detail-card detail-card--warn"],
        ["Control outcomes", policyEvaluation ? "Embedded" : "Not embedded", policyEvaluation ? "detail-card detail-card--good" : "detail-card detail-card--warn"],
    ];

    host.innerHTML = `
        <div class="${trustState.detailTone}">
            <div class="detail-label">What this means for the case</div>
            <div class="detail-value">${escapeHtml(trustState.detail)}</div>
        </div>
        ${details.map(([label, value, klass]) => `
            <div class="${klass}">
                <div class="detail-label">${escapeHtml(label)}</div>
                <div class="detail-value">${escapeHtml(value)}</div>
            </div>
        `).join("")}
    `;
}

function renderGuideSummary(trustState, analysis, policy, review, steps, policyEvaluation) {
    const host = document.getElementById("guide-summary");
    if (!host) {
        return;
    }

    const reviewEntry = review && Array.isArray(review.reviews) && review.reviews.length > 0 ? review.reviews[0] : null;
    const reviewOutcome = review && (review.outcome || (reviewEntry && reviewEntry.outcome));
    const hasPrimaryFault = Boolean(analysis && analysis.primary_fault);
    const approvalState = getAgentApprovalState(Array.isArray(steps) ? steps : []);

    const checks = [
        [
            "1. Trust comes first",
            trustState.label === "Tampered"
                ? "Stop here. Integrity failed, so the record should not be trusted."
                : trustState.label === "Unsigned"
                    ? "The contents are intact, but the origin is not cryptographically proven."
                    : "This artifact passed both integrity and signature checks."
        ],
        [
            "2. Look at the primary finding",
            hasPrimaryFault
                ? "EPI found one main issue to review. Start with the primary fault banner and the linked rule."
                : "No primary policy fault was embedded in this artifact."
        ],
        [
            "3. Check the rulebook",
            policy
                ? "The policy panel shows the exact business rules that were active during the run."
                : "No embedded policy was found, so this case can only be judged from raw execution evidence."
        ],
        [
            "4. Check control outcomes",
            policyEvaluation
                ? policyEvaluation.controls_failed
                    ? `Structured policy evaluation is embedded. ${policyEvaluation.controls_failed} control(s) failed and should be compared with the primary finding.`
                    : "Structured policy evaluation is embedded and shows no failed controls."
                : "No structured policy evaluation is embedded in this artifact yet."
        ],
        [
            "5. Confirm human judgment",
            reviewOutcome
                ? `Human review has already been recorded as: ${formatReviewOutcome(reviewOutcome)}.`
                : "No human review is attached yet. Treat the analyzer output as a machine finding pending judgment."
        ],
        [
            "6. Check agent approvals",
            approvalState.pending
                ? "An approval was requested during execution, but no approval response is embedded yet."
                : approvalState.requests.length
                    ? "Agent approval requests and responses are embedded in the timeline."
                    : "No explicit agent approval checkpoint was recorded in this artifact."
        ],
    ];

    host.innerHTML = checks.map(([label, value]) => `
        <div class="detail-card">
            <div class="detail-label">${escapeHtml(label)}</div>
            <div class="detail-value">${escapeHtml(value)}</div>
        </div>
    `).join("");
}

function buildCaseSummaryText(summary, trustState, analysis, review, policyEvaluation) {
    const verdict = deriveReviewerVerdict(trustState, analysis, review);
    const primaryFault = analysis && analysis.primary_fault ? analysis.primary_fault : null;
    const reviewEntries = getReviewEntries(review);
    const reviewOutcome = review && (review.outcome || (reviewEntries[0] && reviewEntries[0].outcome));
    const lines = [
        summary.title || "Decision Case File",
        summary.subtitle || "Case summary for offline review.",
        "",
        `Case status: ${trustState.displayLabel || getTrustDisplayLabel(trustState.label)}`,
        `Technical trust: ${trustState.label}`,
        `Review status: ${formatReviewOutcome(reviewOutcome || "")}`,
        `Decision verdict: ${verdict.headline}`,
        `Recommended action: ${verdict.action}`,
    ];

    if (primaryFault) {
        lines.push("");
        lines.push(`Primary finding: ${primaryFault.plain_english || primaryFault.rule_id || "Recorded finding"}`);
        lines.push(`Why it matters: ${primaryFault.why_it_matters || "Review before trusting the outcome."}`);
    }

    if (policyEvaluation && Number.isFinite(policyEvaluation.controls_failed)) {
        lines.push(`Controls failed: ${policyEvaluation.controls_failed}`);
    }

    return lines.join("\n");
}

function renderCaseActions(trustState, analysis, review, policyEvaluation) {
    const host = document.getElementById("case-actions");
    if (!host) {
        return;
    }

    const reviewEntry = review && Array.isArray(review.reviews) && review.reviews.length > 0 ? review.reviews[0] : null;
    const reviewOutcome = review && (review.outcome || (reviewEntry && reviewEntry.outcome));
    const hasPrimaryFault = Boolean(analysis && analysis.primary_fault);
    const actions = [];

    if (trustState.label === "Tampered") {
        actions.push(["Stop use of this copy", "Do not approve or rely on this artifact. Ask for the original sealed record."]);
        actions.push(["Escalate ownership", "Send this case to the record owner or security contact before any business action."]);
    } else if (hasPrimaryFault && !reviewOutcome) {
        actions.push(["Review the main issue", "Open the primary finding first and compare it with the linked rule and flagged step."]);
        actions.push(["Record a reviewer decision", "Approve, reject, or escalate the case so the record contains human judgment."]);
    } else if (reviewOutcome === "confirmed_fault") {
        actions.push(["Block or remediate", "A reviewer confirmed the issue. Pause this path until the problem is fixed or formally accepted."]);
        actions.push(["Preserve the case record", "Keep the review notes and trust state together for audit and incident follow-up."]);
    } else if (reviewOutcome === "dismissed") {
        actions.push(["Keep the dismissal note", "The case was reviewed and dismissed. Retain the reviewer note with the record."]);
        actions.push(["Continue normal workflow", "Proceed with standard controls unless another policy or trust issue is present."]);
    } else if (trustState.label === "Unsigned" || trustState.label === "Needs Verification") {
        actions.push(["Verify the source", "Prefer a signed artifact before external sharing, audit use, or sensitive approvals."]);
        actions.push(["Continue with caution", "You can inspect the case, but treat the source as not yet proven."]);
    } else {
        actions.push(["Continue standard review", "The case is trusted and no major issue is currently flagged."]);
        actions.push(["Export if needed", "Share the record or report with operations, compliance, or audit as part of the normal process."]);
    }

    if (policyEvaluation && Number.isFinite(policyEvaluation.controls_failed) && policyEvaluation.controls_failed > 0) {
        actions.push(["Check failed controls", `${policyEvaluation.controls_failed} structured control(s) failed. Compare them with the primary finding before closing the case.`]);
    }

    host.innerHTML = actions.map(([label, value]) => `
        <div class="detail-card">
            <div class="detail-label">${escapeHtml(label)}</div>
            <div class="detail-value">${escapeHtml(value)}</div>
        </div>
    `).join("");
}

function renderReviewWorkspace(summary, trustState, analysis, review, policyEvaluation) {
    const card = document.getElementById("review-workspace-card");
    const host = document.getElementById("review-workspace");
    if (!card || !host) {
        return;
    }

    card.hidden = false;
    const findings = getReviewableFindings(analysis);
    const reviewEntries = getReviewEntries(review);
    const primaryReview = reviewEntries[0] || null;
    const defaultReviewer = review && (review.reviewed_by || review.reviewer) ? (review.reviewed_by || review.reviewer) : "";
    const defaultOutcome = review && (review.outcome || (primaryReview && primaryReview.outcome)) ? (review.outcome || (primaryReview && primaryReview.outcome)) : "confirmed_fault";
    const defaultNotes = review && (review.notes || (primaryReview && primaryReview.notes)) ? (review.notes || (primaryReview && primaryReview.notes)) : "";
    const findingOptions = findings.length
        ? findings.map((fault, index) => {
            const label = fault.plain_english || fault.rule_id || `Finding ${index + 1}`;
            const source = fault._source === "primary" ? "Primary" : "Additional";
            return `<option value="${escapeHtml(String(index))}">${escapeHtml(`${source}: ${truncate(label, 88)}`)}</option>`;
        }).join("")
        : '<option value="">No finding available</option>';

    host.innerHTML = `
        <div class="detail-card">
            <div class="detail-label">What this workspace does</div>
            <div class="detail-value">${findings.length ? "Capture a reviewer decision in plain language, then download a portable review record or a readable case summary." : "This case does not include a reviewable policy finding yet, but you can still download a readable case summary."}</div>
        </div>
        <div class="form-grid">
            <label class="form-field">
                <span class="form-label">Reviewer name</span>
                <input id="reviewer-name-input" class="input" type="text" placeholder="Name or email" value="${escapeHtml(defaultReviewer)}">
            </label>
            <label class="form-field">
                <span class="form-label">Finding</span>
                <select id="review-finding-select" class="input" ${findings.length ? "" : "disabled"}>
                    ${findingOptions}
                </select>
            </label>
            <label class="form-field">
                <span class="form-label">Decision</span>
                <select id="review-outcome-select" class="input" ${findings.length ? "" : "disabled"}>
                    <option value="confirmed_fault" ${defaultOutcome === "confirmed_fault" ? "selected" : ""}>Confirmed issue</option>
                    <option value="dismissed" ${defaultOutcome === "dismissed" ? "selected" : ""}>Dismissed after review</option>
                    <option value="skipped" ${defaultOutcome === "skipped" ? "selected" : ""}>Decide later</option>
                </select>
            </label>
        </div>
        <label class="form-field">
            <span class="form-label">Review notes</span>
            <textarea id="review-notes-input" class="input textarea" placeholder="Add a short explanation for the review decision">${escapeHtml(defaultNotes)}</textarea>
        </label>
        <div class="button-row">
            <button id="download-review-record-button" type="button" class="action-button" ${findings.length ? "" : "disabled"}>Download Review Record</button>
            <button id="download-case-summary-button" type="button" class="action-button action-button--secondary">Download Case Summary</button>
        </div>
        <div id="review-workspace-status" class="workspace-status muted-text"></div>
    `;

    const reviewerInput = document.getElementById("reviewer-name-input");
    const findingSelect = document.getElementById("review-finding-select");
    const outcomeSelect = document.getElementById("review-outcome-select");
    const notesInput = document.getElementById("review-notes-input");
    const reviewButton = document.getElementById("download-review-record-button");
    const summaryButton = document.getElementById("download-case-summary-button");
    const status = document.getElementById("review-workspace-status");
    const caseStem = sanitizeFilenamePart(summary.title || "case", sanitizeFilenamePart(summary.subtitle || "case"));

    if (reviewButton) {
        reviewButton.addEventListener("click", () => {
            if (!findings.length) {
                if (status) {
                    status.textContent = "No reviewable finding is available in this case.";
                }
                return;
            }

            const reviewerName = reviewerInput && reviewerInput.value.trim() ? reviewerInput.value.trim() : "Unknown reviewer";
            const selectedIndex = findingSelect ? Number(findingSelect.value) : 0;
            const selectedFinding = findings[selectedIndex] || findings[0];
            const outcome = outcomeSelect && outcomeSelect.value ? outcomeSelect.value : "confirmed_fault";
            const notes = notesInput ? notesInput.value.trim() : "";
            const timestamp = new Date().toISOString();
            const reviewRecord = {
                review_version: "1.0.0",
                reviewed_by: reviewerName,
                reviewed_at: timestamp,
                reviews: [
                    {
                        fault_step: selectedFinding.step_number || null,
                        rule_id: selectedFinding.rule_id || null,
                        fault_type: selectedFinding.fault_type || null,
                        outcome,
                        notes,
                        reviewer: reviewerName,
                        timestamp,
                    },
                ],
                review_signature: null,
            };

            downloadTextFile(
                `${caseStem}_review_record.json`,
                JSON.stringify(reviewRecord, null, 2),
                "application/json;charset=utf-8"
            );
            if (status) {
                status.textContent = `Downloaded review record for "${selectedFinding.plain_english || selectedFinding.rule_id || "selected finding"}".`;
            }
        });
    }

    if (summaryButton) {
        summaryButton.addEventListener("click", () => {
            const text = buildCaseSummaryText(summary, trustState, analysis, review, policyEvaluation);
            downloadTextFile(`${caseStem}_case_summary.txt`, text);
            if (status) {
                status.textContent = "Downloaded a readable case summary.";
            }
        });
    }
}

function renderManifestFacts(manifest, context) {
    const host = document.getElementById("manifest-facts");
    if (!host) {
        return;
    }

    const fileCount = Number.isFinite(context && context.files_checked)
        ? context.files_checked
        : Object.keys((manifest && manifest.file_manifest) || {}).length;

    const facts = [
        ["Case ID", manifest.workflow_id || "Unavailable"],
        ["Created", prettyDate(manifest.created_at)],
        ["Record format", manifest.spec_version || "Unknown"],
        ["Files sealed in record", String(fileCount)],
        ["Signing key", manifest.public_key ? truncate(manifest.public_key, 52) : "Unavailable"],
        ["Signature", manifest.signature ? truncate(manifest.signature, 96) : "Missing"],
    ];

    host.innerHTML = facts.map(([label, value]) => `
        <div class="detail-card">
            <div class="detail-label">${escapeHtml(label)}</div>
            <div class="detail-value ${label === "Public key" || label === "Signature" ? "mono" : ""}">${escapeHtml(value)}</div>
        </div>
    `).join("");
}

function renderTimelineHighlights(steps, analysis, policy, review, manifest, policyEvaluation) {
    const host = document.getElementById("timeline-highlights");
    if (!host) {
        return;
    }
    const chips = [];
    const reviewEntries = getReviewEntries(review);
    const agentStarts = steps.filter((step) => step.kind === "agent.run.start");
    const handoffs = steps.filter((step) => step.kind === "agent.handoff");
    const memoryReads = steps.filter((step) => step.kind === "agent.memory.read");
    const memoryWrites = steps.filter((step) => step.kind === "agent.memory.write");
    const pauses = steps.filter((step) => step.kind === "agent.run.pause");
    const resumes = steps.filter((step) => step.kind === "agent.run.resume");
    const plans = steps.filter((step) => step.kind === "agent.plan");
    const approvalState = getAgentApprovalState(steps);
    const toolsUsed = new Set(
        steps
            .filter((step) => step.kind === "tool.call" || step.kind === "tool.start")
            .map((step) => {
                const content = step.content || {};
                return getToolName(content);
            })
            .filter(Boolean)
    );

    if (analysis && analysis.primary_fault) {
        chips.push(["Primary fault", analysis.primary_fault.rule_id || analysis.primary_fault.fault_type || "Detected"]);
    }
    if (analysis && Array.isArray(analysis.secondary_flags) && analysis.secondary_flags.length) {
        chips.push(["Secondary flags", analysis.secondary_flags.length]);
    }
    if (policy && Array.isArray(policy.rules)) {
        chips.push(["Rules in force", policy.rules.length]);
    }
    if (policyEvaluation && Number.isFinite(policyEvaluation.controls_evaluated)) {
        chips.push(["Controls evaluated", policyEvaluation.controls_evaluated]);
    }
    if (policyEvaluation && Number.isFinite(policyEvaluation.controls_failed) && policyEvaluation.controls_failed > 0) {
        chips.push(["Controls failed", policyEvaluation.controls_failed]);
    }
    if (reviewEntries.length) {
        chips.push(["Review outcome", formatReviewOutcome(review.outcome || reviewEntries[0].outcome || "Reviewed")]);
    }
    if (agentStarts.length) {
        chips.push(["Agents", agentStarts.length]);
    }
    if (plans.length) {
        chips.push(["Plans", plans.length]);
    }
    if (toolsUsed.size) {
        chips.push(["Tools used", toolsUsed.size]);
    }
    if (approvalState.requests.length) {
        chips.push(["Approvals", approvalState.pending ? "Pending" : approvalState.responses.length]);
    }
    if (handoffs.length) {
        chips.push(["Handoffs", handoffs.length]);
    }
    if (memoryReads.length || memoryWrites.length) {
        chips.push(["Memory ops", memoryReads.length + memoryWrites.length]);
    }
    if (pauses.length || resumes.length) {
        chips.push(["Pauses/resumes", pauses.length + resumes.length]);
    }
    if (Array.isArray(manifest.tags)) {
        manifest.tags.slice(0, 2).forEach((tag) => chips.push(["Tag", tag]));
    }

    host.innerHTML = chips.map(([label, value]) => `
        <span class="meta-pill">
            <span class="meta-pill__label">${escapeHtml(label)}</span>
            <span>${escapeHtml(String(value))}</span>
        </span>
    `).join("");
}

function getStepBadges(step, analysis) {
    const stepIndex = getStepIndex(step);
    const badges = [
        `<span class="timeline-badge timeline-badge--step">#${escapeHtml(getDisplayStepNumber(step))}</span>`,
        `<span class="timeline-badge timeline-badge--kind">${escapeHtml(step.kind || "unknown")}</span>`,
    ];

    if (!analysis) {
        return badges;
    }

    const primary = analysis.primary_fault;
    const secondary = analysis.secondary_flags || [];
    if (primary && primary.step_index === stepIndex) {
        badges.push('<span class="timeline-badge timeline-badge--fault">Primary fault</span>');
    } else if (secondary.some((item) => item.step_index === stepIndex)) {
        badges.push('<span class="timeline-badge timeline-badge--warn">Secondary flag</span>');
    }

    return badges;
}

function getTimelineVariant(step, analysis) {
    const stepIndex = getStepIndex(step);
    if (!analysis) {
        return "timeline-item";
    }
    const primary = analysis.primary_fault;
    const secondary = analysis.secondary_flags || [];
    if (primary && primary.step_index === stepIndex) {
        return "timeline-item timeline-item--fault";
    }
    if (secondary.some((item) => item.step_index === stepIndex)) {
        return "timeline-item timeline-item--secondary";
    }
    return "timeline-item";
}

function clearTimelineFilters() {
    const searchInput = document.getElementById("step-search");
    const filterInput = document.getElementById("step-filter");
    if (searchInput) {
        searchInput.value = "";
    }
    if (filterInput) {
        filterInput.value = "all";
    }
    applyFilters();
}

function jumpToTimelineStep(stepNumber) {
    const numericStep = Number(stepNumber);
    if (!Number.isFinite(numericStep) || numericStep < 1) {
        return;
    }

    clearTimelineFilters();

    const target = document.querySelector(`.timeline-item[data-step-number="${numericStep}"]`);
    if (!target) {
        return;
    }

    const details = target.querySelector("details");
    if (details) {
        details.open = true;
    }

    target.classList.remove("timeline-item--focus");
    void target.offsetWidth;
    target.classList.add("timeline-item--focus");
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    target.focus({ preventScroll: true });

    window.setTimeout(() => {
        target.classList.remove("timeline-item--focus");
    }, 1800);
}

function renderTimeline(steps, analysis, policy, review, manifest, policyEvaluation) {
    const host = document.getElementById("timeline");
    const meta = document.getElementById("timeline-meta");
    if (!host) {
        return;
    }

    const normalizedSteps = steps.map((step, index) => normalizeStep(step, index));

    const hasFault = Boolean(analysis && (analysis.primary_fault || analysis.fault_detected));

    if (meta) {
        meta.textContent = analysis
            ? `${normalizedSteps.length} steps captured. ${hasFault ? "Fault analysis is embedded in this artifact." : "Embedded analysis found no fault."}`
            : `${normalizedSteps.length} steps captured. Raw evidence view.`;
    }

    renderTimelineHighlights(normalizedSteps, analysis, policy, review, manifest, policyEvaluation);

    host.innerHTML = normalizedSteps.map((step) => `
        <article
            id="timeline-step-${escapeHtml(getDisplayStepNumber(step))}"
            class="${getTimelineVariant(step, analysis)}"
            data-step-index="${escapeHtml(getStepIndex(step))}"
            data-step-number="${escapeHtml(getDisplayStepNumber(step))}"
            data-search="${escapeHtml(`${step.kind} ${flattenText(step.content)}`.toLowerCase())}"
            data-kind="${escapeHtml((step.kind || "").toLowerCase())}"
            tabindex="-1"
        >
            <div class="timeline-item__top">
                <div class="timeline-item__left">${getStepBadges(step, analysis).join("")}</div>
                <div class="timeline-item__time">${escapeHtml(prettyDate(getStepTimestamp(step)))}</div>
            </div>
            <p class="timeline-item__summary">${escapeHtml(summarizeStep(step))}</p>
            <div class="timeline-item__details">
                <details>
                    <summary>Show raw step data</summary>
                    <pre>${escapeHtml(formatJson(step.content || {}))}</pre>
                </details>
            </div>
        </article>
    `).join("");
}

function renderAnalysis(analysis) {
    const card = document.getElementById("analysis-card");
    const host = document.getElementById("analysis-summary");
    if (!card || !host) {
        return;
    }
    if (!analysis) {
        card.hidden = true;
        return;
    }

    const hasFault = Boolean(analysis.primary_fault || analysis.fault_detected);
    card.hidden = false;
    const items = [
        ["Fault detected", hasFault ? "Yes" : "No"],
    ];
    if (analysis.summary && analysis.summary.headline) {
        items.push(["Headline", analysis.summary.headline]);
    }
    if (analysis.confidence) {
        items.push(["Confidence", analysis.confidence]);
    }
    if (analysis.mode) {
        items.push(["Analysis mode", analysis.mode.replaceAll("_", " ")]);
    }
    if (analysis.primary_fault) {
        items.push(["Primary finding", analysis.primary_fault.plain_english || "Unavailable"]);
        items.push(["Why it matters", analysis.primary_fault.why_it_matters || "Review this run before trusting the outcome."]);
        items.push(["Review required", analysis.primary_fault.review_required ? "Yes" : "Recommended"]);
        items.push(["How to read this", "Treat this as the machine's best explanation of where the run became risky. Use the linked rule and raw steps below to confirm it."]);
    }
    if (analysis.secondary_flags && analysis.secondary_flags.length) {
        items.push([
            "Secondary flags",
            analysis.secondary_flags
                .slice(0, 3)
                .map((flag) => `${flag.rule_id || flag.fault_type || "Flag"}: ${flag.plain_english || "Review this observation."}`)
                .join(" | "),
        ]);
    }
    if (analysis.disclaimer) {
        items.push(["Disclaimer", analysis.disclaimer]);
    }

    host.innerHTML = items.map(([label, value]) => `
        <div class="detail-card">
            <div class="detail-label">${escapeHtml(label)}</div>
            <div class="detail-value">${escapeHtml(String(value))}</div>
        </div>
    `).join("");
}

function renderPolicy(policy, analysis) {
    const card = document.getElementById("policy-card");
    const host = document.getElementById("policy-summary");
    if (!card || !host) {
        return;
    }
    if (!policy || !Array.isArray(policy.rules) || !policy.rules.length) {
        card.hidden = true;
        return;
    }

    const primaryRuleId = analysis && analysis.primary_fault ? analysis.primary_fault.rule_id : null;
    const scopeBits = [];
    if (policy.scope) {
        ["organization", "team", "application", "workflow", "environment"].forEach((key) => {
            if (policy.scope[key]) {
                scopeBits.push(`${key}=${policy.scope[key]}`);
            }
        });
    }
    card.hidden = false;
    host.innerHTML = `
        <div class="detail-card detail-card--good">
            <div class="detail-label">Policy</div>
            <div class="detail-value">${escapeHtml(policy.system_name || "Unknown")} v${escapeHtml(policy.system_version || "unknown")}</div>
        </div>
        ${policy.policy_id ? `
            <div class="detail-card">
                <div class="detail-label">Policy ID</div>
                <div class="detail-value">${escapeHtml(policy.policy_id)}</div>
            </div>
        ` : ""}
        ${scopeBits.length ? `
            <div class="detail-card">
                <div class="detail-label">Scope</div>
                <div class="detail-value">${escapeHtml(scopeBits.join(", "))}</div>
            </div>
        ` : ""}
        <div class="detail-card">
            <div class="detail-label">What these rules mean</div>
            <div class="detail-value">This is the rulebook that was active during the run. EPI checks the recorded steps against these rules and highlights the rule most closely linked to the primary fault.</div>
        </div>
        ${policy.rules.map((rule) => `
            <div class="detail-card ${primaryRuleId && primaryRuleId === rule.id ? "detail-card--warn" : ""}">
                <div class="detail-label">${escapeHtml(rule.id || "Rule")}</div>
                <div class="detail-value">${escapeHtml(rule.name || rule.type || "Unnamed rule")}</div>
                <div class="detail-subvalue">${escapeHtml(rule.description || "No explanation provided.")}</div>
                <div class="detail-subvalue">${escapeHtml(`Type: ${rule.type || "unknown"} | Severity: ${rule.severity || "unknown"}`)}</div>
                ${(rule.mode || rule.applies_at) ? `<div class="detail-subvalue">${escapeHtml(`Mode: ${rule.mode || "detect"} | Applies at: ${rule.applies_at || "unspecified"}`)}</div>` : ""}
                ${primaryRuleId && primaryRuleId === rule.id ? '<div class="detail-subvalue"><strong>This is the rule linked to the primary fault, so reviewers should compare it with the flagged step below.</strong></div>' : ""}
            </div>
        `).join("")}
    `;
}

function renderPolicyEvaluation(policyEvaluation) {
    const card = document.getElementById("policy-evaluation-card");
    const host = document.getElementById("policy-evaluation-summary");
    if (!card || !host) {
        return;
    }
    if (!policyEvaluation || !Array.isArray(policyEvaluation.results)) {
        card.hidden = true;
        return;
    }

    const failed = policyEvaluation.results.filter((result) => result.status === "failed");
    const passed = policyEvaluation.results.filter((result) => result.status !== "failed");
    const orderedResults = failed.concat(passed);
    const renderStepLinks = (stepNumbers) => {
        if (!Array.isArray(stepNumbers) || !stepNumbers.length) {
            return "";
        }
        const uniqueSteps = Array.from(
            new Set(
                stepNumbers
                    .map((value) => Number(value))
                    .filter((value) => Number.isFinite(value) && value >= 1)
            )
        ).sort((left, right) => left - right);
        if (!uniqueSteps.length) {
            return "";
        }
        return `
            <div class="control-step-links">
                ${uniqueSteps.map((stepNumber) => `
                    <button type="button" class="control-step-link" data-jump-step="${escapeHtml(stepNumber)}">
                        Jump to step ${escapeHtml(stepNumber)}
                    </button>
                `).join("")}
            </div>
        `;
    };

    card.hidden = false;
    host.innerHTML = `
        <div class="detail-card ${failed.length ? "detail-card--warn" : "detail-card--good"}">
            <div class="detail-label">Policy evaluation</div>
            <div class="detail-value">${escapeHtml(policyEvaluation.policy_id || "Unknown policy")}</div>
            <div class="detail-subvalue">${escapeHtml(`${policyEvaluation.controls_evaluated || 0} control(s) evaluated | ${policyEvaluation.controls_failed || 0} failed`)}</div>
        </div>
        <div class="detail-card">
            <div class="detail-label">How to read this</div>
            <div class="detail-value">This panel shows structured control outcomes. Failed controls are the clearest machine-readable view of which policy checks passed or failed during the run.</div>
        </div>
        ${orderedResults.map((result) => `
            <div class="detail-card ${result.status === "failed" ? "detail-card--warn" : "detail-card--good"}">
                <div class="detail-label">${escapeHtml(result.rule_id || "Control")}</div>
                <div class="detail-value">${escapeHtml(result.rule_name || result.rule_type || "Unnamed control")}</div>
                <div class="detail-subvalue">${escapeHtml(`Status: ${result.status || "unknown"} | Mode: ${result.mode || "detect"} | Applies at: ${result.applies_at || "unspecified"}`)}</div>
                <div class="detail-subvalue">${escapeHtml(`Type: ${result.rule_type || "unknown"} | Severity: ${result.severity || "unknown"} | Matches: ${result.match_count || 0}`)}</div>
                <div class="detail-value">${escapeHtml(result.plain_english || "No evaluation summary available.")}</div>
                ${renderStepLinks(result.step_numbers)}
            </div>
        `).join("")}
    `;

    host.querySelectorAll("[data-jump-step]").forEach((node) => {
        node.addEventListener("click", () => {
            jumpToTimelineStep(node.getAttribute("data-jump-step"));
        });
    });
}

function renderReview(review) {
    const card = document.getElementById("review-card");
    const host = document.getElementById("review-summary");
    if (!card || !host) {
        return;
    }
    if (!review) {
        card.hidden = true;
        return;
    }

    card.hidden = false;
    const reviewEntries = getReviewEntries(review);
    const primaryReview = reviewEntries[0] || null;
    const outcome = review.outcome || (primaryReview && primaryReview.outcome) || "Reviewed";
    const reviewer = review.reviewed_by || review.reviewer || "Unknown reviewer";
    const reviewedAt = review.reviewed_at || review.timestamp || null;
    const notes = review.notes || (primaryReview && primaryReview.notes) || "No review notes provided.";
    const signatureStatus = review.review_signature ? "Present" : "Unsigned";
    const entriesHtml = reviewEntries.map((entry, index) => `
        <div class="detail-card">
            <div class="detail-label">Entry ${index + 1}</div>
            <div class="detail-value">${escapeHtml(formatReviewOutcome(entry.outcome || "reviewed"))}</div>
            <div class="detail-subvalue">${escapeHtml(`Rule ${entry.rule_id || "n/a"} | Step ${entry.fault_step || "?"}`)}</div>
            <div class="detail-subvalue">${escapeHtml(entry.notes || "No notes provided.")}</div>
        </div>
    `).join("");

    host.innerHTML = `
        <div class="detail-card detail-card--good">
            <div class="detail-label">Outcome</div>
            <div class="detail-value">${escapeHtml(formatReviewOutcome(outcome))}</div>
        </div>
        <div class="detail-card">
            <div class="detail-label">Reviewed by</div>
            <div class="detail-value">${escapeHtml(reviewer)}</div>
        </div>
        <div class="detail-card">
            <div class="detail-label">Reviewed at</div>
            <div class="detail-value">${escapeHtml(prettyDate(reviewedAt))}</div>
        </div>
        <div class="detail-card">
            <div class="detail-label">Notes</div>
            <div class="detail-value">${escapeHtml(notes)}</div>
        </div>
        <div class="detail-card">
            <div class="detail-label">Review signature</div>
            <div class="detail-value">${escapeHtml(signatureStatus)}</div>
        </div>
        <div class="detail-card">
            <div class="detail-label">Entries recorded</div>
            <div class="detail-value">${escapeHtml(String(reviewEntries.length))}</div>
        </div>
        ${entriesHtml}
    `;
}

function applyFilters() {
    const searchInput = document.getElementById("step-search");
    const filterInput = document.getElementById("step-filter");
    const items = Array.from(document.querySelectorAll(".timeline-item"));
    if (!searchInput || !filterInput || !items.length) {
        return;
    }

    const search = searchInput.value.trim().toLowerCase();
    const filter = filterInput.value;

    items.forEach((item) => {
        const haystack = item.getAttribute("data-search") || "";
        const kind = item.getAttribute("data-kind") || "";
        const flagged = item.classList.contains("timeline-item--fault") || item.classList.contains("timeline-item--secondary");

        const matchesSearch = !search || haystack.includes(search);
        let matchesFilter = true;

        if (filter === "flagged") {
            matchesFilter = flagged;
        } else if (filter === "agent") {
            matchesFilter = kind.includes("agent") || kind.includes("tool");
        } else if (filter === "decision") {
            matchesFilter = kind.includes("decision");
        } else if (filter === "llm") {
            matchesFilter = kind.includes("llm");
        } else if (filter === "errors") {
            matchesFilter = kind.includes("error");
        }

        item.style.display = matchesSearch && matchesFilter ? "" : "none";
    });
}

function init() {
    const data = loadJsonScript("epi-data") || {};
    const context = loadJsonScript("epi-view-context");
    const manifest = data.manifest || {};
    const steps = (Array.isArray(data.steps) ? data.steps : []).map((step, index) => normalizeStep(step, index));
    const analysis = data.analysis || null;
    const policy = data.policy || null;
    const policyEvaluation = data.policy_evaluation || null;
    const review = data.review || null;

    const trustState = computeTrustState(manifest, context);
    const summary = deriveCaseSummary(manifest, steps, trustState, analysis, policy, review, policyEvaluation);

    renderTrustBadge(trustState);
    renderGoalBanner(manifest);
    renderSummary(summary, analysis, policy, review);
    renderReviewerVerdict(trustState, analysis, review);
    renderTrustSummary(manifest, context, trustState, analysis, policy, policyEvaluation);
    renderGuideSummary(trustState, analysis, policy, review, steps, policyEvaluation);
    renderCaseActions(trustState, analysis, review, policyEvaluation);
    renderReviewWorkspace(summary, trustState, analysis, review, policyEvaluation);
    renderManifestFacts(manifest, context);
    renderTimeline(steps, analysis, policy, review, manifest, policyEvaluation);
    renderAnalysis(analysis);
    renderPolicy(policy, analysis);
    renderPolicyEvaluation(policyEvaluation);
    renderReview(review);

    const searchInput = document.getElementById("step-search");
    const filterInput = document.getElementById("step-filter");
    if (searchInput) {
        searchInput.addEventListener("input", applyFilters);
    }
    if (filterInput) {
        filterInput.addEventListener("change", applyFilters);
    }
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
} else {
    init();
}
