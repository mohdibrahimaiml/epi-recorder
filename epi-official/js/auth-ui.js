// EPI Auth UI — nav + free-tier keep-warm wake on every page
(function () {
  var API_BASE = (function () {
    var h = (location && location.hostname) || '';
    if (h === 'epilabs.org' || h === 'www.epilabs.org' || h.endsWith('.pages.dev')) return '';
    return 'https://epi-verify-portal.onrender.com';
  })();
  var TOKEN_KEY = 'epi_token';
  var USER_KEY = 'epi_user';

  // ── Always wake the free Render instance ASAP (fire-and-forget) ──
  // Same-origin /api/* is proxied by Cloudflare Pages Functions → Render.
  function wakeApi() {
    try {
      fetch(API_BASE + '/api/ping', { mode: 'cors', credentials: 'omit', cache: 'no-store' }).catch(function () {});
      fetch(API_BASE + '/api/auth/status', { mode: 'cors', credentials: 'omit', cache: 'no-store' }).catch(function () {});
    } catch (e) {}
  }
  wakeApi();

  // Skip nav injection on account page (it manages its own nav)
  if (window.location.pathname === '/account' || window.location.pathname === '/account/') return;

  var navLinks = document.getElementById('navLinks');
  if (!navLinks) return;

  function injectNav(label, isCta) {
    var existing = document.getElementById('nav-auth');
    if (existing) existing.remove();
    var li = document.createElement('li');
    li.id = 'nav-auth';
    var a = document.createElement('a');
    a.href = '/account';
    if (isCta) a.className = 'nav-link-cta';
    a.textContent = label;
    li.appendChild(a);
    navLinks.appendChild(li);
  }

  // Instant UI from cache
  var cached = localStorage.getItem(USER_KEY);
  var token = localStorage.getItem(TOKEN_KEY) || '';
  if (cached) {
    try {
      var user = JSON.parse(cached);
      injectNav(user.login || 'Account', false);
    } catch (e) {
      injectNav('Sign In', true);
    }
  } else if (!token) {
    injectNav('Sign In', true);
  } else {
    injectNav('Account', false);
  }

  // Revalidate session in background (also keeps instance warm)
  if (!token && !cached) return;

  fetch(API_BASE + '/api/auth/me', {
    credentials: 'include',
    headers: token ? { Authorization: 'Bearer ' + token } : {},
    cache: 'no-store',
  })
    .then(function (r) {
      if (r.ok) return r.json();
      throw new Error('not logged in');
    })
    .then(function (user) {
      localStorage.setItem(USER_KEY, JSON.stringify(user));
      injectNav(user.login || 'Account', false);
    })
    .catch(function () {
      localStorage.removeItem(USER_KEY);
      injectNav(token ? 'Account' : 'Sign In', !token);
    });
})();
