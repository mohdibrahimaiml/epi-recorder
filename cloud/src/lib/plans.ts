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
  startup: { agents: 3, inboxes: 2, evidenceFiles: 500, retentionDays: 365, shareLinks: 3 },
  growth: { agents: 10, inboxes: 10, evidenceFiles: 5000, retentionDays: 2555, shareLinks: null },
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
  return {
    ok: false,
    message: `Plan limit reached (${metric}: ${max} on ${plan}). Upgrade to add more — your data stays.`,
  };
}

export function retentionUntil(plan: PlanId, fromIso: string): string {
  const days = PLAN_LIMITS[plan].retentionDays;
  const from = Date.parse(fromIso);
  if (days === null) return "9999-12-31T00:00:00.000Z"; // custom: effectively unbounded
  return new Date(from + days * 86_400_000).toISOString();
}
