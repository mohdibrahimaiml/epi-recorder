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
      sp.appendChild(document.createTextNode('Running EPI-SPEC v4.2 verification: structural, integrity, signature, chain, SCITT...'));
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
    var h='<div style=\"text-align:center;padding:30px;border:1px solid var(--border);border-radius:12px;background:var(--surface);margin-top:16px\">'+
      '<div style=\"font-size:48px;margin-bottom:12px\">&#10060;</div>'+
      '<h3 style=\"color:var(--error);margin-bottom:8px\">Verification Failed</h3>'+
      '<p style=\"color:var(--ink-soft);margin-bottom:4px\">'+msg+'</p>'+
      (hint?'<p style=\"color:var(--ink-soft);font-size:0.85rem\">'+hint+'</p>':'')+
      '<a href=\"/verify\" style=\"display:inline-block;margin-top:16px;background:var(--accent);color:#fff;padding:10px 24px;border-radius:8px;text-decoration:none;font-weight:600\">Open Verify Portal</a>'+
      '</div>';
    dr.innerHTML=h;
  }

  function _checkBadge(num,label,val,goodHint,badHint){
    var ok=val===true;
    var clr=ok?'#2e7d32':'#c62828';
    var bg=ok?'rgba(46,125,50,0.08)':'rgba(198,40,40,0.08)';
    var icon=ok?'&#9745;':'&#9746;';
    if(val===null||val===undefined){
      clr='var(--ink-soft)';bg='var(--surface-2)';icon='&#9633;';ok=null;
    }
    var text=ok===true?goodHint:ok===false?badHint:'N/A';
    return '<div style=\"display:flex;align-items:center;gap:10px;padding:10px 14px;background:'+bg+';border-radius:8px;border:1px solid '+(ok===null?'var(--border)':(ok?'rgba(46,125,50,0.25)':'rgba(198,40,40,0.25)'))+'\">'+
      '<span style=\"font-size:18px;color:'+clr+'\">'+icon+'</span>'+
      '<div><div style=\"font-weight:700;font-size:13px;color:'+clr+'\">'+num+'. '+label+'</div>'+
      '<div style=\"font-size:11px;color:var(--ink-soft)\">'+text+'</div></div></div>';
  }

  async function handleEPIFile(f){
    _showLoading();
    var fd=new FormData();
    fd.append('file',f,'uploaded.epi');
    fd.append('aiuc1','true');

    try{
      var r=await fetch('https://epi-verify-portal.onrender.com/api/verify',{method:'POST',body:fd});
      var d=await r.json();

      if(!r.ok){
        _showError(d.detail||'Server returned '+r.status, 'Try the Verify Portal at /verify for direct upload.');
        return;
      }

      _hideLoading();
      if(!dr)return;
      dr.style.display='block';

      var trust=d.trust_level||'UNKNOWN';
      var icon=trust==='HIGH'?'&#9989;':trust==='MEDIUM'?'&#9888;':'&#10060;';
      var msg=d.trust_message||(d.decision||{}).reason||'';
      var tc=trust==='HIGH'?'#2e7d32':trust==='MEDIUM'?'#e65100':'#c62828';
      var fcts=d.facts||{};
      var meta=d.metadata||{};
      var specVer=meta.spec_version||'?';
      var steps=meta.steps_count||0;

      var structuralOk=!!specVer;
      var countOk=steps>0;
      var countHint=countOk?steps+' execution steps recorded':'Step count unavailable';

      var h='<div style=\"margin-top:16px;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:28px;text-align:center\">'+
        '<div style=\"font-size:48px;margin-bottom:16px\">'+icon+'</div>'+
        '<h2 style=\"color:'+tc+';margin-bottom:4px;font-size:clamp(1.3rem,3vw,1.8rem)\">'+trust+' TRUST</h2>'+
        '<div style=\"color:var(--ink-soft);font-size:12px;margin-bottom:16px\">EPI-SPEC v'+specVer+' \u00b7 '+steps+' steps</div>'+
        '<p style=\"color:var(--ink-soft);max-width:500px;margin:0 auto 20px;line-height:1.5\">'+msg+'</p>'+

        '<div style=\"display:flex;flex-direction:column;gap:6px;max-width:560px;margin:0 auto 16px;text-align:left\">'+
          _checkBadge(1,'Structural',structuralOk,'Valid EPI envelope or ZIP container','Invalid or corrupted format')+
          _checkBadge(2,'Integrity',fcts.integrity_ok,'All file hashes match manifest SHA-256','Hash mismatch detected')+
          _checkBadge(3,'Signature',fcts.signature_valid,'Ed25519 signature verified against manifest','Invalid or tampered signature')+
          _checkBadge(4,'Chain',fcts.chain_ok,'prev_hash links intact; hash-linked timeline','Chain broken - steps modified or reordered')+
          _checkBadge(5,'Sequence',fcts.sequence_ok,'Step indices monotonic, timestamps chronological','Sequence gap or out-of-order step')+
          _checkBadge(6,'Count',countOk,countHint,'Step count unavailable')+
          _checkBadge(7,'SCITT',fcts.transparency_ok,'Merkle inclusion proof verified; RFC 9162 compliant','SCITT transparency not available')+
        '</div>'+

        (fcts.transparency_ok===true?
          '<div style=\"background:rgba(21,101,192,0.08);border:1px solid rgba(21,101,192,0.25);border-radius:8px;padding:10px 14px;max-width:560px;margin:12px auto;font-size:13px;color:#1565c0\">&#128274; SCITT-anchored: Merkle inclusion proof verified. Evidence registered in transparency ledger per RFC 9162.</div>'
          :'')+

        '<a href=\"/verify\" style=\"display:inline-block;background:var(--accent);color:#fff;padding:10px 24px;border-radius:8px;text-decoration:none;font-weight:600;margin-top:8px\">Full Report &#8594;</a>'+
        '</div>';

      var aiuc=d.aiuc1;
      if(aiuc&&aiuc.domains){
        h+='<div style=\"display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin-top:16px;max-width:660px;margin-left:auto;margin-right:auto;padding:0 16px\">';
        var keys=Object.keys(aiuc.domains).sort();
        for(var i=0;i<keys.length;i++){
          var dm=aiuc.domains[keys[i]];
          var bg='#e8f5e9',clr='#2e7d32';
          if(dm.status==='PARTIAL'){bg='#fff3e0';clr='#e65100';}
          else if(dm.status==='FAIL'){bg='#ffebee';clr='#c62828';}
          h+='<span style=\"background:'+bg+';color:'+clr+';padding:6px 14px;border-radius:999px;font-size:12px;font-weight:700;white-space:nowrap\">'+dm.label+' &#8226; '+dm.status+'</span>';
        }
        h+='</div>';
      }

      dr.innerHTML=h;

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
