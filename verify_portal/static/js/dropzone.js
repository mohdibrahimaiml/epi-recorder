(function(){
  var dz=document.getElementById('dropZoneEl');
  var fi=document.getElementById('fileInput');
  var dr=document.getElementById('dropResult');
  var sp=null;

  function _showLoading(){
    if(!sp){
      sp=document.createElement('div');
      sp.style.cssText='text-align:center;padding:40px;margin-top:16px;color:var(--ink-soft)';
      var d=document.createElement('div');
      d.style.cssText='width:40px;height:40px;border:3px solid var(--border);border-top-color:var(--accent);border-radius:50%;margin:0 auto 16px;animation:epiSpin 1s linear infinite';
      sp.appendChild(d);
      sp.appendChild(document.createTextNode('Verifying integrity, signature, and AIUC-1 compliance...'));
      dz.parentNode.insertBefore(sp,dz.nextSibling);
      var style=document.createElement('style');
      style.textContent='@keyframes epiSpin{to{transform:rotate(360deg)}}';
      document.head.appendChild(style);
    }
    sp.style.display='block';
    dz.style.opacity='0.6';
    if(dr)dr.style.display='none';
  }

  function _hideLoading(){
    if(sp)sp.style.display='none';
    dz.style.opacity='1';
  }

  function _showError(msg,hint){
    _hideLoading();
    if(!dr)return;
    dr.style.display='block';
    dr.innerHTML='<div style=\"text-align:center;padding:30px;border:1px solid var(--border);border-radius:12px;background:var(--surface);margin-top:16px\">'+
      '<div style=\"font-size:48px;margin-bottom:12px\">&#10060;</div>'+
      '<h3 style=\"color:var(--error);margin-bottom:8px\">Verification Failed</h3>'+
      '<p style=\"color:var(--ink-soft);margin-bottom:4px\">'+msg+'</p>'+
      (hint?'<p style=\"color:var(--ink-soft);font-size:0.85rem\">'+hint+'</p>':'')+
      '<a href=\"/verify\" style=\"display:inline-block;margin-top:16px;background:var(--accent);color:#fff;padding:10px 24px;border-radius:8px;text-decoration:none;font-weight:600\">Open Verify Portal</a>'+
      '</div>';
  }

  async function handleEPIFile(f){
    _showLoading();
    var fd=new FormData();
    fd.append('file',f,'uploaded.epi');
    fd.append('aiuc1','true');

    try{
      var r=await fetch('/api/verify',{method:'POST',body:fd});
      var d=await r.json();

      if(!r.ok){
        _showError(d.detail||'Server returned '+r.status, 'Try the Verify Portal at /verify for direct upload.');
        return;
      }

      _hideLoading();
      if(!dr)return;
      dr.style.display='block';

      var trust=d.trust_level||'UNKNOWN';
      var icon=trust==='HIGH'?'&#9989;':trust==='MEDIUM'?'&#9888;&#65039;':'&#10060;';
      var msg=d.trust_message||(d.decision||{}).reason||'';

      var tc=trust==='HIGH'?'#2e7d32':trust==='MEDIUM'?'#e65100':'#c62828';

      var html='<div style=\"margin-top:16px;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:30px;text-align:center\">'+
        '<div style=\"font-size:48px;margin-bottom:16px\">'+icon+'</div>'+
        '<h2 style=\"color:'+tc+';margin-bottom:8px;font-size:clamp(1.3rem,3vw,1.8rem)\">'+trust+' TRUST</h2>'+
        '<p style=\"color:var(--ink-soft);max-width:500px;margin:0 auto 20px;line-height:1.5\">'+msg+'</p>'+
        '<a href=\"/verify\" style=\"display:inline-block;background:var(--accent);color:#fff;padding:10px 24px;border-radius:8px;text-decoration:none;font-weight:600\">Full Report &#8594;</a>'+
        '</div>';

      var aiuc=d.aiuc1;
      if(aiuc&&aiuc.domains){
        html+='<div style=\"display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin-top:20px;max-width:660px;margin-left:auto;margin-right:auto;padding:0 16px\">';
        for(var id in aiuc.domains){
          var dm=aiuc.domains[id];
          var bg='#e8f5e9',clr='#2e7d32';
          if(dm.status==='PARTIAL'){bg='#fff3e0';clr='#e65100';}
          else if(dm.status==='FAIL'){bg='#ffebee';clr='#c62828';}
          html+='<span style=\"background:'+bg+';color:'+clr+';padding:6px 14px;border-radius:999px;font-size:12px;font-weight:700;white-space:nowrap\">'+dm.label+' &#8226; '+dm.status+'</span>';
        }
        html+='</div>';
      }

      dr.innerHTML=html;

    }catch(e){
      _showError('Could not reach verification service.', 'The API may be starting up. Try again in 30 seconds.');
    }
  }

  if(dz){
    dz.addEventListener('click',function(){if(fi)fi.click()});
    dz.addEventListener('dragover',function(e){e.preventDefault();dz.classList.add('dragover')});
    dz.addEventListener('dragleave',function(){dz.classList.remove('dragover')});
    dz.addEventListener('drop',function(e){
      e.preventDefault();dz.classList.remove('dragover');
      var files=e.dataTransfer.files;
      if(files&&files.length)handleEPIFile(files[0]);
    });
  }

  if(fi){
    fi.addEventListener('change',function(){if(fi.files.length)handleEPIFile(fi.files[0])});
    fi.setAttribute('accept','.epi');
  }
})();
