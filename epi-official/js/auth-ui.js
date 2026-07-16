// EPI Auth UI — injects sign-in/sign-out button into the nav on all pages
// Does NOT run on /account page (that page manages its own nav)
(function(){
  if (window.location.pathname === '/account') return;

  var API_BASE = 'https://epi-verify-portal.onrender.com';
  var navLinks = document.getElementById('navLinks');
  if (!navLinks) return;

  // 1. Check localStorage first — shows cached user instantly (no Render delay)
  var cached = localStorage.getItem('epi_user');
  if (cached) {
    try {
      var user = JSON.parse(cached);
      injectNav(user.login || 'Account', false);
      return;
    } catch(e) {}
  }

  // 2. No cached user — try Render (may be cold)
  var token = localStorage.getItem('epi_token') || '';
  fetch(API_BASE + '/api/auth/me', {
    credentials: 'include',
    headers: token ? { 'Authorization': 'Bearer ' + token } : {}
  })
    .then(function(r) {
      if (r.ok) return r.json();
      throw new Error('not logged in');
    })
    .then(function(user) {
      localStorage.setItem('epi_user', JSON.stringify(user));
      injectNav(user.login || 'Account', false);
    })
    .catch(function() {
      injectNav('Sign In', true);
    });
})();

function injectNav(label, isCta) {
  if (document.getElementById('nav-auth')) return;
  var navLinks = document.getElementById('navLinks');
  var li = document.createElement('li');
  li.id = 'nav-auth';
  var a = document.createElement('a');
  a.href = '/account';
  if (isCta) a.className = 'nav-link-cta';
  a.textContent = label;
  li.appendChild(a);
  var oldCta = navLinks.querySelector('.nav-link-cta');
  if (oldCta && !isCta) oldCta.remove();
  navLinks.appendChild(li);
}
