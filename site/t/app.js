/* EPI Cloud trust page (real data). Bot-proof by design:
   - Token lives in the URL fragment (#k=): never sent to servers or proxies.
     It is stripped from the address bar on load and sent only as a header.
   - Nothing is fetched until the human gate click. No events on page load.
   - Events (opened/verified_file/...) fire on human actions only.
   - ?api= override exists for local Playwright tests only (same-origin default).
*/
(function () {
  'use strict';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function params() {
    return new URLSearchParams(window.location.search || '');
  }

  function slug() {
    var m = (window.location.pathname || '').match(/^\/t\/([^/]+)\/?$/);
    if (m && m[1] !== 'app' && m[1] !== 'acme-demo' && m[1].slice(-5) !== '.html') return m[1];
    return params().get('s') || '';
  }

  function token() {
    var h = window.location.hash || '';
    var m = h.match(/(?:^#|[&?])k=([^&]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  function apiBase() {
    var override = params().get('api');
    if (override) return String(override).replace(/\/$/, '');
    return '';
  }

  var SLUG = slug();
  var TOKEN = token();
  var API = apiBase();
  var loaded = false;

  // Strip the fragment immediately so the token never lingers in the URL.
  try {
    if (window.location.hash) history.replaceState(null, '', window.location.pathname + window.location.search);
  } catch (e) { /* ignore */ }

  function api(path, opts) {
    return fetch(API + path, opts);
  }

  function sendEvent(kind, detail) {
    if (!loaded) return;
    api('/v1/trust/' + encodeURIComponent(SLUG) + '/events', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-EPI-Share-Token': TOKEN },
      body: JSON.stringify(detail ? { kind: kind, detail: detail } : { kind: kind }),
      keepalive: true,
    }).catch(function () { /* events are best-effort */ });
  }

  function stat(num, key, desc) {
    return '<div class="stat"><div class="sv"><span>' + esc(num) + '</span></div>' +
      '<div class="sk">' + esc(key) + '</div><div class="sd">' + esc(desc) + '</div></div>';
  }

  function render(doc) {
    document.getElementById('vendorTitle').textContent = doc.vendor + ' — evidence';
    document.getElementById('gateVendor').textContent = doc.vendor + ' — ' + doc.link_label;

    var stats = '';
    (doc.inboxes || []).forEach(function (b) {
      stats += stat(b.total_witnessed, 'Runs witnessed · ' + b.label, b.d30 + ' in the last 30 days · ' + b.d90 + ' in 90 days.');
    });
    if (!stats) stats = stat('0', 'Runs witnessed', 'No witness data in scope yet.');
    var awaiting = (doc.inboxes || []).some(function (b) { return b.awaiting_checkpoint; });
    if (awaiting) {
      stats += '<div class="tier" style="border-color:var(--warn)"><div class="tdesc">Some runs are logged but not checkpointed yet — counts appear after the first daily checkpoint (signed 00:05 UTC).</div></div>';
    }
    document.getElementById('trustStats').innerHTML = stats; // static-html: built from esc() only

    var keys = '';
    (doc.keys || []).forEach(function (k) {
      keys += '<div class="tier"><h3>Sealing key</h3>' +
        '<div style="font-family:var(--mono);font-size:.74rem;overflow-wrap:anywhere">fingerprint <code class="k">' +
        esc(k.fingerprint) + '</code> · since ' + esc(k.valid_from) +
        (k.revoked_at ? ' · <span style="color:var(--bad)">revoked ' + esc(k.revoked_at) + '</span>' : ' · current') + '</div></div>';
    });
    if (!keys) {
      keys = '<div class="tier"><h3>Key history</h3><div class="tdesc">No keys registered yet. Registration is informational only — never a pin. Claim-ready identity requires pinning out of band.</div></div>';
    }
    document.getElementById('trustKeys').innerHTML = keys; // static-html: built from esc() only

    var files = '';
    (doc.artifacts || []).forEach(function (f, idx) {
      var bad = f.signature_check === 'invalid' || f.witness_status === 'different_version';
      files += '<div class="tier"><h3>' + esc(f.goal || f.workflow_id || 'Sealed run') + '</h3>' +
        '<div style="font-family:var(--mono);font-size:.72rem;color:var(--dim)">sha256 <code class="k">' + esc(f.claimed_sha256) + '</code></div>' +
        (bad ? '<div style="color:var(--bad)">Needs review: ' + esc(f.signature_check) + ' / ' + esc(f.witness_status) + '</div>' : '') +
        (f.download_url ? '<div style="margin-top:10px"><button type="button" class="btn btn-sec" data-artifact="' + idx + '">Verify these bytes</button></div><div class="vresult" role="status" aria-live="polite" style="margin-top:10px;font-size:.82rem"></div>' : '') +
        '</div>';
    });
    if (!files) {
      files = '<div class="tier"><h3>Evidence Room</h3><div class="tdesc">No selected files shared yet. Witness counts above cover every run; files the vendor selects for review appear here.</div></div>';
    }
    document.getElementById('trustFiles').innerHTML = files; // static-html: built from esc() only

    document.getElementById('trustContent').style.display = '';
    document.getElementById('gate').style.display = 'none';
    wireArtifactButtons(doc);
  }

  var currentDoc = null;

  function wireArtifactButtons(doc) {
    currentDoc = doc;
    document.querySelectorAll('[data-artifact]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var f = (currentDoc.artifacts || [])[Number(btn.getAttribute('data-artifact'))];
        var url = f && (f.content_url || f.download_url);
        if (!f || !url) return;
        var box = btn.closest('.tier').querySelector('.vresult');
        box.style.display = '';
        box.innerHTML = '<span style="color:var(--dim)">Fetching shared bytes…</span>';
        fetch(url, { credentials: 'same-origin', headers: { 'X-EPI-Share-Token': TOKEN } }).then(function (res) {
          if (!res.ok) throw new Error('HTTP ' + res.status);
          return res.blob();
        }).then(function (blob) {
          verifyBlob(blob, box, f.claimed_sha256);
        }).catch(function (e) {
          box.innerHTML = '<span style="color:var(--bad)">Could not fetch: ' + esc(e.message) + '</span>';
        });
      });
    });
  }

  async function load() {
    if (loaded) return;
    loaded = true;
    var status = document.getElementById('gateStatus');
    status.textContent = 'Loading evidence…';
    var res;
    try {
      res = await api('/v1/trust/' + encodeURIComponent(SLUG), { headers: { 'X-EPI-Share-Token': TOKEN } });
    } catch (e) {
      loaded = false;
      status.textContent = 'Could not reach the evidence service. Check your connection and retry.';
      return;
    }
    if (!res.ok) {
      loaded = false;
      status.textContent = res.status === 404
        ? 'This link is invalid, expired, or revoked. Ask the vendor for a fresh trust link.'
        : 'Evidence failed to load (HTTP ' + res.status + '). Retry in a moment.';
      return;
    }
    status.textContent = '';
    render(await res.json());
    sendEvent('opened');
  }

  /* Verify-a-file drop zone (same browser engine as /verify/). */
  function hexOf(buf) {
    return Array.from(new Uint8Array(buf)).map(function (b) { return b.toString(16).padStart(2, '0'); }).join('');
  }

  async function verifyBlob(blob, box, claimed) {
    box.style.display = '';
    box.innerHTML = '<span style="color:var(--dim)">Checking the seal in this tab (file never uploaded)…</span>';
    try {
      var buf = await blob.arrayBuffer();
      var actual = hexOf(await crypto.subtle.digest('SHA-256', buf));
      var mismatch = claimed && actual !== String(claimed).toLowerCase();
      var sealLine = '';
      try {
        if (window.verifyEPI) {
          // Flat shape from epi-verify-core.js: {structure, manifest,
          // integrity, hashChain, signature(true/false/null), trust_level}.
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
      if (mismatch) {
        box.innerHTML = '<span style="color:var(--bad)">FAIL — these bytes do not match the shared record.</span>' + sealLine;
      } else if (!window.verifyEPI && !claimed) {
        box.innerHTML = '<span style="color:var(--dim)">Hash: ' + esc(actual.slice(0, 16)) + '… (verifier engine did not load)</span>';
      } else if (claimed) {
        box.innerHTML = '<span style="color:var(--ok)">Hash matches the shared record.</span> <span style="font-family:var(--mono);font-size:.72rem">(' + esc(actual.slice(0, 16)) + '…)</span>' + sealLine;
      } else {
        box.innerHTML = '<span style="color:var(--ok)">Hash: ' + esc(actual.slice(0, 16)) + '…</span>' + sealLine;
      }
      sendEvent('verified_file', mismatch ? 'mismatch' : 'checked');
    } catch (e) {
      box.innerHTML = '<span style="color:var(--bad)">Could not verify: ' + esc(e.message) + '</span>';
    }
  }

  function wireDrop() {
    var dz = document.getElementById('dropZoneEl');
    var fi = document.getElementById('fileInput');
    var dr = document.getElementById('dropResult');
    if (!dz || !fi || !dr) return;
    dz.addEventListener('click', function () { fi.click(); });
    dz.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fi.click(); } });
    fi.addEventListener('change', function () { if (fi.files && fi.files[0]) verifyBlob(fi.files[0], dr, null); });
    ['dragover', 'dragenter'].forEach(function (t) { dz.addEventListener(t, function (e) { e.preventDefault(); }); });
    dz.addEventListener('drop', function (e) {
      e.preventDefault();
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]) verifyBlob(e.dataTransfer.files[0], dr, null);
    });
  }

  var gateBtn = document.getElementById('gateBtn');
  if (!SLUG || !TOKEN) {
    document.getElementById('gateStatus').textContent = 'This trust link is incomplete (missing evidence reference). Ask the vendor for a fresh trust link.';
    if (gateBtn) gateBtn.disabled = true;
  } else if (gateBtn) {
    gateBtn.addEventListener('click', function () {
      load().catch(function (e) {
        loaded = false;
        document.getElementById('gateStatus').textContent = 'Failed to load: ' + e.message;
      });
    });
  }
  wireDrop();
})();
