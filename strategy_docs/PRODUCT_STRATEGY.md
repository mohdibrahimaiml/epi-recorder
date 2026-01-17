# EPI Product Strategy: The "Web-First" Trust Platform

## 1. The Core Problem
**EPI currently solves a technical problem:** "How do I capture and sign AI execution data?"
**Enterprise users have a business problem:** "How do I know my organization is safe, compliant, and investing wisely in AI without reading code?"

The "Desktop App" and "Synchronous Proxy" approaches introduce too much friction and risk. The strategy must be **Zero-Friction** and **Low-Risk**.

## 2. The "3-Pillar" Strategy (Revised)

### Pillar A: "Invisible" Recording (The Developer Side)
*Don't block production. Don't ask for permission.*
*   **Solution**: **EPI CI/CD Action**. Automatically runs during build/deploy pipelines. Low risk, high value.
*   **Solution**: **EPI Sidecar (On-Prem)**. An asynchronous logger that runs primarily in the client's VPC. It captures logs *after* the fact, ensuring 0ms latency impact on the critical path.

### Pillar B: Universal Verification (The Consumer Side)
*Don't ask them to install anything.*
*   **Solution**: **The Web Verifier (`verify.epilabs.org`)**.
    *   **Technology**: Client-side WASM/JS.
    *   **Privacy**: **No data is uploaded.** Verification happens in the user's browser memory.
    *   **UX**: Drag & Drop -> "Green Checkmark".
    *   **Distribution**: Send a link. Works on locked-down Bank laptops immediately.

### Pillar C: Enterprise Governance (The Management Side)
*   **Solution**: **EPI Vault (Self-Hosted)**.
    *   Centralized WORM storage for compliance.
    *   Hosted inside the Bank's cloud (AWS/Azure) to satisfy data residency laws.

## 3. Risks & De-Risking (The "Gateway Trap")

| Risk | Old Plan (Sync Proxy) | New Plan (Async Sidecar) |
| :--- | :--- | :--- |
| **Latency** | High (Middleman) | **Zero** (Fire-and-forget) |
| **Reliability** | Single Point of Failure | **Resilient** (App works if EPI is down) |
| **Privacy** | Data leaves VPC | **Local** (Data stays in VPC) |
| **Adoption** | "IT Security Nightmare" | **"Vendor Approved"** |

## 4. User Journey: The Bank Loan Scenario (Revised)

1.  **Dev** pushes code. **EPI GitHub Action** auto-tests and generates a "Baseline Evidence" file.
2.  **Prod** app runs with **EPI Sidecar**. Asynchronously logs live decisions to **EPI Vault** (in Bank's Azure).
3.  **Auditor** asks for proof. Compliance Officer searches Vault.
4.  **Verification**: compliance Officer drags the file to `verify.bank-internal.com` (The hosted Web Verifier).
5.  **Result**: Instant "Green Checkmark" in browser.

## 5. Roadmap

*   **Phase 1: The Visual Trust (Now)**. Build the Client-Side Web Verifier. Prove the crypto works in-browser.
*   **Phase 2: The Invisible Hook**. Build the GitHub Action. Get devs using it.
*   **Phase 3: The Enterprise Moat**. Build the On-Prem Sidecar & Dashboard.
