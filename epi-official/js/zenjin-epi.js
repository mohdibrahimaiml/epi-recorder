/**
 * EPI LABS — ZENJIN-GRADE TELEMETRY & CHOREOGRAPHY ENGINE (zenjin-epi.js)
 * - 160ms hover-intent popover mega-menu + Escape key handler
 * - IntersectionObserver scroll-reveal (.z-reveal / .z-reveal--media)
 * - Launch film walkthrough video controller (matches Zenjin launch film)
 * - 6 deterministic multi-beat SVG telemetry state machines
 * - Hero 3-layer verification monolith state machine
 * - Context-aware Post-Upload Tamper Lab (only active AFTER a file is uploaded/loaded)
 * - Smooth single-open FAQ accordion
 * - Full prefers-reduced-motion compliance
 */
(function () {
  "use strict";

  var REDUCED_MOTION =
    typeof window !== "undefined" &&
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ── 1. Theme Controller (Dark default like Zenjin, Light toggleable) ── */
  var THEME_KEY = "epi-zenjin-theme";
  function getTheme() {
    try {
      var saved = localStorage.getItem(THEME_KEY);
      if (saved === "light" || saved === "dark") return saved;
    } catch (e) {}
    return "dark";
  }

  function applyTheme(t) {
    document.documentElement.setAttribute("data-theme", t);
    if (document.body) document.body.setAttribute("data-theme", t);
    document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
      var isDark = t === "dark";
      btn.setAttribute("aria-label", isDark ? "Switch to light mode" : "Switch to dark mode");
      btn.setAttribute("title", isDark ? "Switch to light mode" : "Switch to dark mode");
      btn.innerHTML = isDark ? "&#9788;" : "&#9790;";
    });
  }

  applyTheme(getTheme());

  document.addEventListener("click", function (e) {
    var btn = e.target && e.target.closest && e.target.closest("[data-theme-toggle]");
    if (!btn) return;
    e.preventDefault();
    var next = document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light";
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch (err) {}
    applyTheme(next);
  });

  /* ── 2. Navbar Hover-Intent Mega-Menu (160ms grace timer) & Mobile Menu ── */
  function initNavbar() {
    var wrap = document.querySelector(".z-nav__dropdown-wrap");
    var trigger = wrap ? wrap.querySelector("[data-dropdown-trigger]") : null;
    var closeTimer = null;

    function clearTimer() {
      if (closeTimer) {
        clearTimeout(closeTimer);
        closeTimer = null;
      }
    }

    function setOpen(open) {
      if (!wrap || !trigger) return;
      wrap.setAttribute("data-open", open ? "true" : "false");
      trigger.setAttribute("aria-expanded", open ? "true" : "false");
    }

    if (wrap && trigger) {
      wrap.addEventListener("mouseenter", function () {
        clearTimer();
        setOpen(true);
      });
      wrap.addEventListener("mouseleave", function () {
        clearTimer();
        closeTimer = setTimeout(function () {
          setOpen(false);
        }, 160);
      });
      trigger.addEventListener("click", function (e) {
        if (window.innerWidth < 1024) {
          e.preventDefault();
          var isOpen = wrap.getAttribute("data-open") === "true";
          setOpen(!isOpen);
        }
      });
    }

    var burger = document.getElementById("burger");
    var mmenu = document.getElementById("mmenu");
    if (burger && mmenu) {
      burger.addEventListener("click", function () {
        var open = !mmenu.classList.contains("open");
        if (open) { mmenu.classList.add("open"); } else { mmenu.classList.remove("open"); }
        burger.setAttribute("aria-expanded", open ? "true" : "false");
      });
      mmenu.querySelectorAll("a").forEach(function (a) {
        a.addEventListener("click", function () {
          mmenu.classList.remove("open");
          burger.setAttribute("aria-expanded", "false");
        });
      });
    }

    window.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        clearTimer();
        setOpen(false);
        if (mmenu && mmenu.classList.contains("open")) {
          mmenu.classList.remove("open");
          if (burger) burger.setAttribute("aria-expanded", "false");
        }
      }
    });
  }

  /* ── 3. Scroll-Triggered Reveal (Matches Zenjin top 88% trigger) ────── */
  function initScrollReveal() {
    var items = document.querySelectorAll(".z-reveal");
    if (!items.length) return;
    if (REDUCED_MOTION || !("IntersectionObserver" in window)) {
      items.forEach(function (el) {
        el.classList.add("is-visible");
      });
      return;
    }
    var obs = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            obs.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -10% 0px" }
    );
    items.forEach(function (el) {
      obs.observe(el);
    });
  }

  /* ── 4. CLI Copy Button ─────────────────────────────────────────────── */
  function initCopyButtons() {
    document.querySelectorAll("[data-copy-text]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var text = btn.getAttribute("data-copy-text") || "pip install epi-recorder";
        var orig = btn.textContent;
        function done() {
          btn.textContent = "Copied ✓";
          setTimeout(function () {
            btn.textContent = orig;
          }, 1600);
        }
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(done).catch(done);
        } else {
          done();
        }
      });
    });
  }

  /* ── 5. Walkthrough Video Player (Matches Zenjin Launch Film Section) ─ */
  function initWalkthroughVideo() {
    var video = document.getElementById("walkthroughVideo");
    var playBtn = document.getElementById("walkthroughPlayBtn");
    if (!video || !playBtn) return;

    playBtn.addEventListener("click", function () {
      playBtn.style.display = "none";
      video.controls = true;
      video.muted = false;
      var p = video.play();
      if (p && typeof p.catch === "function") {
        p.catch(function () {
          video.muted = true;
          video.play().catch(function () {});
        });
      }
    });
  }

  /* ── 6. Hero Monolith 3-Layer Interactive State Machine ─────────────── */
  function initHeroMonolith() {
    var root = document.getElementById("heroMonolith");
    if (!root) return;

    var states = [
      {
        key: "seal",
        cmd: "$ epi verify claim-4821.epi",
        badge: "01 / SEAL · VALID",
        badgeColor: "#10b981",
        lines: [
          { k: "CONTAINER", v: "envelope-v2 (HTML+ZIP)", c: "#d4d4d8" },
          { k: "MANIFEST", v: "JCS RFC 8785 · 7 files", c: "#d4d4d8" },
          { k: "SHA-256", v: "142/142 steps intact", c: "#10b981" },
          { k: "SIGNATURE", v: "ed25519:6090c0… VALID", c: "#10b981" },
          { k: "RFC 3161", v: "TSA root verified offline", c: "#10b981" },
          { k: "PROOF", v: "Unaltered since sealing.", c: "#90909b" }
        ]
      },
      {
        key: "identity",
        cmd: "$ epi verify claim-4821.epi --policy strict",
        badge: "02 / IDENTITY · PINNED",
        badgeColor: "#f59e0b",
        lines: [
          { k: "SEAL", v: "Verified (SHA-256 + Ed25519)", c: "#10b981" },
          { k: "SIGNER", v: "6090 c0d9 8a14 (acme-prod)", c: "#f59e0b" },
          { k: "TRUST PIN", v: "Pinned via epi keys trust", c: "#10b981" },
          { k: "WITNESS", v: "WITNESSED · receipt #00419", c: "#06b6d4" },
          { k: "DECISION", v: "PASS (strict claim-ready)", c: "#10b981" },
          { k: "PROOF", v: "Unpinned keys show WARN.", c: "#90909b" }
        ]
      },
      {
        key: "policy",
        cmd: "$ epi analyze claim-4821.epi",
        badge: "03 / POLICY · FAULT",
        badgeColor: "#f43f5e",
        lines: [
          { k: "SEAL", v: "Verified · record intact", c: "#10b981" },
          { k: "RULEBOOK", v: "epi_policy.json (sealed)", c: "#d4d4d8" },
          { k: "STEP #038", v: "issue_refund ($4,800 > $1k)", c: "#f43f5e" },
          { k: "APPROVAL", v: "approval.response MISSING", c: "#f43f5e" },
          { k: "VERDICT", v: "FAULT — review required", c: "#f43f5e" },
          { k: "PROOF", v: "Seal PASS + Policy FAULT.", c: "#90909b" }
        ]
      }
    ];

    var cmdEl = document.getElementById("hmCmd");
    var badgeEl = document.getElementById("hmBadge");
    var rowsEl = document.getElementById("hmRows");
    var tabs = root.querySelectorAll("[data-hm-tab]");
    var idx = 0;
    var timer = null;

    function render(i) {
      idx = i;
      var st = states[i];
      if (cmdEl) cmdEl.textContent = st.cmd;
      if (badgeEl) {
        badgeEl.textContent = st.badge;
        badgeEl.style.color = st.badgeColor;
        badgeEl.style.borderColor = st.badgeColor + "66";
        badgeEl.style.backgroundColor = st.badgeColor + "1a";
      }
      if (rowsEl) {
        rowsEl.innerHTML = st.lines
          .map(function (l) {
            return (
              '<div style="display:flex;justify-content:space-between;align-items:baseline;gap:8px;padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.06)">' +
              '<span style="color:var(--text-muted);flex-shrink:0;font-size:0.68rem">' +
              l.k +
              "</span>" +
              '<span style="color:' +
              l.c +
              ';text-align:right;word-break:break-word">' +
              l.v +
              "</span></div>"
            );
          })
          .join("");
      }
      tabs.forEach(function (t, ti) {
        var active = ti === i;
        t.setAttribute("aria-selected", active ? "true" : "false");
        t.style.borderBottomColor = active ? st.badgeColor : "transparent";
        t.style.color = active ? "var(--foreground)" : "var(--text-muted)";
        t.style.backgroundColor = active ? "rgba(255,255,255,0.05)" : "transparent";
      });
    }

    tabs.forEach(function (t, ti) {
      t.addEventListener("click", function () {
        if (timer) clearInterval(timer);
        render(ti);
      });
    });

    render(0);
    if (!REDUCED_MOTION) {
      timer = setInterval(function () {
        render((idx + 1) % states.length);
      }, 3800);
    }
  }

  /* ── 7. The 6 Multi-Beat Telemetry Stages (Matches Zenjin Module 7494) ── */
  var STAGE_SCRIPTS = {
    envelope: {
      accent: "#10b981",
      beats: [
        {
          label: "01 Capture · steps.jsonl",
          text: "Every prompt, tool call, and decision appends to a SHA-256 hash-linked timeline.",
          activeNodes: ["n-steps"]
        },
        {
          label: "02 Redact · Default Privacy",
          text: "API keys, bearer tokens, emails, cards, and SSNs are scrubbed before bytes hit disk.",
          activeNodes: ["n-steps", "n-env"]
        },
        {
          label: "03 Inventory · manifest.json",
          text: "Every member file is SHA-256 hashed into a JCS-canonical (RFC 8785) manifest.",
          activeNodes: ["n-steps", "n-env", "n-manifest"]
        },
        {
          label: "04 Sign · Ed25519 Seal",
          text: "The canonical manifest is signed with Ed25519. Flipping a single byte invalidates the seal.",
          activeNodes: ["n-manifest", "n-sig"]
        },
        {
          label: "05 Notarize · RFC 3161 TSA",
          text: "Only a 32-byte hash is sent to a public TSA; epi verify checks the token offline.",
          activeNodes: ["n-sig", "n-tsa"]
        },
        {
          label: "06 Polyglot · Envelope v2 (.epi)",
          text: "Valid HTML + ZIP binary: double-click to inspect in any browser, or verify via CLI.",
          activeNodes: ["n-steps", "n-env", "n-manifest", "n-sig", "n-tsa", "n-epi"]
        }
      ]
    },
    trust: {
      accent: "#f59e0b",
      beats: [
        {
          label: "01 Layer 1 · Seal Integrity",
          text: "Checks SHA-256 file hashes, step prev_hash chain, outer viewer hash, and Ed25519 signature.",
          activeNodes: ["t-seal"]
        },
        {
          label: "02 Unpinned Key · Honest Amber",
          text: "Valid signature from an unknown key reports NOT_PINNED (WARN) — never a false green badge.",
          activeNodes: ["t-seal", "t-id"]
        },
        {
          label: "03 Out-of-Band Pin · epi keys trust",
          text: "Auditor pins the vendor's key fingerprint out of band; --policy strict now enforces identity.",
          activeNodes: ["t-seal", "t-id"]
        },
        {
          label: "04 Layer 3 · Policy & Faults",
          text: "epi analyze evaluates the sealed run against epi_policy.json without altering the seal.",
          activeNodes: ["t-seal", "t-id", "t-policy"]
        }
      ]
    },
    capture: {
      accent: "#8b5cf6",
      beats: [
        {
          label: "01 Scan · LLM Providers",
          text: "wrap_openai() and wrap_anthropic() capture model calls, parameters, and token usage.",
          activeNodes: ["c-openai", "c-anthropic", "c-litellm"]
        },
        {
          label: "02 Hook · Agent Orchestrators",
          text: "EpiCallbackHandler and LangGraph checkpoints bind multi-agent spans into one trace.",
          activeNodes: ["c-langchain", "c-langgraph", "c-otel"]
        },
        {
          label: "03 Proxy · epi gateway serve",
          text: "Self-hosted fail-closed capture proxy records full payloads outside application code.",
          activeNodes: ["c-gateway", "c-pytest", "c-agt"]
        },
        {
          label: "04 Seal · Deterministic .epi",
          text: "All 9 capture paths emit the exact same Envelope v2 evidence artifact.",
          activeNodes: ["c-openai", "c-anthropic", "c-litellm", "c-langchain", "c-langgraph", "c-otel", "c-gateway", "c-pytest", "c-agt"]
        }
      ]
    },
    witness: {
      accent: "#06b6d4",
      beats: [
        {
          label: "01 Seal · Vendor Bucket",
          text: "Full .epi artifact stays in your local storage or BYO bucket — prompts never leave.",
          activeNodes: ["w-recorder"]
        },
        {
          label: "02 Witness · Hash-Only Push",
          text: "Only the 32-byte SHA-256 digest and key fingerprint are sent to EPI Cloud Witness.",
          activeNodes: ["w-recorder", "w-witness"]
        },
        {
          label: "03 Receipt · Ed25519 Stamp",
          text: "Witness appends the hash to an ordered log and returns a signed Ed25519 receipt.",
          activeNodes: ["w-witness", "w-checkpoint"]
        },
        {
          label: "04 Share · /t/{slug}#k=token",
          text: "Share token stays in the URL #fragment (never sent in referrer headers or server logs).",
          activeNodes: ["w-checkpoint", "w-reviewer"]
        },
        {
          label: "05 Verify · Offline Evidence Pack",
          text: "Reviewer downloads the ZIP pack and runs epi verify --policy strict --witness-log offline.",
          activeNodes: ["w-recorder", "w-witness", "w-checkpoint", "w-reviewer"]
        }
      ]
    },
    policy: {
      accent: "#f43f5e",
      beats: [
        {
          label: "01 Span #01 · llm.request",
          text: "Agent receives refund claim ORD-9001 ($4,800) and queries order lookup tool.",
          activeNodes: ["p-span1", "p-span2"]
        },
        {
          label: "02 Span #03 · High-Value Action",
          text: "Agent invokes tool.call issue_refund with amount=4800.00 (policy cap is $1,000).",
          activeNodes: ["p-span1", "p-span2", "p-span3"]
        },
        {
          label: "03 Guard · Prohibition Fired",
          text: "epi_policy.json rule R-04 flags missing agent.approval.response before disbursement.",
          activeNodes: ["p-span3", "p-span4"]
        },
        {
          label: "04 Sealed · policy_evaluation.json",
          text: "Fault analysis is hashed and sealed inside the .epi so the violation cannot be hidden.",
          activeNodes: ["p-span1", "p-span2", "p-span3", "p-span4"]
        }
      ]
    },
    audit: {
      accent: "#6366f1",
      beats: [
        {
          label: "01 Input · Sealed .epi Runs",
          text: "Cryptographically verified execution records form the raw input for governance review.",
          activeNodes: ["a-center", "a-annex"]
        },
        {
          label: "02 Group · AIUC-1 & Annex IV",
          text: "epi verify --aiuc1 and epi annex pack organize evidence into structured auditor templates.",
          activeNodes: ["a-center", "a-annex", "a-aiuc"]
        },
        {
          label: "03 Register · SCITT Transparency",
          text: "Embed COSE/SCITT receipts (local or independent ledger) inside artifacts/scitt/.",
          activeNodes: ["a-center", "a-scitt", "a-claims"]
        },
        {
          label: "04 Export · Auditor Pack",
          text: "Deliver a self-contained offline bundle for underwriters, bank risk teams, and regulators.",
          activeNodes: ["a-center", "a-annex", "a-aiuc", "a-scitt", "a-claims"]
        }
      ]
    }
  };

  function initTelemetryStages() {
    document.querySelectorAll("[data-telemetry-stage]").forEach(function (stageEl) {
      var key = stageEl.getAttribute("data-telemetry-stage");
      var cfg = STAGE_SCRIPTS[key];
      if (!cfg) return;

      var pillsContainer = stageEl.querySelector(".z-stage__pills");
      var eyebrowEl = stageEl.querySelector(".z-stage__eyebrow");
      var captionEl = stageEl.querySelector(".z-stage__caption");
      var beats = cfg.beats;
      var cur = REDUCED_MOTION ? beats.length - 1 : 0;
      var timer = null;

      if (pillsContainer) {
        pillsContainer.innerHTML = beats
          .map(function (b, idx) {
            return (
              '<span class="z-stage__pill" data-beat-idx="' +
              idx +
              '" style="pointer-events:auto;cursor:pointer"></span>'
            );
          })
          .join("");
      }

      var pills = stageEl.querySelectorAll(".z-stage__pill");

      function renderBeat(idx) {
        cur = idx;
        var beat = beats[idx];
        if (eyebrowEl) eyebrowEl.textContent = beat.label;
        if (captionEl) captionEl.textContent = beat.text;

        pills.forEach(function (p, pi) {
          var isAct = pi === idx;
          p.classList.toggle("is-active", isAct);
          p.style.backgroundColor = isAct
            ? cfg.accent
            : pi < idx
            ? cfg.accent + "66"
            : "rgba(255,255,255,0.16)";
        });

        stageEl.querySelectorAll("[data-node-id]").forEach(function (node) {
          var nid = node.getAttribute("data-node-id");
          var active = beat.activeNodes.indexOf(nid) !== -1;
          node.style.borderColor = active ? cfg.accent : "rgba(255,255,255,0.14)";
          node.style.boxShadow = active ? "0 0 0 4px " + cfg.accent + "26" : "none";
          node.style.opacity = active ? "1" : "0.52";
        });
      }

      pills.forEach(function (p) {
        p.addEventListener("click", function (e) {
          e.stopPropagation();
          var bi = parseInt(p.getAttribute("data-beat-idx"), 10) || 0;
          if (timer) clearInterval(timer);
          renderBeat(bi);
        });
      });

      renderBeat(cur);
      if (!REDUCED_MOTION) {
        timer = setInterval(function () {
          renderBeat((cur + 1) % beats.length);
        }, 2900);
      }
    });
  }

  /* ── 8. Context-Aware Verifier & Post-Upload Tamper Lab ─────────────── */
  function initVerifierAndTamperLab() {
    var loadDemoBtn = document.getElementById("loadSampleValidBtn");
    var tamperLab = document.getElementById("tamperLabBar");
    var tamperFileName = document.getElementById("tamperFileName");
    var tamperStatus = document.getElementById("tamperLabStatus");
    var flipByteBtn = document.getElementById("tamperLoadedFileBtn");
    var restoreBtn = document.getElementById("restoreLoadedFileBtn");
    var fileInput = document.getElementById("fileInput");
    var dropZone = document.getElementById("dropZoneEl");

    // Store the user's currently uploaded/loaded .epi bytes so Tamper Lab only acts on an active file!
    var activeOriginalBytes = null;
    var activeOriginalName = "";

    function activateTamperLab(u8, name, isTampered, flippedInfo) {
      if (!tamperLab) return;
      tamperLab.classList.add("is-active");
      if (tamperFileName) {
        tamperFileName.textContent =
          name + " (" + u8.byteLength.toLocaleString() + " bytes)";
      }
      if (tamperStatus) {
        if (isTampered && flippedInfo) {
          tamperStatus.style.display = "block";
          tamperStatus.style.color = "#fda4af";
          tamperStatus.textContent =
            "TAMPER SIMULATION ACTIVE: Flipped 1 byte at offset " +
            flippedInfo.offsetHex +
            " (" +
            flippedInfo.beforeHex +
            " → " +
            flippedInfo.afterHex +
            ") in " +
            activeOriginalName +
            ". Notice how the verifier above immediately rejected the modified file.";
        } else {
          tamperStatus.style.display = "none";
          tamperStatus.textContent = "";
        }
      }
      if (restoreBtn) {
        restoreBtn.style.display = isTampered ? "inline-flex" : "none";
      }
    }

    // Capture any file the user uploads via file picker or drag-and-drop
    function captureUserFile(file) {
      if (!file) return;
      file
        .arrayBuffer()
        .then(function (buf) {
          activeOriginalBytes = new Uint8Array(buf.slice(0));
          activeOriginalName = file.name || "uploaded.epi";
          activateTamperLab(activeOriginalBytes, activeOriginalName, false, null);
        })
        .catch(function () {});
    }

    if (fileInput) {
      fileInput.addEventListener("change", function () {
        if (fileInput.files && fileInput.files[0]) {
          captureUserFile(fileInput.files[0]);
        }
      });
    }

    if (dropZone) {
      dropZone.addEventListener("drop", function (e) {
        if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]) {
          captureUserFile(e.dataTransfer.files[0]);
        }
      });
    }

    // Helper button: Load demo sample.epi
    if (loadDemoBtn) {
      loadDemoBtn.addEventListener("click", async function (e) {
        e.preventDefault();
        e.stopPropagation();
        if (typeof window.epiVerifyDroppedFile !== "function") return;
        try {
          var res = await fetch("/assets/sample.epi");
          if (!res.ok) throw new Error("HTTP " + res.status);
          var buf = await res.arrayBuffer();
          activeOriginalBytes = new Uint8Array(buf.slice(0));
          activeOriginalName = "sample.epi";
          var file = new File([activeOriginalBytes], activeOriginalName, {
            type: "application/vnd.epi+zip"
          });
          window.epiVerifyDroppedFile(file);
          activateTamperLab(activeOriginalBytes, activeOriginalName, false, null);
        } catch (err) {
          console.error("Sample load failed:", err);
        }
      });
    }

    // Flip 1 byte in the currently loaded file
    if (flipByteBtn) {
      flipByteBtn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        if (!activeOriginalBytes || typeof window.epiVerifyDroppedFile !== "function") {
          return;
        }
        var copy = new Uint8Array(activeOriginalBytes.length);
        copy.set(activeOriginalBytes);
        var pos = Math.min(200, Math.max(0, copy.length - 64));
        var before = copy[pos];
        var after = before ^ 0xff;
        copy[pos] = after;
        var tamperedName = activeOriginalName.replace(/\.epi$/i, "") + "-tampered.epi";
        var tamperedFile = new File([copy], tamperedName, {
          type: "application/vnd.epi+zip"
        });
        window.epiVerifyDroppedFile(tamperedFile);
        activateTamperLab(copy, tamperedName, true, {
          offsetHex: "0x" + pos.toString(16).toUpperCase().padStart(4, "0"),
          beforeHex: "0x" + before.toString(16).toUpperCase().padStart(2, "0"),
          afterHex: "0x" + after.toString(16).toUpperCase().padStart(2, "0")
        });
      });
    }

    // Restore original unmodified bytes of the user's loaded file
    if (restoreBtn) {
      restoreBtn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        if (!activeOriginalBytes || typeof window.epiVerifyDroppedFile !== "function") {
          return;
        }
        var origFile = new File([activeOriginalBytes], activeOriginalName, {
          type: "application/vnd.epi+zip"
        });
        window.epiVerifyDroppedFile(origFile);
        activateTamperLab(activeOriginalBytes, activeOriginalName, false, null);
      });
    }
  }

  /* ── 9. FAQ Accordion (Single-Open, ARIA-Compliant) ─────────────────── */
  function initFaqAccordion() {
    var buttons = document.querySelectorAll(".z-faq-btn");
    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var expanded = btn.getAttribute("aria-expanded") === "true";
        var panelId = btn.getAttribute("aria-controls");
        var panel = panelId ? document.getElementById(panelId) : null;

        buttons.forEach(function (other) {
          other.setAttribute("aria-expanded", "false");
          var pid = other.getAttribute("aria-controls");
          var p = pid ? document.getElementById(pid) : null;
          if (p) p.classList.remove("is-open");
        });

        if (!expanded && panel) {
          btn.setAttribute("aria-expanded", "true");
          panel.classList.add("is-open");
        }
      });
    });
  }

  function boot() {
    initNavbar();
    initScrollReveal();
    initCopyButtons();
    initWalkthroughVideo();
    initHeroMonolith();
    initTelemetryStages();
    initVerifierAndTamperLab();
    initFaqAccordion();
  }

  if (document.readyState !== "loading") boot();
  else document.addEventListener("DOMContentLoaded", boot);
})();
