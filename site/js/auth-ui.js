// EPI Auth UI — single account system: EPI Cloud only.
// Website "Sign In" points to https://cloud.epilabs.org. No Render calls.
// The old Render login (/api/auth/*) is retired; cloud uses HttpOnly
// session cookies on cloud.epilabs.org. The nav quietly asks the cloud
// whether this browser is signed in (same-site fetch, 2 s timeout) and
// says "Dashboard" instead of "Sign In" when it is — either way the
// button links to the cloud front door.
(function () {
  'use strict';

  var CLOUD_URL = 'https://cloud.epilabs.org';

  function cloudHref() {
    return CLOUD_URL + '/';
  }

  // Ask the cloud if this browser holds a session. Always resolves with a
  // label; any failure (offline, timeout, CORS, bad JSON) keeps "Sign In".
  function checkSession(done) {
    var settled = false;
    function finish(label) {
      if (settled) return;
      settled = true;
      done(label);
    }
    try {
      var ctl = ('AbortController' in window) ? new AbortController() : null;
      var timer = null;
      if (ctl) {
        timer = setTimeout(function () { try { ctl.abort(); } catch (e) {} }, 2000);
      }
      fetch(CLOUD_URL + '/auth/session', { credentials: 'include', cache: 'no-store', signal: ctl ? ctl.signal : undefined })
        .then(function (r) {
          if (timer) clearTimeout(timer);
          return r.json().catch(function () { return {}; });
        })
        .then(function (j) { finish(j && j.signed_in === true ? 'Dashboard' : 'Sign In'); })
        .catch(function () { if (timer) clearTimeout(timer); finish('Sign In'); });
    } catch (e) {
      finish('Sign In');
    }
    // Safety net for browsers without AbortController: never hang the nav.
    setTimeout(function () { finish('Sign In'); }, 2500);
  }

  function findNavContainer() {
    return document.getElementById('nav-auth-slot') ||
           document.getElementById('navLinks') ||
           document.querySelector('.nlinks') ||
           document.querySelector('.nav-links') ||
           document.querySelector('nav ul');
  }

  function injectNav(label) {
    label = label || 'Sign In';
    var href = cloudHref();
    var slot = document.getElementById('nav-auth-slot');
    if (!slot) {
      var nav = findNavContainer();
      if (nav) {
        var existing = document.getElementById('nav-auth') || nav.querySelector('[data-auth-link]');
        if (existing) {
          existing.textContent = label;
          existing.href = href;
          existing.className = 'nav-cta';
          existing.setAttribute('data-auth-link', '1');
        } else {
          var li = document.createElement('li');
          li.id = 'nav-auth-slot';
          var a = document.createElement('a');
          a.href = href;
          a.id = 'nav-auth';
          a.textContent = label;
          a.className = 'nav-cta';
          a.setAttribute('data-auth-link', '1');
          li.appendChild(a);
          var tgl = nav.querySelector('.tgl, .theme-toggle-nav');
          if (tgl && tgl.closest('li')) nav.insertBefore(li, tgl.closest('li'));
          else nav.appendChild(li);
        }
      }
    } else {
      slot.innerHTML = '';
      var b = document.createElement('a');
      b.href = href;
      b.id = 'nav-auth';
      b.textContent = label;
      b.className = 'nav-cta';
      b.setAttribute('data-auth-link', '1');
      slot.appendChild(b);
    }

    var mm = document.getElementById('mobMenu') || document.getElementById('mmenu') || document.querySelector('.mmenu');
    if (mm) {
      var mExisting = mm.querySelector('[data-auth-link]') || mm.querySelector('#mob-nav-auth');
      if (mExisting) {
        mExisting.textContent = label;
        mExisting.href = href;
        mExisting.className = 'nav-cta';
        mExisting.setAttribute('data-auth-link', '1');
      } else {
        var ma = document.createElement('a');
        ma.href = href;
        ma.id = 'mob-nav-auth';
        ma.setAttribute('data-auth-link', '1');
        ma.textContent = label;
        ma.className = 'nav-cta';
        var mtgl = mm.querySelector('.tgl, button');
        if (mtgl) mm.insertBefore(ma, mtgl);
        else mm.appendChild(ma);
      }
    }
  }

  function init() {
    // Rewrite any stale /account links to the cloud front door.
    try {
      var links = document.querySelectorAll('a[href="/account"], a[href="/login"]');
      for (var i = 0; i < links.length; i++) {
        var el = links[i];
        if (el.id === 'nav-auth' || el.hasAttribute('data-auth-link')) continue;
        el.href = cloudHref();
      }
    } catch (e) {}
    checkSession(injectNav);
  }

  if (document.readyState !== 'loading') init();
  else document.addEventListener('DOMContentLoaded', init);
})();
