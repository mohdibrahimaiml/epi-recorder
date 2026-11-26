// Status page: probes EPI Cloud from the browser and refreshes every 60s.
(function(){
    // Single account system: status checks the new EPI Cloud, not Render.
    var CLOUD = 'https://cloud.epilabs.org';

    function check(name, dotId, detailId, timeId, url) {
      var dot = document.getElementById(dotId);
      var detail = document.getElementById(detailId);
      var time = document.getElementById(timeId);
      var start = Date.now();
      fetch(url, { cache: 'no-store' }).then(function(r) {
        var ms = Date.now() - start;
        if (r.ok) {
          dot.className = 'status-indicator up';
          detail.textContent = 'Responding (' + ms + 'ms)';
        } else {
          dot.className = 'status-indicator down';
          detail.textContent = 'HTTP ' + r.status + ' (' + ms + 'ms)';
        }
        time.textContent = new Date().toLocaleTimeString();
      }).catch(function() {
        dot.className = 'status-indicator down';
        detail.textContent = 'Unreachable';
        time.textContent = new Date().toLocaleTimeString();
      });
    }

    check('EPI Cloud', 'dot-auth', 'detail-auth', 'time-auth', CLOUD + '/health');

    // Re-check every 60 seconds
    setInterval(function() {
      document.querySelectorAll('.status-indicator').forEach(function(d) { d.className = 'status-indicator checking'; });
      document.querySelectorAll('.status-detail:not(#detail-note)').forEach(function(d) { d.textContent = 'Re-checking...'; });
      check('EPI Cloud', 'dot-auth', 'detail-auth', 'time-auth', CLOUD + '/health');
    }, 60000);
  })();
