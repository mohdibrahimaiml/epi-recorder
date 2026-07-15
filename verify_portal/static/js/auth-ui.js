// EPI Auth UI — injects login/logout button into the nav on all pages
(function(){
  var navLinks = document.getElementById('navLinks');
  if (!navLinks) return;
  var li = document.getElementById('nav-auth');
  if (li) return;

  fetch('/api/auth/me', { credentials: 'include' })
    .then(function(r) {
      if (r.ok) return r.json();
      throw new Error('not logged in');
    })
    .then(function(user) {
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
