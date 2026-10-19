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
        (k.revoked_at ? ' · <span style="color:var(--bad)">revoked ' + esc(k.revoked_at) + '</span>' : ' · current') +
        (k.revoke_reason ? '<br>revocation reason: ' + esc(k.revoke_reason) : '') + '</div></div>';
    });
    if (!keys) {
      keys = '<div class="tier"><h3>Key history</h3><div class="tdesc">No keys registered yet. Registration is informational only — never a pin. Claim-ready identity requires pinning out of band.</div></div>';
    }
    document.getElementById('trustKeys').innerHTML = keys; // static-html: built from esc() only

    function witLine(f) {
    var st = f.witness_status;
    if (st === 'witnessed') {
      return '<div style="color:var(--ok)">Witnessed \u2713 \u2014 this exact file is in the witness log.</div>';
    }
    if (st === 'no_inbox') {
      return '<div style="color:var(--warn)">Not witnessed \u2014 the vendor has no witness inbox for this yet.</div>';
    }
    // different_version already shows the red "Needs review" line below;
    // a second warning saying the same thing only adds noise.
    if (st === 'different_version') {
      return '';
    }
    return '<div style="color:var(--warn)">Not witnessed \u2014 no witness stamp arrived for this file yet. Ask the vendor to witness it and re-share.</div>';
  }

  var files = '';
    (doc.artifacts || []).forEach(function (f, idx) {
      var bad = f.signature_check === 'invalid' || f.witness_status === 'different_version';
      var fileUrl = f && (f.content_url || f.download_url);
      files += '<div class="tier"><h3>' + esc(f.goal || ('Sealed run ' + String(f.claimed_sha256 || '').slice(0, 8))) + '</h3>' +
        '<div style="font-family:var(--mono);font-size:.72rem;color:var(--dim)">sha256 <code class="k">' + esc(f.claimed_sha256) + '</code></div>' +
        witLine(f) +
        (bad ? '<div style="color:var(--bad)">Needs review: ' + esc(f.signature_check) + ' / ' + esc(f.witness_status) + '</div>' : '') +
        (fileUrl ? '<div style="margin-top:10px"><button type="button" class="btn btn-sec" data-artifact="' + idx + '">Verify these bytes</button> <a href="#" data-dlartifact="' + idx + '" style="font-size:.8rem;color:var(--mut)">Download file</a></div><div class="vresult" role="status" aria-live="polite" style="margin-top:10px;font-size:.82rem"></div>' : '') +
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
        fetchBytes(url).then(function (buf) {
          verifyBlob(new Blob([buf], { type: 'application/octet-stream' }), box, f.claimed_sha256);
        }).catch(function (e) {
          box.innerHTML = '<span style="color:var(--bad)">Could not fetch: ' + esc(e.message) + '</span>';
        });
      });
    });
    document.querySelectorAll('[data-dlartifact]').forEach(function (a) {
      a.addEventListener('click', function (ev) {
        ev.preventDefault();
        var idx = Number(a.getAttribute('data-dlartifact'));
        var f = (currentDoc.artifacts || [])[idx];
        var url = f && (f.content_url || f.download_url);
        if (!f || !url) return;
        var name = packFileName(f, idx, {});
        if (/^data:/i.test(url)) {
          var d = document.createElement('a');
          d.href = url;
          d.download = name;
          document.body.appendChild(d);
          d.click();
          d.remove();
          return;
        }
        fetchBytes(url).then(function (buf) {
          triggerBlobDownload(new Blob([buf], { type: 'application/octet-stream' }), name);
        }).catch(function () { /* fetch errors surface on the Verify button */ });
      });
    });
  }

  /* Whole-link evidence pack (M6). Human click only: nothing here runs on
     page load or on the gate click. Every file is SHA-256 hash-checked
     against the shared record BEFORE zipping; any mismatch aborts the
     whole pack (no partial download, no events). */
  function safeSlug(s) {
    return String(s == null ? '' : s).toLowerCase()
      .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'evidence';
  }

  function needsAuth(url) {
    return /^https?:/i.test(url) || url.charAt(0) === '/';
  }

  function fetchBytes(url) {
    var opts = { credentials: 'same-origin' };
    if (needsAuth(url)) opts.headers = { 'X-EPI-Share-Token': TOKEN };
    return fetch(url, opts).then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.arrayBuffer();
    });
  }

  function packFileName(f, idx, used) {
    var fromUrl = '';
    try {
      var path = String(f.content_url || f.download_url || '').split('#')[0].split('?')[0];
      var last = path.split('/').pop() || '';
      if (/\.epi$/i.test(last)) fromUrl = last;
    } catch (e) { /* ignore */ }
    var base = fromUrl ||
      (safeSlug(f.goal || f.workflow_id || String(f.claimed_sha256 || '').slice(0, 12) || ('file-' + (idx + 1))) + '.epi');
    var name = base;
    var n = 1;
    while (used[name]) {
      n += 1;
      name = base.replace(/\.epi$/i, '') + '-' + n + '.epi';
    }
    used[name] = 1;
    return name;
  }

  function triggerBlobDownload(blob, name) {
    var objUrl = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = objUrl;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(objUrl); a.remove(); }, 4000);
  }

  var PACK_OFFLINE_CMD = 'epi verify FILE --policy strict --witness-log witness.json --witness-pubkey <PASTE-KEY> --offline';
  var PACK_HONESTY_NOTE = 'Each witness line carries an Ed25519 receipt from the EPI witness \u2014 checkable offline ONLY against a witness public key you pinned yourself (see below). Full-log consistency is additionally covered by the signed daily checkpoint; per-line Merkle inclusion proofs are planned, not present.';
  var PACK_KEY_NOTE = 'NEVER trust the witness_pubkey printed inside witness.json: it arrives in the same file as the stamps, so a forger swaps in their own (a passport printing its own stamp sample). Get the EPI witness key from TWO places and check they match: (1) https://cloud.epilabs.org/.well-known/epi-witness-key.json  (2) the public epi-witness-checkpoints GitHub repo. Paste it as --witness-pubkey above (or EPI_WITNESS_PUBKEY). Without it the verifier answers STAMP NOT CONFIRMED, never WITNESSED. If the result does not say "verified witness receipt", the pack proves nothing about the witness.';

  function buildPackReadme(doc, witness, folder, files) {
    var out = [];
    out.push('EPI evidence pack \u2014 offline verification');
    out.push('========================================');
    out.push('Vendor: ' + (doc.vendor || 'unknown') + ' \u2014 ' + (doc.link_label || ''));
    out.push('');
    out.push('Every file below was SHA-256 hash-checked against the shared');
    out.push('record before zipping. Re-check everything yourself, offline:');
    out.push('');
    out.push('  ' + PACK_OFFLINE_CMD);
    out.push('');
    out.push('  (replace FILE with one of the .epi files in ' + folder + '/,');
    out.push('   and <PASTE-KEY> with the EPI witness key — see below.)');
    out.push('');
    out.push(PACK_HONESTY_NOTE);
    out.push('');
    out.push(PACK_KEY_NOTE);
    out.push('');
    out.push('Files (sha256):');
    files.forEach(function (x) {
      out.push('  ' + folder + '/' + x.name + '  ' + x.sha + (x.goal ? '  (' + x.goal + ')' : ''));
    });
    out.push('');
    out.push('Trust record: trust.json (vendor, witness counts, key history with fingerprints).');
    out.push('Witness lines: witness.json (per-line Ed25519 receipts; its printed');
    out.push('witness_pubkey is a hint for display ONLY — never trust it, pin the key');
    out.push('from the two places above).');
    out.push('Manifest: MANIFEST.json (name + sha256 of every zipped file).');
    out.push('');
    return out.join('\n');
  }

  async function downloadPack() {
    var status = document.getElementById('packStatus');
    var btn = document.getElementById('packBtn');
    if (!currentDoc || !status || !btn) return;
    btn.disabled = true;
    status.style.color = 'var(--dim)';
    status.textContent = 'Building evidence pack\u2026';
    try {
      var wres = await api('/v1/trust/' + encodeURIComponent(SLUG) + '/witness-lines', {
        headers: { 'X-EPI-Share-Token': TOKEN },
      });
      if (!wres.ok) throw new Error('witness lines unavailable (HTTP ' + wres.status + '); pack aborted');
      var witness = await wres.json();
      var folder = safeSlug(currentDoc.vendor || 'vendor');
      var used = {};
      var files = [];
      var arts = currentDoc.artifacts || [];
      for (var i = 0; i < arts.length; i++) {
        var f = arts[i];
        var url = f && (f.content_url || f.download_url);
        if (!url) throw new Error('a shared file has no download available; pack aborted');
        status.textContent = 'Fetching file ' + (i + 1) + ' of ' + arts.length + '\u2026';
        var buf = await fetchBytes(url);
        var actual = hexOf(await crypto.subtle.digest('SHA-256', buf));
        var claimed = String(f.claimed_sha256 || '').toLowerCase();
        if (!claimed || actual !== claimed) {
          throw new Error('a shared file does not match its record (sha256 ' +
            (claimed || 'missing') + '); pack aborted \u2014 nothing was zipped');
        }
        files.push({ name: packFileName(f, i, used), buf: buf, sha: actual, goal: f.goal || f.workflow_id || '' });
      }
      if (typeof JSZip === 'undefined') throw new Error('zip engine did not load; retry in a moment');
      var zip = new JSZip();
      files.forEach(function (x) { zip.file(folder + '/' + x.name, x.buf); });
      zip.file('trust.json', JSON.stringify(currentDoc, null, 2) + '\n');
      zip.file('witness.json', JSON.stringify(witness, null, 2) + '\n');
      zip.file('README.txt', buildPackReadme(currentDoc, witness, folder, files));
      zip.file('MANIFEST.json', JSON.stringify(files.map(function (x) {
        return { name: folder + '/' + x.name, sha256: x.sha };
      }), null, 2) + '\n');
      status.textContent = 'Compressing\u2026';
      var blob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE', streamFiles: true });
      triggerBlobDownload(blob, folder + '-evidence-pack.zip');
      status.style.color = 'var(--ok)';
      status.textContent = 'Evidence pack downloaded (' + files.length + ' file(s), hashes verified).';
      sendEvent('downloaded_pack');
      sendEvent('downloaded_witness');
    } catch (e) {
      status.style.color = 'var(--bad)';
      status.textContent = 'Evidence pack failed: ' + (e && e.message ? e.message : e);
    } finally {
      btn.disabled = false;
    }
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
  var packBtn = document.getElementById('packBtn');
  if (packBtn) {
    packBtn.addEventListener('click', function () {
      downloadPack().catch(function (e) {
        var status = document.getElementById('packStatus');
        if (status) {
          status.style.color = 'var(--bad)';
          status.textContent = 'Evidence pack failed: ' + (e && e.message ? e.message : e);
        }
      });
    });
  }
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
