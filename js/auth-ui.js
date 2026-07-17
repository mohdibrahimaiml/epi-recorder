// EPI Auth UI — nav sign-in / account label on all pages except /account
(function () {
  if (window.location.pathname === '/account' || window.location.pathname === '/account/') return;

  var API_BASE = 'https://epi-verify-portal.onrender.com';
  var TOKEN_KEY = 'epi_token';
  var USER_KEY = 'epi_user';

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
    var oldCta = navLinks.querySelector('.nav-link-cta');
    if (oldCta && !isCta) {
      // keep pricing CTA; only remove duplicate "Get Started" if it points to account
    }
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

  // Revalidate session in background
  if (!token && !cached) return;

  fetch(API_BASE + '/api/auth/me', {
    credentials: 'include',
    headers: token ? { Authorization: 'Bearer ' + token } : {},
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
      // keep token only if 401 would clear — network errors keep cache
      injectNav(token ? 'Account' : 'Sign In', !token);
    });
})();
