// EPI Auth UI — injects sign-in/sign-out button into the nav on all pages
// Does NOT run on /account page (that page manages its own nav)
(function(){
  // Skip on account page — it has its own auth handling
  if (window.location.pathname === '/account') return;

  var API_BASE = 'https://epi-verify-portal.onrender.com';
  var navLinks = document.getElementById('navLinks');
  if (!navLinks) return;

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
      if (document.getElementById('nav-auth')) return;
      var li = document.createElement('li');
      li.id = 'nav-auth';
      var a = document.createElement('a');
      a.href = '/account';
      a.textContent = user.login || 'Account';
      li.appendChild(a);
      var cta = navLinks.querySelector('.nav-link-cta');
      if (cta) cta.remove();
      navLinks.appendChild(li);
    })
    .catch(function() {
      if (document.getElementById('nav-auth')) return;
      var li = document.createElement('li');
      li.id = 'nav-auth';
      var a = document.createElement('a');
      a.href = '/account';
      a.className = 'nav-link-cta';
      a.textContent = 'Sign In';
      li.appendChild(a);
      navLinks.appendChild(li);
    });
})();
