#!/usr/bin/env python3
"""
Realistic AI workflow: Content Moderation Agent
An AI agent moderates user-generated content on a platform.
Documents decision chain for regulatory appeal.
"""
from epi_recorder.api import EpiRecorderSession

# Simulated content moderation queue
CONTENT = {
    "post_id": "POST-2025-44129",
    "user_id": "usr_884422",
    "content_type": "text",
    "content": "This is a platform safety test with a fake API key: sk-live-51Hj...fake",
    "context": "political_discussion",
    "user_reputation_score": 0.78,
}

def main():
    with EpiRecorderSession(
        output_path="content_moderation.epi",
        workflow_name="moderation-POST-2025-44129",
        goal="Document content moderation decision for potential appeal",
        notes="High-visibility political post. Decision may be appealed to oversight board.",
        tags=["ai", "moderation", "content-policy", "appealable"],
        auto_sign=True,
    ) as epi:
        # Step 1: Content ingestion
        epi.log_step("content.ingested", {
            "post_id": CONTENT["post_id"],
            "content_type": CONTENT["content_type"],
            "context": CONTENT["context"],
            "user_reputation": CONTENT["user_reputation_score"],
        })

        # Step 2: Automated policy scan
        epi.log_step("policy.scan", {
            "rule_id": "HATE_SPEECH_DETECTED",
            "triggered": False,
            "confidence": 0.12,
            "matched_keywords": [],
        })

        # Step 3: LLM nuanced assessment
        epi.log_step("llm.request", {
            "model": "claude-3-sonnet",
            "prompt": f"Moderate this {CONTENT['context']} post: '{CONTENT['content']}'",
            "system_prompt": "You are a content moderation AI. Classify as: ALLOW, WARN, REMOVE, ESCALATE. Explain reasoning.",
        })

        # Step 4: LLM response
        epi.log_step("llm.response", {
            "output": "DECISION: ALLOW. REASON: Post contains mild skepticism of policy but no hate speech, no incitement to violence, no targeted harassment. Political discourse is protected under platform norms. No action required.",
            "model": "claude-3-sonnet",
            "confidence": 0.89,
        })

        # Step 5: Guardrails check
        epi.log_step("validation.pass", {
            "validator": "guardrails",
            "result": "pass",
            "score": 0.94,
            "checks": ["toxicity", "bias", "factual_accuracy"],
        })

        # Step 6: Human supervisor spot-check
        epi.log_step("human.review", {
            "reviewer": "mod.lead@platform.com",
            "decision": "CONCUR",
            "notes": "Agree with AI assessment. Post is borderline but within policy. Documented for transparency.",
            "escalation_required": False,
        })

        # Step 7: Final action
        epi.log_step("action.taken", {
            "action": "NO_ACTION",
            "visibility": "public",
            "monetization": "enabled",
            "appeal_window_days": 30,
            "audit_trail_id": "AUDIT-2025-44129-MOD",
        })

        print(f"Content moderation recorded: content_moderation.epi")


if __name__ == "__main__":
    main()
