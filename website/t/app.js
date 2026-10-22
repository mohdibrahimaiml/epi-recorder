/* EPI Cloud trust page (real data). Bot-proof by design:
   - Token lives in the URL fragment (#k=): never sent to servers or proxies.
     It is stripped from the address bar on load and sent only as a header.
     A copy is kept in sessionStorage (this tab only, keyed by slug) so a
     refresh still works; it is never written to a URL, cookie or log.
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
    // The ?api= override exists for local Playwright tests only.
    //
    // It must NEVER be honoured on a public deployment: every request this
    // page makes carries the reviewer share token in the X-EPI-Share-Token
    // header, so an attacker-supplied ?api=https://evil.example would
    // forward the victim's reviewer credential to the attacker (and let the
    // attacker serve arbitrary content back as the trust page).
    //
    // The site's Content-Security-Policy is Report-Only, so nothing else
    // would stop it (red-team W-01).
    if (!override) return '';
    var host = (window.location.hostname || '').toLowerCase();
    var isLocal = host === 'localhost' || host === '127.0.0.1' || host === '::1' ||
                  host === '0.0.0.0' || /\.localhost$/.test(host);
    if (!isLocal) return '';
    return String(override).replace(/\/$/, '');
  }

  var SLUG = slug();
  var TOKEN_STORE = 'epi-trust-k:' + SLUG;

  function storedToken() {
    try { return (SLUG && window.sessionStorage.getItem(TOKEN_STORE)) || ''; } catch (e) { return ''; }
  }
  function storeToken(v) {
    try { if (SLUG) window.sessionStorage.setItem(TOKEN_STORE, v); } catch (e) { /* storage blocked: refresh will need the link again */ }
  }
  function forgetToken() {
    try { if (SLUG) window.sessionStorage.removeItem(TOKEN_STORE); } catch (e) { /* ignore */ }
  }

  var TOKEN = token();
  if (TOKEN) storeToken(TOKEN); else TOKEN = storedToken();
  var API = apiBase();
  var loaded = false;

  // Strip the fragment immediately so the token never lingers in the URL
  // (address bar, bookmarks, screenshots). The sessionStorage copy above
  // keeps a refresh of this tab working.
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

  /* Display helpers shared by the summary, cards, pack and drop zone. */
  function normFp(fp) {
    return String(fp || '').replace(/[^0-9a-f]/gi, '').toLowerCase().slice(0, 16);
  }
  function groupFp(fp) {
    var n = normFp(fp);
    return n.replace(/(.{4})(?=.)/g, '$1 ');
  }
  // "2026-10-19 15:55 UTC": unambiguous for a reviewer in any time zone.
  function fmtWhen(iso) {
    var s = String(iso || '');
    var m = s.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/);
    return m ? m[1] + ' ' + m[2] + ' UTC' : s;
  }
  function shortId(f) {
    return String(f.claimed_sha256 || f.id || '').slice(0, 8);
  }
  function fileTitle(f) {
    return f.goal || ('Sealed run ' + String(f.claimed_sha256 || '').slice(0, 8));
  }
  function plural(n, one, many) {
    return n + ' ' + (n === 1 ? one : many);
  }

  // Facts about the shared set, computed once per render. Everything here
  // restates fields of the trust record; nothing is inferred beyond them.
  function analyse(doc) {
    var arts = doc.artifacts || [];
    var counts = {};
    arts.forEach(function (f) {
      var k = normFp(f.key_fingerprint);
      if (k) counts[k] = (counts[k] || 0) + 1;
    });
    var main = '';
    Object.keys(counts).forEach(function (k) { if (!main || counts[k] > counts[main]) main = k; });
    var registered = {};
    (doc.keys || []).forEach(function (k) {
      var n = normFp(k.fingerprint);
      if (n) registered[n] = k;
    });
    return {
      n: arts.length,
      witnessed: arts.filter(function (f) { return f.witness_status === 'witnessed'; }).length,
      changed: arts.filter(function (f) { return f.witness_status === 'different_version'; }).length,
      badSeal: arts.filter(function (f) { return f.signature_check === 'invalid'; }).length,
      keyCounts: counts,
      mainKey: main,
      distinctKeys: Object.keys(counts).length,
      registered: registered,
      hasRegistered: Object.keys(registered).length > 0,
    };
  }

  function renderSummary(doc, a) {
    var out = [];
    if (!a.n) {
      out.push('<p class="sum-line">No files have been shared on this link yet. The witness counts below cover the runs the vendor registered.</p>');
    } else {
      var notW = a.n - a.witnessed - a.changed;
      var line = a.witnessed === a.n
        ? (a.n === 1 ? 'The shared file was' : 'All ' + a.n + ' shared files were') + ' registered with EPI’s independent witness when ' + (a.n === 1 ? 'it was' : 'they were') + ' made, and the copies shared here match what was registered.'
        : a.witnessed + ' of ' + a.n + ' shared files were registered with EPI’s independent witness when they were made, and the copies shared here match what was registered.';
      out.push('<p class="sum-line"><span class="sum-dot ' + (a.witnessed === a.n ? 'ok' : 'warn') + '"></span>' + esc(line) + '</p>');
      if (notW > 0) {
        out.push('<p class="sum-line"><span class="sum-dot warn"></span>' + esc(plural(notW, 'file was', 'files were') + ' not registered with the witness — ask the vendor why.') + '</p>');
      }
      if (a.changed > 0) {
        out.push('<p class="sum-line"><span class="sum-dot bad"></span>' + esc(plural(a.changed, 'file differs', 'files differ') + ' from the version that was registered. Treat ' + (a.changed === 1 ? 'it' : 'them') + ' as changed and ask the vendor.') + '</p>');
      }
      if (a.badSeal > 0) {
        out.push('<p class="sum-line"><span class="sum-dot bad"></span>' + esc(plural(a.badSeal, 'file has', 'files have') + ' a broken seal. Don’t rely on ' + (a.badSeal === 1 ? 'it' : 'them') + '.') + '</p>');
      }
    }
    // Who signed: honest about what is and is not established.
    var keyLine;
    if (a.hasRegistered) {
      var regs = (doc.keys || []).filter(function (k) { return !k.revoked_at; }).map(function (k) { return groupFp(k.fingerprint); });
      keyLine = 'The vendor registered signing key ' + (regs.join(', ') || groupFp((doc.keys[0] || {}).fingerprint)) +
        ' with EPI. Registration alone does not prove who they are: confirm the fingerprint with the vendor directly (for example by phone) before relying on who signed.';
    } else {
      keyLine = 'The vendor has not registered a signing key with EPI. We can’t confirm who signed these files until you confirm the vendor’s key fingerprint with them directly (it is shown on each file below).';
    }
    if (a.distinctKeys > 1) keyLine += ' These files were signed with ' + a.distinctKeys + ' different keys.';
    // Amber: who signed is not established until the reviewer confirms the key.
    out.push('<p class="sum-line"><span class="sum-dot ' + (a.hasRegistered && a.distinctKeys <= 1 ? 'info' : 'warn') + '"></span>' + esc(keyLine) + '</p>');
    if (doc.expires_at) {
      out.push('<p class="sum-line sum-small">This link is valid until ' + esc(fmtWhen(doc.expires_at)) + '.</p>');
    }
    out.push('<p class="sum-line sum-small">Re-check any file in this browser with the Verify button on each file, or check everything offline with the evidence pack below.</p>');
    out.push('<details class="terms"><summary>What these terms mean</summary><dl>' +
      '<dt>Witnessed</dt><dd>When the run was recorded, its fingerprint (hash) was sent to EPI’s witness service, which logged it with the time it arrived. The vendor cannot change that log entry afterwards, so a later edit to the file would no longer match.</dd>' +
      '<dt>Checkpoint</dt><dd>Once a day (00:05 UTC) the witness signs a summary of its whole log, so entries cannot be quietly removed or reordered later.</dd>' +
      '<dt>Seal</dt><dd>The file’s built-in lock: every part of the record is hashed and the list of hashes is signed. Any change after sealing breaks it.</dd>' +
      '<dt>Signing key</dt><dd>The key the vendor’s software used to sign the seal. A valid signature shows the file was not changed; it shows <em>who</em> signed only once you have confirmed the key belongs to the vendor.</dd>' +
      '<dt>SHA-256 fingerprint</dt><dd>A short code computed from a file’s exact bytes. Change one byte and the code changes completely, so matching codes mean identical files. A key fingerprint (e.g. <code class="k">ff09 77d2 7a60 6699</code>) is the same idea for a key: read it to the vendor to confirm the key.</dd>' +
      '</dl></details>');
    return out.join('');
  }

  function verifyYourselfHtml(doc, a) {
    var folder = safeSlug(doc.vendor || 'vendor');
    return '<div class="term">' + esc('# 1. Pin the vendor’s signing key (once), after they confirm its fingerprint to you\n' +
      'epi keys trust ' + folder + '/FILE.epi --name ' + folder + ' --fingerprint "<fingerprint the vendor read to you>"\n' +
      '# 2. Verify each file against the witness lines in the pack\n' +
      PACK_OFFLINE_CMD) + '</div>' +
      '<p style="font-size:.86rem;color:var(--mut)">Download the evidence pack above, unzip it, and run these from the unzipped folder. ' +
      'Its <code class="k">README.txt</code> lists every file with the result to expect and where to get the EPI witness key for <code class="k">&lt;PASTE-KEY&gt;</code>. ' +
      'Without step 1 the file’s integrity, signature and witness receipt still check, but the decision reads FAIL (“identity unknown” or “not a key you trust”) until you pin the key — that is about who signed, not a sign the file changed.</p>';
  }

  function render(doc) {
    var a = analyse(doc);
    document.getElementById('vendorTitle').textContent = doc.vendor + ' — evidence';
    document.getElementById('gateVendor').textContent = doc.vendor + ' — ' + doc.link_label;
    try { document.title = doc.vendor + ' — evidence'; } catch (e) { /* ignore */ }
    var sum = document.getElementById('trustSummary');
    if (sum) sum.innerHTML = renderSummary(doc, a); // static-html: built from esc() only
    var vy = document.getElementById('verifyYourself');
    if (vy) vy.innerHTML = verifyYourselfHtml(doc, a); // static-html: built from esc() only

    var stats = '';
    if (a.n) {
      var notW = a.n - a.witnessed;
      stats += stat(a.witnessed + ' of ' + a.n, 'Shared files witnessed',
        notW ? plural(notW, 'file', 'files') + ' not witnessed.' : 'Every shared file is in the witness log.');
    }
    (doc.inboxes || []).forEach(function (b) {
      // Before the first signed daily checkpoint there are no per-date counts
      // yet: say so instead of showing a contradictory "0 in the last 30 days".
      var desc = b.awaiting_checkpoint
        ? 'Counts by date appear after the daily checkpoint (00:05 UTC).'
        : b.d30 + ' in the last 30 days · ' + b.d90 + ' in 90 days.';
      stats += stat(b.total_witnessed, 'Runs in witness log · ' + b.label,
        'Every run the vendor registered for ' + b.label + ', shared here or not. ' + desc);
    });
    if (!stats) stats = stat('0', 'Runs witnessed', 'No witness data in scope yet.');
    document.getElementById('trustStats').innerHTML = stats; // static-html: built from esc() only

    var keys = '';
    (doc.keys || []).forEach(function (k) {
      keys += '<div class="tier"><h3>Signing key</h3>' +
        '<div style="font-family:var(--mono);font-size:.74rem;overflow-wrap:anywhere">fingerprint <code class="k">' +
        esc(groupFp(k.fingerprint) || k.fingerprint) + '</code> · since ' + esc(fmtWhen(k.valid_from)) +
        (k.revoked_at ? ' · <span style="color:var(--bad)">revoked ' + esc(fmtWhen(k.revoked_at)) + '</span>' : ' · current') +
        (k.revoke_reason ? '<br>revocation reason: ' + esc(k.revoke_reason) : '') + '</div></div>';
    });
    if (!keys) {
      keys = '<div class="tier"><div class="tdesc">The vendor has not registered a signing key with EPI. Registration would be informational only anyway: to know who signed, confirm the key fingerprint shown on each file with the vendor directly.</div></div>';
    }
    document.getElementById('trustKeys').innerHTML = keys; // static-html: built from esc() only

    function witLine(f) {
      var st = f.witness_status;
      if (st === 'witnessed') {
        return '<div style="color:var(--ok)">Witnessed ✓ — this exact file is in the witness log.</div>';
      }
      if (st === 'no_inbox') {
        return '<div style="color:var(--warn)">Not witnessed — the vendor has no witness inbox for this yet, so EPI can’t independently confirm when it was made. Ask the vendor why.</div>';
      }
      // different_version already shows the red "Needs review" line below;
      // a second warning saying the same thing only adds noise.
      if (st === 'different_version') {
        return '';
      }
      return '<div style="color:var(--warn)">Not witnessed — this file was not registered with the witness when it was created, so EPI can’t independently confirm when it was made. Ask the vendor why.</div>';
    }

    function keyLine(f) {
      var fp = normFp(f.key_fingerprint);
      if (!fp) {
        return f.signature_check === 'unsigned'
          ? '<div style="color:var(--warn);font-size:.82rem">Not signed — anyone could have produced this file.</div>'
          : '';
      }
      var bits = 'Signed by key <code class="k">' + esc(groupFp(fp)) + '</code>';
      if (a.distinctKeys > 1 && fp !== a.mainKey) {
        bits += ' <span style="color:var(--warn)">— a different key from the other files</span>';
      }
      if (a.hasRegistered) {
        var reg = a.registered[fp];
        bits += reg
          ? (reg.revoked_at ? ' <span style="color:var(--bad)">— a key the vendor revoked</span>' : ' — matches a key the vendor registered')
          : ' <span style="color:var(--warn)">— not one of the vendor’s registered keys</span>';
      }
      return '<div style="font-size:.82rem;color:var(--mut);overflow-wrap:anywhere">' + bits + '</div>';
    }

    var files = '';
    (doc.artifacts || []).forEach(function (f, idx) {
      var bad = f.signature_check === 'invalid' || f.witness_status === 'different_version';
      var fileUrl = f && (f.content_url || f.download_url);
      var meta = [];
      if (f.sealed_at) meta.push('Sealed ' + fmtWhen(f.sealed_at));
      if (shortId(f)) meta.push('id ' + shortId(f));
      files += '<div class="tier"><h3>' + esc(fileTitle(f)) + '</h3>' +
        (meta.length ? '<div style="font-size:.8rem;color:var(--mut)">' + esc(meta.join(' · ')) + '</div>' : '') +
        '<div style="font-family:var(--mono);font-size:.72rem;color:var(--dim);overflow-wrap:anywhere;word-break:break-all">sha256 <code class="k" style="overflow-wrap:anywhere;word-break:break-all;white-space:normal">' + esc(f.claimed_sha256) + '</code></div>' +
        keyLine(f) +
        witLine(f) +
        (bad ? '<div style="color:var(--bad)">Needs review: ' + esc(f.signature_check) + ' / ' + esc(f.witness_status) + '</div>' : '') +
        (fileUrl ? '<div style="margin-top:10px"><button type="button" class="btn btn-sec" data-artifact="' + idx + '">Verify these bytes</button> <a href="#" data-dlartifact="' + idx + '" style="font-size:.8rem;color:var(--mut)">Download file</a></div>' +
          '<div class="vresult" role="status" aria-live="polite" style="margin-top:10px;font-size:.82rem"></div>' : '') +
        '</div>';
    });
    if (files) {
      files = '<p style="font-size:.84rem;color:var(--mut)">The Verify button on each file confirms that the file you get from this page matches the shared record exactly and re-checks its seal in this browser. Independent proof comes from the witness receipt and the offline check in the evidence pack.</p>' + files;
    }
    if (!files) {
      files = '<div class="tier"><h3>Evidence Room</h3><div class="tdesc">No selected files shared yet. Witness counts above cover every run; files the vendor selects for review appear here.</div></div>';
    } else if (a.n >= 200) {
      files = '<p style="font-size:.86rem;color:var(--warn)">Showing the ' + a.n + ' most recently shared files. Older files on this link are not listed here.</p>' + files;
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
        var name = packFileName(f, idx, {});  // goal-slug + seal date + short sha
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
    // Otherwise: goal-slug + seal date/time + short sha, so many runs with the
    // same goal still get distinct, recognisable names.
    var when = String(f.sealed_at || '').match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
    var base = fromUrl || (
      safeSlug(f.goal || f.workflow_id || ('file-' + (idx + 1))).slice(0, 48).replace(/-+$/, '') +
      (when ? '-' + when[1] + when[2] + when[3] + '-' + when[4] + when[5] : '') +
      (f.claimed_sha256 ? '-' + String(f.claimed_sha256).slice(0, 8) : '') + '.epi');
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
  var PACK_HONESTY_NOTE = 'Each witness line carries an Ed25519 receipt from the EPI witness \u2014 checkable offline ONLY against a witness public key you pinned yourself (step 2). Full-log consistency is additionally covered by the signed daily checkpoint; per-line Merkle inclusion proofs are planned, not present.';
  var PACK_KEY_NOTE = 'NEVER trust the witness_pubkey printed inside witness.json: it arrives in the same file as the stamps, so a forger swaps in their own (a passport printing its own stamp sample). Get the EPI witness key from TWO places and check they match: (1) https://cloud.epilabs.org/.well-known/epi-witness-key.json  (2) the public epi-witness-checkpoints GitHub repo. Paste it as --witness-pubkey in step 3 (or set EPI_WITNESS_PUBKEY). Without it the verifier answers STAMP NOT CONFIRMED, never WITNESSED. If the result does not say "verified witness receipt", the pack proves nothing about the witness.';

  function buildPackReadme(doc, witness, folder, files) {
    var out = [];
    var vendorSlug = safeSlug(doc.vendor || 'vendor');
    // Distinct signing keys, most-used first, each with one file to pin from.
    var keyList = [];
    var byKey = {};
    files.forEach(function (x) {
      var fp = normFp(x.art && x.art.key_fingerprint);
      if (!fp) return;
      if (!byKey[fp]) { byKey[fp] = { fp: fp, count: 0, file: folder + '/' + x.name }; keyList.push(byKey[fp]); }
      byKey[fp].count += 1;
    });
    keyList.sort(function (p, q) { return q.count - p.count; });
    keyList.forEach(function (k, i) { k.pinName = i === 0 ? vendorSlug : vendorSlug + '-key' + (i + 1); });

    out.push('EPI evidence pack — offline verification');
    out.push('========================================');
    out.push('Vendor: ' + (doc.vendor || 'unknown') + ' — ' + (doc.link_label || ''));
    out.push('');
    out.push('Every file below was SHA-256 hash-checked against the shared');
    out.push('record before zipping. Re-check everything yourself, offline,');
    out.push('from the folder this README is in (install: pip install epi-recorder).');
    out.push('');
    out.push('STEP 1 — Confirm and pin the vendor’s signing key (once)');
    out.push('---------------------------------------------------------');
    if (keyList.length) {
      out.push('Signing key fingerprint(s) used by the files in this pack:');
      keyList.forEach(function (k) {
        out.push('  ' + groupFp(k.fp) + '   (' + plural(k.count, 'file', 'files') + ')');
      });
      out.push('');
      out.push('Ask the vendor — by phone or another channel you already trust, NOT');
      out.push('this pack or the message it came with — to read you their signing key');
      out.push('fingerprint. Only if it matches, pin it:');
      out.push('');
      keyList.forEach(function (k) {
        out.push('  epi keys trust ' + k.file + ' --name ' + k.pinName + ' --fingerprint "<the fingerprint the vendor read to you>"');
      });
      out.push('');
      out.push('epi refuses to pin unless the fingerprint you type matches the key in');
      out.push('that file. Pin a key only if the vendor confirmed that exact fingerprint.');
    } else {
      out.push('No file in this pack carries a signing key fingerprint, so there is no');
      out.push('key to pin: the strict check below cannot establish who made them.');
    }
    out.push('');
    out.push('STEP 2 — Get the EPI witness key (<PASTE-KEY> below)');
    out.push('-------------------------------------------------');
    out.push(PACK_KEY_NOTE);
    out.push('');
    out.push('STEP 3 — Verify each file');
    out.push('------------------------');
    out.push('  ' + PACK_OFFLINE_CMD);
    out.push('');
    out.push('  (replace FILE with one of the .epi files in ' + folder + '/,');
    out.push('   and <PASTE-KEY> with the EPI witness key from step 2.)');
    out.push('');
    out.push('What passes even before step 1: the seal ("Integrity: Verified",');
    out.push('"Signature: Valid") and, with the witness key from step 2, the witness');
    out.push('receipt ("Witness: WITNESSED — verified witness receipt"). Until you pin');
    out.push('the vendor’s key the DECISION reads FAIL ("Identity unknown" or "Not a');
    out.push('key you trust"): that means EPI cannot tell you who signed, not that the');
    out.push('file changed.');
    out.push('');
    out.push(PACK_HONESTY_NOTE);
    out.push('');
    out.push('Files and the result to expect after steps 1-3:');
    files.forEach(function (x) {
      var f = x.art || {};
      var fp = normFp(f.key_fingerprint);
      var k = fp ? byKey[fp] : null;
      var expect;
      if (f.signature_check === 'invalid') {
        expect = 'FAIL — the seal is broken. Do not rely on this file.';
      } else if (!fp) {
        expect = 'FAIL — the file is not signed, so no signer can be confirmed.';
      } else if (f.witness_status === 'different_version') {
        expect = 'FAIL — witness MISMATCH: the witness log holds a different version of this run. Ask the vendor.';
      } else if (f.witness_status !== 'witnessed') {
        expect = 'FAIL — "never reported to your witness log". This file was not registered with the witness when it was made; ask the vendor why.';
      } else {
        expect = 'PASS (decision PASS, Witness: WITNESSED — verified witness receipt)' +
          (k && keyList.length > 1 ? ', once key ' + groupFp(fp) + ' is pinned as ' + k.pinName : '') + '.';
      }
      out.push('  ' + folder + '/' + x.name);
      out.push('    sha256 ' + x.sha);
      if (x.goal || f.sealed_at) out.push('    ' + [x.goal, f.sealed_at ? 'sealed ' + fmtWhen(f.sealed_at) : ''].filter(Boolean).join(' — '));
      if (fp) out.push('    signed by key ' + groupFp(fp));
      out.push('    expect: ' + expect);
    });
    out.push('');
    out.push('Trust record: trust.json (vendor, witness counts, key history with fingerprints).');
    out.push('Witness lines: witness.json (per-line Ed25519 receipts; its printed');
    out.push('witness_pubkey is a hint for display ONLY — never trust it, get the key');
    out.push('from the two places in step 2).');
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
        files.push({ name: packFileName(f, i, used), buf: buf, sha: actual, goal: f.goal || f.workflow_id || '', art: f });
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
    var btn = document.getElementById('gateBtn');
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
      if (res.status === 404) {
        // Final for this link: retrying cannot help, so don't offer it.
        forgetToken();
        if (btn) btn.disabled = true;
        status.textContent = 'This link is invalid, expired, or revoked. Ask the vendor for a fresh trust link.';
      } else {
        status.textContent = 'Evidence failed to load (HTTP ' + res.status + '). Retry in a moment.';
      }
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

  // Which shared file (if any) has exactly these bytes.
  function sharedMatch(sha) {
    var arts = (currentDoc && currentDoc.artifacts) || [];
    for (var i = 0; i < arts.length; i++) {
      if (String(arts[i].claimed_sha256 || '').toLowerCase() === sha) return arts[i];
    }
    return null;
  }

  // claimed: the shared record's sha256 ("Verify these bytes"), or null for
  // a dropped file, which is then matched against every shared file.
  async function verifyBlob(blob, box, claimed) {
    box.style.display = '';
    box.innerHTML = '<span style="color:var(--dim)">Checking the seal in this tab (file never uploaded)…</span>';
    try {
      var buf = await blob.arrayBuffer();
      var actual = hexOf(await crypto.subtle.digest('SHA-256', buf));
      var mismatch = !!claimed && actual !== String(claimed).toLowerCase();
      var sealLine = '';
      var sealFail = false;
      try {
        if (window.verifyEPI) {
          // Flat shape from epi-verify-core.js: {structure, manifest,
          // integrity, hashChain, signature(true/false/null), viewer, trust_level}.
          var r = await window.verifyEPI(blob);
          if (!r.structure || !r.manifest) {
            sealFail = true;
            sealLine = '<br><span style="color:var(--bad)">Seal check: FAIL — not a readable EPI container.</span>';
          } else if (!r.integrity || r.signature === false) {
            sealFail = true;
            sealLine = '<br><span style="color:var(--bad)">Seal check: FAIL — ' + esc(r.message || 'integrity or signature failed') + '. Don’t rely on this file. Use epi verify for the full report.</span>';
          } else if (r.signature === true) {
            sealLine = '<br><span style="color:var(--warn)">Seal check: SEAL VALID · IDENTITY NOT PINNED — hashes and Ed25519 signature passed; this browser does not know the signer (amber is correct).</span>';
          } else {
            sealLine = '<br><span style="color:var(--warn)">Seal check: inconclusive in browser — run epi verify offline.</span>';
          }
        } else {
          sealLine = '<br><span style="color:var(--dim)">Browser verifier not loaded — the hash check is still exact.</span>';
        }
      } catch (e) {
        sealLine = '<br><span style="color:var(--warn)">Browser seal check error: ' + esc(e.message) + '</span>';
      }
      var hashTxt = '<span style="font-family:var(--mono);font-size:.72rem">(' + esc(actual.slice(0, 16)) + '…)</span>';
      // Green only when every check on this line passed.
      var okColor = sealFail ? 'var(--mut)' : 'var(--ok)';
      if (mismatch) {
        box.innerHTML = '<span style="color:var(--bad)">FAIL — these bytes do not match the shared record.</span>' + sealLine;
      } else if (claimed) {
        box.innerHTML = '<span style="color:' + okColor + '">Hash matches the shared record.</span> ' + hashTxt + sealLine;
      } else {
        var m = sharedMatch(actual);
        var which;
        if (m) {
          var wit = m.witness_status === 'witnessed'
            ? ' — witnessed ✓'
            : (m.witness_status === 'different_version' ? ' — witness log holds a different version' : ' — not witnessed');
          which = '<span style="color:' + (sealFail || m.witness_status !== 'witnessed' ? (sealFail ? 'var(--mut)' : 'var(--warn)') : 'var(--ok)') + '">' +
            'This is the shared file “' + esc(fileTitle(m)) + '”' +
            (m.sealed_at ? ' sealed ' + esc(fmtWhen(m.sealed_at)) : '') + ' (id ' + esc(shortId(m)) + ') above' + esc(wit) + '.</span> ' + hashTxt;
        } else {
          which = '<span style="color:var(--warn)">This file is not one of the files shared on this page.</span> ' + hashTxt;
        }
        box.innerHTML = which + sealLine;
      }
      sendEvent('verified_file', mismatch ? 'mismatch' : (sealFail ? 'seal_fail' : 'checked'));
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
  if (!SLUG) {
    document.getElementById('gateStatus').textContent = 'This trust link is incomplete (missing evidence reference). Ask the vendor for a fresh trust link.';
    if (gateBtn) gateBtn.disabled = true;
  } else if (!TOKEN) {
    document.getElementById('gateStatus').textContent = 'This page was reloaded or the address was copied without its key — open the original link again (the key part after # is never sent to any server).';
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
