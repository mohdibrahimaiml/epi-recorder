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

function summarizeStep(step) {
    const kind = step.kind || "unknown";
    const content = step.content || {};

    if (kind === "llm.request") {
        return `Requested model ${content.model || "unknown"} with ${Array.isArray(content.messages) ? content.messages.length : 0} message(s).`;
    }
    if (kind === "llm.response") {
        return truncate(
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
                pillClass: "status-pill status-pill--warn",
                detailTone: "detail-card detail-card--warn",
                detail: "The artifact is unsigned, but the sealed files still match the manifest.",
            };
        }
        if (context.signature_valid && context.integrity_ok) {
            return {
                label: "Signed",
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
            label: "Signed",
            pillClass: "status-pill status-pill--good",
            detailTone: "detail-card detail-card--good",
            detail: "A signature is present on this artifact.",
        };
    }

    return {
        label: "Unsigned",
        pillClass: "status-pill status-pill--warn",
        detailTone: "detail-card detail-card--warn",
        detail: "No signature is present on this artifact.",
    };
}

function deriveCaseSummary(manifest, steps, trustState) {
    const startStep = steps.find((step) => step.kind === "session.start");
    const receivedStep = steps.find((step) => (step.kind || "").includes("received"));
    const decisionStep = steps.find((step) => (step.kind || "").toLowerCase().includes("decision"));

    const title =
        manifest.goal ||
        (startStep && startStep.content && startStep.content.workflow_name) ||
        "Execution Evidence";

    const subtitleParts = [];
    if (receivedStep && receivedStep.content && receivedStep.content.applicant) {
        subtitleParts.push(receivedStep.content.applicant);
    }
    if (receivedStep && receivedStep.content && receivedStep.content.source) {
        subtitleParts.push(`Source: ${receivedStep.content.source}`);
    }
    if (decisionStep && decisionStep.content && decisionStep.content.decision) {
        subtitleParts.push(`Decision: ${decisionStep.content.decision}`);
    }

    const kpis = [
        ["Trust", trustState.label],
        ["Steps", steps.length],
    ];

    if (receivedStep && receivedStep.content && receivedStep.content.loan_amount != null) {
        kpis.push(["Amount", receivedStep.content.loan_amount]);
    }
    if (decisionStep && decisionStep.content && decisionStep.content.confidence != null) {
        kpis.push(["Confidence", decisionStep.content.confidence]);
    }
    if (decisionStep && decisionStep.content && decisionStep.content.decision) {
        kpis.push(["Decision", decisionStep.content.decision]);
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
    host.innerHTML = `<span class="${trustState.pillClass}">${escapeHtml(trustState.label)}</span>`;
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
        subtitle.textContent = summary.subtitle || "Portable execution evidence for offline review.";
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
            items.push("No execution data recorded — this artifact cannot support meaningful fault analysis");
        }
        if (!analysis) {
            items.push("No embedded fault analysis");
        }
        if (!policy) {
            items.push("No embedded policy");
        }
        if (!review) {
            items.push("No human review appended");
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

function renderTrustSummary(manifest, context, trustState, analysis, policy) {
    const host = document.getElementById("trust-summary");
    if (!host) {
        return;
    }

    const details = [
        ["Artifact trust", trustState.label, trustState.detailTone],
        ["Integrity", context ? (context.integrity_ok ? "Intact" : "Compromised") : "Unknown", context && context.integrity_ok === false ? "detail-card detail-card--bad" : "detail-card"],
        ["Signature", context ? (context.has_signature ? "Present" : "Missing") : (manifest.signature ? "Present" : "Missing"), !manifest.signature && context && !context.has_signature ? "detail-card detail-card--warn" : "detail-card"],
        ["Analysis", analysis ? "Embedded" : "Not embedded", analysis ? "detail-card detail-card--good" : "detail-card detail-card--warn"],
        ["Policy", policy ? "Embedded" : "Not embedded", policy ? "detail-card detail-card--good" : "detail-card detail-card--warn"],
    ];

    host.innerHTML = `
        <div class="${trustState.detailTone}">
            <div class="detail-label">Trust state</div>
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

function renderManifestFacts(manifest, context) {
    const host = document.getElementById("manifest-facts");
    if (!host) {
        return;
    }

    const facts = [
        ["Workflow ID", manifest.workflow_id || "Unavailable"],
        ["Created", prettyDate(manifest.created_at)],
        ["Spec Version", manifest.spec_version || "Unknown"],
        ["Files in manifest", context ? String(context.files_checked) : String(Object.keys(manifest.file_manifest || {}).length)],
        ["Public key", manifest.public_key ? truncate(manifest.public_key, 52) : "Unavailable"],
        ["Signature", manifest.signature ? truncate(manifest.signature, 96) : "Missing"],
    ];

    host.innerHTML = facts.map(([label, value]) => `
        <div class="detail-card">
            <div class="detail-label">${escapeHtml(label)}</div>
            <div class="detail-value ${label === "Public key" || label === "Signature" ? "mono" : ""}">${escapeHtml(value)}</div>
        </div>
    `).join("");
}

function renderTimelineHighlights(steps) {
    const host = document.getElementById("timeline-highlights");
    if (!host) {
        return;
    }
    const receivedStep = steps.find((step) => (step.kind || "").includes("received"));
    const decisionStep = steps.find((step) => (step.kind || "").toLowerCase().includes("decision"));
    const chips = [];

    if (receivedStep && receivedStep.content && receivedStep.content.applicant) {
        chips.push(["Applicant", receivedStep.content.applicant]);
    }
    if (receivedStep && receivedStep.content && receivedStep.content.loan_amount != null) {
        chips.push(["Amount", formatNumber(receivedStep.content.loan_amount)]);
    }
    if (decisionStep && decisionStep.content && decisionStep.content.decision) {
        chips.push(["Decision", decisionStep.content.decision]);
    }
    if (decisionStep && decisionStep.content && decisionStep.content.confidence != null) {
        chips.push(["Confidence", decisionStep.content.confidence]);
    }

    host.innerHTML = chips.map(([label, value]) => `
        <span class="meta-pill">
            <span class="meta-pill__label">${escapeHtml(label)}</span>
            <span>${escapeHtml(String(value))}</span>
        </span>
    `).join("");
}

function getStepBadges(step, analysis) {
    const badges = [
        `<span class="timeline-badge timeline-badge--step">#${escapeHtml(step.index)}</span>`,
        `<span class="timeline-badge timeline-badge--kind">${escapeHtml(step.kind || "unknown")}</span>`,
    ];

    if (!analysis) {
        return badges;
    }

    const primary = analysis.primary_fault;
    const secondary = analysis.secondary_flags || [];
    if (primary && primary.step_index === step.index) {
        badges.push('<span class="timeline-badge timeline-badge--fault">Primary fault</span>');
    } else if (secondary.some((item) => item.step_index === step.index)) {
        badges.push('<span class="timeline-badge timeline-badge--warn">Secondary flag</span>');
    }

    return badges;
}

function getTimelineVariant(step, analysis) {
    if (!analysis) {
        return "timeline-item";
    }
    const primary = analysis.primary_fault;
    const secondary = analysis.secondary_flags || [];
    if (primary && primary.step_index === step.index) {
        return "timeline-item timeline-item--fault";
    }
    if (secondary.some((item) => item.step_index === step.index)) {
        return "timeline-item timeline-item--secondary";
    }
    return "timeline-item";
}

function renderTimeline(steps, analysis) {
    const host = document.getElementById("timeline");
    const meta = document.getElementById("timeline-meta");
    if (!host) {
        return;
    }

    if (meta) {
        meta.textContent = analysis
            ? `${steps.length} steps captured. ${analysis.fault_detected ? "Fault analysis is embedded in this artifact." : "Embedded analysis found no fault."}`
            : `${steps.length} steps captured. Raw evidence view.`;
    }

    renderTimelineHighlights(steps);

    host.innerHTML = steps.map((step) => `
        <article class="${getTimelineVariant(step, analysis)}" data-search="${escapeHtml(`${step.kind} ${flattenText(step.content)}`.toLowerCase())}" data-kind="${escapeHtml((step.kind || "").toLowerCase())}">
            <div class="timeline-item__top">
                <div class="timeline-item__left">${getStepBadges(step, analysis).join("")}</div>
                <div class="timeline-item__time">${escapeHtml(prettyDate(step.timestamp))}</div>
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

    card.hidden = false;
    const items = [
        ["Fault detected", analysis.fault_detected ? "Yes" : "No"],
    ];
    if (analysis.summary && analysis.summary.headline) {
        items.push(["Headline", analysis.summary.headline]);
    }
    if (analysis.primary_fault) {
        items.push(["Primary finding", analysis.primary_fault.plain_english || "Unavailable"]);
        items.push(["Why it matters", analysis.primary_fault.why_it_matters || "Review this run before trusting the outcome."]);
        items.push(["Review required", analysis.primary_fault.review_required ? "Yes" : "Recommended"]);
    }
    if (analysis.secondary_flags && analysis.secondary_flags.length) {
        items.push(["Secondary flags", analysis.secondary_flags.length]);
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

function renderPolicy(policy) {
    const card = document.getElementById("policy-card");
    const host = document.getElementById("policy-summary");
    if (!card || !host) {
        return;
    }
    if (!policy || !Array.isArray(policy.rules) || !policy.rules.length) {
        card.hidden = true;
        return;
    }

    card.hidden = false;
    host.innerHTML = `
        <div class="detail-card detail-card--good">
            <div class="detail-label">Policy</div>
            <div class="detail-value">${escapeHtml(policy.system_name || "Unknown")} v${escapeHtml(policy.system_version || "unknown")}</div>
        </div>
        ${policy.rules.map((rule) => `
            <div class="detail-card">
                <div class="detail-label">${escapeHtml(rule.id || "Rule")}</div>
                <div class="detail-value">${escapeHtml(rule.name || rule.type || "Unnamed rule")}</div>
            </div>
        `).join("")}
    `;
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
    const primaryReview = review.reviews && review.reviews[0] ? review.reviews[0] : null;
    const outcome = review.outcome || (primaryReview && primaryReview.outcome) || "Reviewed";
    const reviewer = review.reviewed_by || review.reviewer || "Unknown reviewer";
    const reviewedAt = review.reviewed_at || review.timestamp || null;
    const notes = review.notes || (primaryReview && primaryReview.notes) || "No review notes provided.";

    host.innerHTML = `
        <div class="detail-card detail-card--good">
            <div class="detail-label">Outcome</div>
            <div class="detail-value">${escapeHtml(outcome)}</div>
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
    const steps = Array.isArray(data.steps) ? data.steps : [];
    const analysis = data.analysis || null;
    const policy = data.policy || null;
    const review = data.review || null;

    const trustState = computeTrustState(manifest, context);
    const summary = deriveCaseSummary(manifest, steps, trustState);

    renderTrustBadge(trustState);
    renderGoalBanner(manifest);
    renderSummary(summary, analysis, policy, review);
    renderTrustSummary(manifest, context, trustState, analysis, policy);
    renderManifestFacts(manifest, context);
    renderTimeline(steps, analysis);
    renderAnalysis(analysis);
    renderPolicy(policy);
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
