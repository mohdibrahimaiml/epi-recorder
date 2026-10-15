/* EPI Cloud demo trust page (static DEMO). No tracking on load.
   Data loads only after the human gate click. No events are sent anywhere. */
(function () {
  'use strict';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function hexOf(buf) {
    return Array.from(new Uint8Array(buf)).map(function (b) {
      return b.toString(16).padStart(2, '0');
    }).join('');
  }

  async function sha256Hex(blob) {
    var buf = await blob.arrayBuffer();
    var digest = await crypto.subtle.digest('SHA-256', buf);
    return hexOf(digest);
  }

  var gate = document.getElementById('gate');
  var gateBtn = document.getElementById('gateBtn');
  var content = document.getElementById('demoContent');
  var status = document.getElementById('gateStatus');
  var loaded = false;

  var burger = document.getElementById('burger');
  var menu = document.getElementById('mmenu');
  if (burger && menu) {
    burger.addEventListener('click', function () {
      var open = menu.classList.toggle('open');
      burger.classList.toggle('x', open);
      burger.setAttribute('aria-expanded', open ? 'true' : 'false');
      document.body.style.overflow = open ? 'hidden' : '';
    });
  }

  function fileRow(f) {
    var div = document.createElement('div');
    div.className = 'tier';
    div.innerHTML =
      '<h3>' + esc(f.label) + ' <span class="flag" style="position:static">DEMO file</span></h3>' +
      '<div class="tdesc">' + esc(f.goal) + '</div>' +
      '<div style="font-family:var(--mono);font-size:.72rem;color:var(--dim);margin:10px 0">' +
      'sha256 <code class="k">' + esc(f.claimed_sha256) + '</code><br>' +
      'workflow <code class="k">' + esc(f.workflow_id) + '</code> · ' + esc(f.size_bytes) + ' bytes' +
      '<br><span style="color:var(--warn)">' + esc(f.demo_note) + '</span></div>' +
      '<div style="display:flex;gap:10px;flex-wrap:wrap">' +
      '<a class="btn btn-sec" href="' + esc(f.path) + '" download>Download file</a>' +
      '<button type="button" class="btn btn-pri" data-verify="' + esc(f.path) + '">Verify in my browser</button>' +
      '</div>' +
      '<div class="vresult" role="status" aria-live="polite" style="margin-top:12px;font-size:.82rem"></div>'; // static-html
    return div;
  }

  async function verifyFile(path, claimed, box) {
    box.innerHTML = '<span style="color:var(--dim)">Fetching + hashing in this tab (file never uploaded)…</span>'; // static-html
    try {
      var res = await fetch(path, { credentials: 'same-origin' });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      var blob = await res.blob();
      var actual = await sha256Hex(blob);
      var hashOk = actual === (claimed || '').toLowerCase();
      var sealLine = '';
      try {
        if (window.verifyEPI) {
          var r = await window.verifyEPI(blob);
          if (!r.structure || !r.manifest) {
            sealLine = '<br><span style="color:var(--bad)">Seal check: FAIL — not a readable EPI container.</span>';
          } else if (!r.integrity || r.signature === false) {
            sealLine = '<br><span style="color:var(--bad)">Seal check: FAIL — ' + esc(r.message || 'integrity or signature failed') + '. Use epi verify for the full report.</span>';
          } else if (r.signature === true) {
            sealLine = '<br><span style="color:var(--warn)">Seal check: SEAL VALID · IDENTITY NOT PINNED — hashes and Ed25519 signature passed; this browser does not know the signer (amber is correct).</span>';
          } else {
            sealLine = '<br><span style="color:var(--warn)">Seal check: inconclusive in browser — run epi verify offline.</span>';
          }
        } else {
          sealLine = '<br><span style="color:var(--dim)">Browser verifier not loaded — hash check below is still exact.</span>';
        }
      } catch (e) {
        sealLine = '<br><span style="color:var(--warn)">Browser seal check error: ' + esc(e.message) + '</span>';
      }
      if (!hashOk) {
        box.innerHTML = '<span style="color:var(--bad)">FAIL — bytes do not match claimed_sha256.</span><br>' +
          '<span style="font-family:var(--mono);font-size:.72rem">claimed ' + esc(claimed) + '<br>actual&nbsp;&nbsp;' + esc(actual) + '</span>' + sealLine; // static-html
      } else {
        box.innerHTML = '<span style="color:var(--ok)">Hash matches claimed_sha256.</span>' +
          '<span style="font-family:var(--mono);font-size:.72rem"> (' + esc(actual.slice(0, 16)) + '…)</span>' + sealLine; // static-html
      }
    } catch (e) {
      box.innerHTML = '<span style="color:var(--bad)">Could not verify: ' + esc(e.message) + '</span>'; // static-html
    }
  }

  async function load() {
    if (loaded) return;
    loaded = true;
    if (status) status.textContent = 'Loading DEMO data…';
    var res = await fetch('demo-data.json', { credentials: 'same-origin' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    var data = await res.json();

    var agent = (data.agents && data.agents[0]) || {};
    var cp = data.checkpoint_DEMO || {};
    var key = (data.keys && data.keys[0]) || {};

    var stats = document.getElementById('demoStats');
    if (stats) {
      stats.innerHTML =
        '<div class="stat"><div class="sv"><span>' + esc(agent.runs_witnessed_30d_DEMO) + '</span></div><div class="sk">Runs witnessed · 30d · DEMO</div><div class="sd">Hash-only receipts. Illustration, not real runs.</div></div>' +
        '<div class="stat"><div class="sv"><span>' + esc(agent.runs_witnessed_90d_DEMO) + '</span></div><div class="sk">Runs witnessed · 90d · DEMO</div><div class="sd">Ordered, signed, anchored daily in the real product.</div></div>' +
        '<div class="stat"><div class="sv"><span>' + esc(agent.runs_in_evidence_room) + '</span></div><div class="sk">Files in Evidence Room</div><div class="sd">Real sealed .epi files from this repo.</div></div>' +
        '<div class="stat"><div class="sv"><span>' + esc(agent.different_version_DEMO) + '</span></div><div class="sk">different_version · DEMO</div><div class="sd">Shown red in the real product when a copy is not what was reported.</div></div>'; // static-html
    }

    var keyBox = document.getElementById('demoKeys');
    if (keyBox) {
      keyBox.innerHTML =
        '<div class="tier"><h3>Sealing key (DEMO history)</h3>' +
        '<div style="font-family:var(--mono);font-size:.74rem;overflow-wrap:anywhere">public_key <code class="k">' + esc(key.public_key) + '</code><br>' +
        'fingerprint <code class="k">' + esc(key.fingerprint) + '</code> · since ' + esc(key.valid_from) + ' · ' + esc(key.status) + '</div>' +
        '<p style="font-size:.82rem;color:var(--mut)">Registration is informational only — never a pin. Claim-ready identity requires pinning out of band (<code class="k">epi keys trust --fingerprint …</code>).</p></div>'; // static-html
    }

    var cpBox = document.getElementById('demoCheckpoint');
    if (cpBox) {
      cpBox.innerHTML =
        '<div class="tier"><h3>Daily checkpoint (DEMO layout)</h3>' +
        '<div style="font-family:var(--mono);font-size:.74rem">day <code class="k">' + esc(cp.day) + '</code> · count ' + esc(cp.count) + '<br>' +
        'head <code class="k">' + esc(cp.head_hash) + '</code></div>' +
        '<p style="font-size:.82rem;color:var(--mut)">' + esc(cp.note) + '</p></div>'; // static-html
    }

    var filesBox = document.getElementById('demoFiles');
    if (filesBox) {
      filesBox.innerHTML = ''; // static-html
      (data.files || []).forEach(function (f) { filesBox.appendChild(fileRow(f)); });
      filesBox.querySelectorAll('[data-verify]').forEach(function (btn) {
        btn.addEventListener('click', function () {
          var path = btn.getAttribute('data-verify');
          var match = (data.files || []).filter(function (x) { return x.path === path; })[0] || {};
          var box = btn.closest('.tier').querySelector('.vresult');
          verifyFile(path, match.claimed_sha256, box);
        });
      });
    }

    if (gate) gate.style.display = 'none';
    if (content) content.style.display = '';
    if (status) status.textContent = '';
  }

  if (gateBtn) {
    gateBtn.addEventListener('click', function () {
      load().catch(function (e) {
        loaded = false;
        if (status) status.textContent = 'DEMO data failed to load: ' + e.message;
      });
    });
  }
})();
