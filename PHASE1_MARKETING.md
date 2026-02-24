# PHASE 1: Irrefutable Visual Proof (Execution Plan)

This document contains everything you need to execute Phase 1 of the marketing sprint.

## 🎬 1. Recording the 60-Second Demo

We have prepared a minimal reproducible LangGraph failure script at `c:\Users\dell\epi-recorder\examples\demo_controlled_failure.py`.

### Structure (Exactly 60 Seconds)

**0–10 sec: The Problem**
1. Run the script: `python examples/demo_controlled_failure.py`
2. Show the terminal logs flying by beautifully.
3. Show the final lines: `Agent pipeline complete.` and `FATAL: Final state verification failed. Data corrupted.`
4. Highlight that **no Python exceptions were raised**. The context is lost. Say nothing fancy, just show the confusion.

**10–30 sec: The Solution**
1. Show the script code in your editor.
2. Toggle `use_epi = True` (This wraps the execution in `with record("agent_failure.epi"):`)
3. Run the script again. 
4. The terminal completes just as before, but now `agent_failure.epi` is generated.

**30–60 sec: Cryptographic Replay**
1. Run `epi view agent_failure.epi` (or double-click the .epi file if your system is configured).
2. The offline .epi viewer opens in the browser instantly.
3. Scroll down the execution timeline to Step 31 (the node where the LLM hallucinated the string instead of int).
4. Click the exact node.
5. Visually highlight the **Prompt**, the **Tool Output**, and the **Cryptographic Hash Signature** confirming no tampering.

---

## 📢 2. Pin It Everywhere

We have already updated the top of the `epi-recorder/README.md` with the headline:
**"AI agents fail silently. Here is cryptographic replay."**
Once you upload the video (to YouTube, Twitter, or as a GitHub GIF), replace the placeholder link and image in the README.

### Social Media Post Templates

Copy/paste these exactly to maximize engagement. Let the video do the selling.

#### 𝕏 (Twitter)
> AI agents fail silently. You come back to a corrupted database and zero context.
>
> We built the flight recorder for agents.
> 1. Wrap your code `with record("agent.epi")`
> 2. Every prompt, tool call, and state transition is saved
> 3. Cryptographically signed.
> 
> [Attach 60s Video]
> Link: github.com/mohdibrahimaiml/epi-recorder

#### 🟦 r/LangChain (Reddit)
**Title:** AI agents fail silently. Here is cryptographic replay.
**Body:**
*(Submit as a Video/Link post natively)*
When your LangGraph agent fails at step 31 overnight, standard logs won't tell you *what* the LLM was thinking or *why* it hallucinated a tool call.

EPI Recorder (`pip install epi-recorder`) captures every state transition, LLM interaction, and system environment into a single, offline `.epi` zip archive. It is cryptographically signed (Ed25519) so traces can be verified for compliance/audits.

Just `epi view` the trace and see the exact node where the context drifted. Open source and plugs straight into LangChain/LangGraph.

Link to repo: https://github.com/mohdibrahimaiml/epi-recorder

#### 🦙 r/LocalLLaMA (Reddit)
**Title:** Debugging 40-step agents is a nightmare. I built an offline "flight recorder" to replay local LLM decisions with signature verification.
**Body:**
*(Submit as a Video post)*
Testing multi-step agents against local models (like deepseek-r1 or Llama-3 via Ollama) means dealing with silent failures and prompt drift.

I built an open-source tool that wraps around LiteLLM/LangChain and dumps every reasoning step, tool call, and context window into an offline `.epi` file. 
- 100% offline (no LangSmith/dashboard needed, it opens an HTML viewer locally).
- Signs traces with Ed25519 for tamper-proof debugging.
- Built-in UI to step backwards through the entire context window of exactly where your model hallucinated.

Repo: https://github.com/mohdibrahimaiml/epi-recorder

#### 🟧 Hacker News (Show HN format)
**Title:** Show HN: EPI – A cryptographic flight recorder for AI agents
**Body:**
AI agents fail silently in production. When a multi-step pipeline goes off the rails at step 31, traditional logs (Cloudwatch, Datadog) rarely capture the full prompt context, tool outputs, and LLM reasoning that caused the drift.

EPI Recorder provides a lightweight, offline-first alternative to heavy dashboards like LangSmith. 
It captures a full snapshot of the execution (all LLM calls, checkpoints, context) into a single `.epi` file, cryptographically signs it with Ed25519, and generates a self-contained HTML viewer. 

You can `epi view trace.epi` completely air-gapped. 

We built this for developers who need irrefutable audit trails (compliance, fintech) and for anyone tired of losing the exact context of why their local or cloud agent failed overnight.

GitHub: https://github.com/mohdibrahimaiml/epi-recorder
Demo Video: [Link to Video]
