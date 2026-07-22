// EPI Auth UI — nav slot + free-tier keep-warm wake on every page
(function () {
  var API_BASE = (function () {
    var h = (location && location.hostname) || '';
    if (h === 'epilabs.org' || h === 'www.epilabs.org' || h.endsWith('.pages.dev')) return '';
    return 'https://epi-verify-portal.onrender.com';
  })();
  var TOKEN_KEY = 'epi_token';
  var USER_KEY = 'epi_user';

  function wakeApi() {
    try {
      fetch(API_BASE + '/api/ping', { mode: 'cors', credentials: 'omit', cache: 'no-store' }).catch(function () {});
      fetch(API_BASE + '/api/auth/status', { mode: 'cors', credentials: 'omit', cache: 'no-store' }).catch(function () {});
    } catch (e) {}
  }
  wakeApi();

  if (window.location.pathname === '/account' || window.location.pathname === '/account/') return;

  // Prefer dedicated slot so nav stays slim
  var slot = document.getElementById('nav-auth-slot');
  var navLinks = document.getElementById('navLinks');
  if (!slot && !navLinks) return;

  function injectNav(label, isCta) {
    if (slot) {
      slot.innerHTML = '';
      var a = document.createElement('a');
      a.href = '/account';
      a.id = 'nav-auth';
      a.textContent = label;
      if (isCta) a.className = 'nav-auth-quiet';
      slot.appendChild(a);
      return;
    }
    // Fallback: append once
    var existing = document.getElementById('nav-auth');
    if (existing) existing.parentElement.remove();
    var li = document.createElement('li');
    var a2 = document.createElement('a');
    a2.href = '/account';
    a2.id = 'nav-auth';
    a2.textContent = label;
    li.appendChild(a2);
    navLinks.appendChild(li);
  }

  var cached = localStorage.getItem(USER_KEY);
  var token = localStorage.getItem(TOKEN_KEY) || '';
  if (cached) {
    try {
      var user = JSON.parse(cached);
      injectNav(user.login || 'Account', false);
    } catch (e) {
      injectNav('Sign in', false);
    }
  } else if (!token) {
    injectNav('Sign in', false);
  } else {
    injectNav('Account', false);
  }

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
      injectNav(token ? 'Account' : 'Sign in', false);
    });
})();
