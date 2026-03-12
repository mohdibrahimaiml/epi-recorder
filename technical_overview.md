# EPI Recorder: How It Works (Simplified)

Think of **EPI** as a **Black Box Flight Recorder** for your AI programs. Just like a flight recorder captures every instrument reading and pilot decision to prove what happened during a flight, EPI captures every prompt, response, and action your AI takes to prove it actually happened.

## The Core Concept

When you run your AI agent with EPI, we don't just "watch" it from the outside. We gently slip a "listening device" into the python process itself. This allows us to hear exactly what the AI hears and see exactly what the AI says, with zero delay.

## The 4 Stages of Evidence

Here is the journey of an EPI recording, explained simply:

### 1. The Setup (Injection)
When you type `epi run my_agent.py`, EPI creates a secure environment for your script. Before your code even runs its first line, EPI is already there, waiting. It's like putting a dashcam in a car before starting the engine.

### 2. The Recording (Monkey Patching)
This is the magic part. EPI uses a technique called **Monkey Patching**.
*   **Imagine:** Your code wants to call OpenAI or Google Gemini. It reaches for the "phone" to make that call.
*   **The Switch:** EPI has swapped the phone with a special one that looks and works exactly the same.
*   **The Action:** When your code makes the call, EPI's phone records the number dialed (the prompt) and the conversation (the response) *before* letting the call go through to the real destination.
*   **Result:** Your code never knows the difference, but EPI has a perfect copy of the interaction.

### 3. The Safety Net (Atomic Storage)
Computers can crash. Power can go out. If your AI agent crashes halfway through, you don't want to lose the evidence of what led up to the crash.
*   **The Old Way:** Saving to a text file. If the program crashes, the file might get cut off or corrupted.
*   **The EPI Way:** We use a tiny, high-speed database engine (SQLite) that writes every single step to the hard drive instantly. It's like writing in a notebook in permanent ink immediately after every event, rather than trying to remember it all and write it down at the end.

### 4. The Seal (Cryptographic Signing)
Once the program finishes, we have a pile of evidence (logs). But how do you prove you didn't edit them?
*   **The Box:** We pack all the logs into a single file (`.epi`).
*   **The Wax Seal:** We use a powerful mathematical tool called a **Cryptographic Signature** (Ed25519). This is like pouring hot wax over the lock of the box and stamping it with your unique ring.
*   **Decentralized Trust (v2.7.1):** We now embed your "identity" (public key) directly inside the seal. This means anyone in the world can verify the box without ever having met you or having your keys on their computer first. It's truly zero-config.
*   **Verification:** If anyone tries to open the box and change a single letter of the logs, the "wax seal" will break. The EPI Viewer checks this seal instantly. If it's broken, it yells **"TAMPERED"**. If it's intact, it confirms **"VERIFIED"**.

---

## Technical Summary (For Developers)

For those who want the specifics:

*   **Patcher**: We use `unittest.mock` style wrapping on `openai`, `google.generativeai`, and `requests` / `httpx`.
*   **Storage**: `sqlite3` in WAL (Write-Ahead Log) mode for atomic, crash-safe writes.
*   **Format**: The `.epi` file is a standard ZIP containing JSONL logs and a standalone HTML viewer.
*   **Security**: Ed25519 digital signatures with **Decentralized Identity** (v2.7.1).
*   **Self-Healing**: Automatic restoration of OS file associations (registry/mime) on every execution (v2.7.1).
