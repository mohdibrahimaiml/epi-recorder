// EPI Auth UI — injects sign-in/sign-out button into the nav on all pages
// API calls go to the Render backend, token stored in localStorage
(function(){
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
      var li = document.getElementById('nav-auth');
      if (li) { li.innerHTML = '<a href="/account">' + (user.login || 'Account') + '</a>'; return; }
      li = document.createElement('li');
      li.id = 'nav-auth';
      var a = document.createElement('a');
      a.href = '/account';
      a.textContent = user.login || 'Account';
      li.appendChild(a);
      navLinks.appendChild(li);
    })
    .catch(function() {
      var li = document.getElementById('nav-auth');
      if (li) { li.innerHTML = '<a href="/account" class="nav-link-cta">Sign In</a>'; return; }
      li = document.createElement('li');
      li.id = 'nav-auth';
      var a = document.createElement('a');
      a.href = '/account';
      a.className = 'nav-link-cta';
      a.textContent = 'Sign In';
      li.appendChild(a);
      navLinks.appendChild(li);
    });
})();
