// WitnessInbox Durable Object — M0 stub. Full ordered hash-chained log,
// export.jsonl and daily checkpoints land in M1 (plan §6.2).

export class WitnessInbox {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  constructor(_state: DurableObjectState, _env: unknown) {}
  async fetch(): Promise<Response> {
    return Response.json(
      { error: { code: "not_implemented", message: "Hosted witness ships in M1." } },
      { status: 501 },
    );
  }
}
