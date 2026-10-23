// Plan limits: single source of truth (plan §5, §6.8). Verification is
// never limited or charged — these gate agents, inboxes, files and links.

export type PlanId = "free" | "design_partner" | "startup" | "growth" | "enterprise";

export interface PlanLimits {
  agents: number | null; // null = custom / unlimited
  inboxes: number | null;
  evidenceFiles: number | null;
  retentionDays: number | null;
  shareLinks: number | null;
}

export const PLAN_LIMITS: Record<PlanId, PlanLimits> = {
  free: { agents: 1, inboxes: 1, evidenceFiles: 50, retentionDays: 30, shareLinks: 1 },
  design_partner: { agents: 10, inboxes: 5, evidenceFiles: 2000, retentionDays: 2555, shareLinks: 10 },
  // HOS pricing note (Oct 2026): relationships are the value metric —
  // Startup 3 (+ add-ons), Growth 15; files per year via retention.
  startup: { agents: 3, inboxes: 3, evidenceFiles: 1000, retentionDays: 365, shareLinks: 3 },
  growth: { agents: 15, inboxes: 15, evidenceFiles: 10000, retentionDays: 2555, shareLinks: null },
  enterprise: { agents: null, inboxes: null, evidenceFiles: null, retentionDays: null, shareLinks: null },
};

export function planOf(raw: string | null | undefined): PlanId {
  if (raw === "design_partner" || raw === "startup" || raw === "growth" || raw === "enterprise") return raw;
  return "free";
}

/** Null (custom) never blocks. Returns an upgrade hint when blocked. */
export function limitAllows(
  plan: PlanId,
  metric: keyof PlanLimits,
  current: number,
): { ok: true } | { ok: false; message: string } {
  const max = PLAN_LIMITS[plan][metric];
  if (max === null) return { ok: true };
  if (current < max) return { ok: true };
  return { ok: false, message: limitMessage(plan, metric, max) };
}

const PLAN_NAMES: Record<PlanId, string> = {
  free: "free",
  design_partner: "design-partner",
  startup: "Startup",
  growth: "Growth",
  enterprise: "Enterprise",
};

// Customer-facing words: a recorder ("agent") and its witness inbox are both
// "a customer" in the product; never leak internal metric names.
const METRIC_WORDS: Record<keyof PlanLimits, [string, string]> = {
  agents: ["customer", "customers"],
  inboxes: ["customer", "customers"],
  evidenceFiles: ["stored run", "stored runs"],
  retentionDays: ["day of storage", "days of storage"],
  shareLinks: ["share link", "share links"],
};

const LIMIT_TIPS: Partial<Record<keyof PlanLimits, string>> = {
  shareLinks: " Revoke an old link in Share links, or",
  agents: " Close a customer you no longer need, or",
  inboxes: " Close a customer you no longer need, or",
};

function limitMessage(plan: PlanId, metric: keyof PlanLimits, max: number): string {
  const [one, many] = METRIC_WORDS[metric];
  const tip = LIMIT_TIPS[metric] ?? "";
  return (
    `Your ${PLAN_NAMES[plan]} plan includes ${max} ${max === 1 ? one : many}.` +
    `${tip}${tip ? " see" : " See"} https://epilabs.org/plans to add more — your data stays.`
  );
}

export function retentionUntil(plan: PlanId, fromIso: string): string {
  const days = PLAN_LIMITS[plan].retentionDays;
  const from = Date.parse(fromIso);
  if (days === null) return "9999-12-31T00:00:00.000Z"; // custom: effectively unbounded
  return new Date(from + days * 86_400_000).toISOString();
}
