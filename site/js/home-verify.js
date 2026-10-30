(function(){
"use strict";
/* ── VERIFY DROP ZONE ──
   Faithful browser-side EPI verification matching the Python codebase:
   - Container detection (legacy ZIP + envelope-v2 with <!-- magic)
   - mimetype validation (application/vnd.epi+zip)
   - File manifest SHA-256 integrity check
   - Ed25519 signature verification via Web Crypto API
   - Structured report: facts + identity + metadata (matching create_verification_report) */
var dz=document.getElementById('dropZoneEl'),fi=document.getElementById('fileInput'),dr=document.getElementById('dropResult');
var EPI_MIMETYPE='application/vnd.epi+zip',EPI_ENVELOPE_MAGIC='<!--';

function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}

function reportDOM(report){
  var f=report.facts,i=report.identity,m=report.metadata;
  var idStatus=(i&&i.status)||'UNKNOWN';
  var pinned=idStatus==='KNOWN';
  var trustColor='var(--verified)',trustIcon='&#10003;';
  // Green only when seal OK *and* identity pinned. Unpinned valid seal = amber.
  if(!f.integrity_ok||f.signature_valid===false){trustColor='var(--tamper)';trustIcon='&#10007;'}
  else if(!f.has_signature){trustColor='var(--warn)';trustIcon='&#9888;'}
  else if(f.signature_valid===true&&!pinned){trustColor='var(--warn)';trustIcon='&#9888;'}
  else if(f.signature_valid===true&&pinned){trustColor='var(--verified)';trustIcon='&#10003;'}
  else if(f.signature_valid===null){trustColor='var(--warn)';trustIcon='&#9888;'}

  var steps=m.steps_count!==null?(' · '+m.steps_count+' steps'):'';
  var chks=[];
  // Identity first — claim trust requires known sealer
  var idDisplay=idStatus==='UNKNOWN'?'NOT_PINNED':idStatus;
  chks.push('<strong>Identity: '+idDisplay+'</strong>'+(pinned?'':' <span style="color:var(--warn)">(not claim-ready)</span>'));
  if(f.structure_ok)chks.push('Structure valid');
  if(f.integrity_ok)chks.push('Hashes match (seal)');
  else chks.push('<span style="color:var(--tamper)">Hashes mismatch ('+Object.keys(f.mismatches||{}).length+')</span>');
  if(f.completeness_ok===false)chks.push('<span style="color:var(--warn)">Capture completeness: gaps (not a broken seal)</span>');
  if(f.chain_ok===false)chks.push('<span style="color:var(--tamper)">Step chain: broken</span>');
  if(f.has_signature){
    if(f.signature_valid===true)chks.push('Signature: VALID (Ed25519) — proves consistency, not who');
    else if(f.signature_valid===false)chks.push('<span style="color:var(--tamper)">Signature: INVALID</span>');
    else chks.push('Signature: UNVERIFIED (browser Ed25519 limited — use epi verify)');
  }else{chks.push('Unsigned')}
  chks.push('Chain: '+(f.chain_ok!==false?'intact':'<span style="color:var(--tamper)">broken</span>'));
  if(f.content_truncated===true)chks.push('<span style="color:var(--tamper)">Payload: truncated before seal</span>');
  else if(f.content_truncated===false)chks.push('Payload: full strings sealed');
  else if(m.spec_version)chks.push('Payload: content_truncated not set (pre-4.4.2 seal)');

  var levelLabel=report.trust_level||'';
  var title=levelLabel;
  if(levelLabel==='HIGH')title='SEAL · IDENTITY PINNED';
  else if(levelLabel==='LOW'&&report.facts.signature_valid===true)title='SEAL VALID · IDENTITY NOT PINNED';
  else if(levelLabel.indexOf('SEAL')===0||levelLabel==='NONE')title=levelLabel;
  else if(levelLabel)title=levelLabel+' TRUST';
  return '<div style="font-size:0.82rem;margin-bottom:0.6rem"><strong style="font-size:1.05rem;color:'+trustColor+'">'+trustIcon+' '+title+'</strong> <span style="color:var(--ink-muted);font-size:0.72rem">v'+esc(m.spec_version)+steps+'</span></div>'
    +chks.join('<br>')
    +'<div style="margin-top:0.5rem;font-size:0.68rem;color:var(--ink-dim);border-top:1px solid var(--border);padding-top:0.5rem">'+esc(report.trust_message)+'</div>'
    +(i.detail?'<div style="margin-top:0.3rem;font-size:0.68rem;color:var(--ink-dim)">'+esc(i.detail)+'</div>':'')
    +(f.viewer_note?'<div style="margin-top:0.3rem;font-size:0.68rem;color:var(--ink-dim)">'+esc(f.viewer_note)+'</div>':'');
}

function updateChecks(report){
  function set(id,pass,text){var el=document.getElementById(id);if(!el)return;if(pass)el.classList.add('pass');el.innerHTML='<span class="check-dot"></span> '+text} // static-html: callers pass static markup + internal enum/count only (audited); file text never reaches set()
  var f=report.facts;
  set('chk1',f.structure_ok,'01 · Structure '+(f.structure_ok?'Valid — valid EPI archive':'<span style="color:var(--tamper)">Invalid</span>'));
  set('chk2',f.integrity_ok,'02 · Integrity '+(f.integrity_ok?'PASS — all file hashes match':'<span style="color:var(--tamper)">FAIL — '+Object.keys(f.mismatches||{}).length+' mismatch(es)</span>'));
  if(f.has_signature){
    // Only mark pass when crypto actually returned true — null is not a green check
    set('chk3',f.signature_valid===true,'03 · Signature '+(f.signature_valid===true?'VALID — Ed25519 verified':f.signature_valid===null?'CHECK — browser Ed25519 limited (use epi verify)':'<span style="color:var(--tamper)">INVALID — tampered</span>'));
  }else{set('chk3',false,'03 · Signature — none present (unsigned)')}
  set('chk4',f.chain_ok!==false,'04 · Chain '+(f.chain_ok!==false?'INTACT':'<span style="color:var(--tamper)">BROKEN</span>'));
  // Identity is not org-pinned in the browser — never claim KNOWN/HIGH here
  var idLabel = report.identity && report.identity.status ? report.identity.status : 'UNKNOWN';
  set('chk5', false, '05 · Identity — '+idLabel+' (not pinned in browser · use epi keys trust / CLI)');
  set('chk6', false, '06 · Full audit — notarization, SCITT, policy: run <code style="font-size:0.75em">epi verify</code> offline');
}

async function sha256(buf){var h=await crypto.subtle.digest('SHA-256',buf);return Array.from(new Uint8Array(h)).map(function(b){return b.toString(16).padStart(2,'0')}).join('')}
function buf2hex(buf){return Array.from(new Uint8Array(buf)).map(function(b){return b.toString(16).padStart(2,'0')}).join('')}

async function deriveKeyName(pubKeyHex){
  var hash=await sha256(new TextEncoder().encode(pubKeyHex));
  return hash.substring(0,16);
}

async function verifyEd25519(sigStr,pubKeyHex,hashHex){
  if(typeof globalThis.epiVerifyEd25519!=='function'){
    return{valid:null,msg:'epi-manifest-preimage.js failed to load'};
  }
  return globalThis.epiVerifyEd25519(sigStr,pubKeyHex,hashHex);
}

// ── Approval labels (step 3c) ────────────────────────────────────────────────
// The browser has no approver registry, so it can only say what KIND of
// approval a step is — never that a human was verified. Wording is fixed here
// and asserted by tests.
function approvalSourceLabel(c){
  c=c||{};
  var claimed=typeof c.claimed_approval_source==='string'?c.claimed_approval_source:'';
  if(claimed)return'Agent-reported (claimed '+claimed+'; the gateway did not accept it)';
  var src=String(c.approval_source||'raw_api_unverified');
  if(src==='gateway_link_unsigned')return'Gateway link click (not a signed approval)';
  if(src==='gateway_link_authenticated')return'Gateway link click by a logged-in user (not a signed approval)';
  if(src==='gateway_human')return'Gateway link click, older gateway (not a signed approval)';
  return'Agent-reported';
}

function approvalStepLine(c){
  c=c||{};
  var said=c.approved===true?'approved':c.approved===false?'rejected':'replied';
  var who=c.reviewer?String(c.reviewer):'a reviewer';
  var action=c.action?' '+String(c.action):'';
  var label=approvalSourceLabel(c);
  var body=label==='Agent-reported'
    ? 'Agent-reported: '+who+' '+said+action
    : label;
  return body+(c.reason?': '+String(c.reason):'');
}

function hexToBytes(h){
  h=String(h||'');
  var n=h.length>>1,a=new Uint8Array(n);
  for(var i=0;i<n;i++)a[i]=parseInt(h.substr(i*2,2),16);
  return a;
}

async function verifyEd25519Raw(pubHex,sigHex,msgBytes){
  try{
    var pub=hexToBytes(pubHex);
    if(pub.length!==32)return false;
    var key=await crypto.subtle.importKey('raw',pub,{name:'Ed25519'},false,['verify']);
    return await crypto.subtle.verify({name:'Ed25519'},key,hexToBytes(sigHex),msgBytes);
  }catch(e){return false}
}

// Same value as epi_core.keys.key_fingerprint: SHA-256 over the lowercase hex
// key TEXT, first 16 hex chars, grouped by 4. Never over the raw key bytes.
async function keyFingerprintHex(pubHex){
  var text=String(pubHex||'').trim().toLowerCase();
  if(text.length!==64)return null;
  var digest=await sha256(new TextEncoder().encode(text));
  var short=digest.substring(0,16);
  return short.match(/.{1,4}/g).join(' ');
}

/*
  Container detection + ZIP extract.
  Prefer shared epi-verify-core (window.epiDetectContainer / epiExtractZipBytes)
  so homepage and /verify/ cannot drift. Fallback mirrors the same rules:
  envelope-v2 magic "<!--", legacy ZIP "PK", BOM/junk preamble, and
  EPI_ZIP_PAYLOAD_START marker (never naive first-PK — embedded JSZip
  source contains a false PK\x03\x04 string).
*/
var EPI_ZIP_MARKER='\n<!-- EPI_ZIP_PAYLOAD_START -->\n';
var EPI_HEADER_SIZE=128;

// Outer polyglot viewer check (SEAL FAIL — FILE ALTERED on a flipped byte in
// the display layer). The one implementation lives in epi-verify-core.js
// (window.epiVerifyPolyglotViewer) so /verify/, the homepage and the trust page
// cannot drift. Fail closed if the core did not load.
async function verifyPolyglotViewer(u8){
  if(typeof window!=='undefined'&&typeof window.epiVerifyPolyglotViewer==='function'){
    return window.epiVerifyPolyglotViewer(u8,0);
  }
  return{fail:true,detail:'verifier core (epi-verify-core.js) did not load — hard-refresh and try again',note:null};
}

function toU8(buffer){
  if(buffer instanceof Uint8Array)return buffer;
  if(buffer instanceof ArrayBuffer)return new Uint8Array(buffer);
  if(ArrayBuffer.isView(buffer))return new Uint8Array(buffer.buffer,buffer.byteOffset,buffer.byteLength);
  return new Uint8Array(buffer||[]);
}

// Name a common non-EPI file kind from its first bytes, so a visitor who
// dropped the wrong file gets a plain answer instead of a hex dump.
function sniffFileKind(u8){
  if(!u8||u8.length<4)return null;
  if(u8[0]===0x25&&u8[1]===0x50&&u8[2]===0x44&&u8[3]===0x46)return'a PDF document';
  if(u8[0]===0x89&&u8[1]===0x50&&u8[2]===0x4e&&u8[3]===0x47)return'a PNG image';
  if(u8[0]===0xff&&u8[1]===0xd8&&u8[2]===0xff)return'a JPEG image';
  if(u8[0]===0x47&&u8[1]===0x49&&u8[2]===0x46)return'a GIF image';
  if(u8[0]===0x50&&u8[1]===0x4b)return'a ZIP archive';
  return null;
}

function hexPreview(u8,n){
  n=Math.min(n||16,u8.length);
  var p=[];for(var i=0;i<n;i++)p.push(u8[i].toString(16).padStart(2,'0'));
  return p.join(' ');
}

function detectContainer(buffer){
  if(typeof window!=='undefined'&&typeof window.epiDetectContainer==='function'){
    var d=window.epiDetectContainer(buffer);
    return d?d.format:null;
  }
  var u8=toU8(buffer);
  if(u8.length<4)return null;
  var i=0;
  if(u8.length>=3&&u8[0]===0xef&&u8[1]===0xbb&&u8[2]===0xbf)i=3;
  while(i<u8.length&&(u8[i]===0x09||u8[i]===0x0a||u8[i]===0x0d||u8[i]===0x20))i++;
  if(i+3<u8.length&&u8[i]===0x3c&&u8[i+1]===0x21&&u8[i+2]===0x2d&&u8[i+3]===0x2d)return'envelope-v2';
  if(i+1<u8.length&&u8[i]===0x50&&u8[i+1]===0x4b)return'legacy-zip';
  var scan=Math.min(u8.length-4,i+512);
  for(var j=i;j<=scan;j++){
    if(u8[j]===0x3c&&u8[j+1]===0x21&&u8[j+2]===0x2d&&u8[j+3]===0x2d)return'envelope-v2';
    if(u8[j]===0x50&&u8[j+1]===0x4b)return'legacy-zip';
  }
  // Marker anywhere ⇒ envelope
  var marker=new TextEncoder().encode(EPI_ZIP_MARKER);
  var end=Math.min(u8.length,8*1024*1024)-marker.length;
  outer:for(var k=0;k<=end;k++){
    for(var m=0;m<marker.length;m++){if(u8[k+m]!==marker[m])continue outer;}
    return'envelope-v2';
  }
  return null;
}

function extractZIPPayload(buffer,fmt){
  if(typeof window!=='undefined'&&typeof window.epiExtractZipBytes==='function'){
    return window.epiExtractZipBytes(buffer);
  }
  var u8=toU8(buffer);
  if(fmt==='legacy-zip'){
    // Skip preamble if any
    var off=0;
    if(u8.length>=3&&u8[0]===0xef&&u8[1]===0xbb&&u8[2]===0xbf)off=3;
    while(off<u8.length&&(u8[off]===0x09||u8[off]===0x0a||u8[off]===0x0d||u8[off]===0x20))off++;
    while(off+1<u8.length&&!(u8[off]===0x50&&u8[off+1]===0x4b))off++;
    return off===0?u8:u8.slice(off);
  }
  // Envelope: find payload via marker (NOT first PK — viewer embeds JSZip source)
  var headerOff=0;
  if(!(u8[0]===0x3c&&u8[1]===0x21&&u8[2]===0x2d&&u8[3]===0x2d)){
    for(var s=0;s+3<Math.min(u8.length,512);s++){
      if(u8[s]===0x3c&&u8[s+1]===0x21&&u8[s+2]===0x2d&&u8[s+3]===0x2d){headerOff=s;break;}
    }
  }
  var marker=new TextEncoder().encode(EPI_ZIP_MARKER);
  var searchFrom=headerOff+EPI_HEADER_SIZE;
  var zipStart=headerOff+EPI_HEADER_SIZE;
  var foundMarker=false;
  var mend=Math.min(u8.length,searchFrom+8*1024*1024)-marker.length;
  outer2:for(var p=searchFrom;p<=mend;p++){
    for(var q=0;q<marker.length;q++){if(u8[p+q]!==marker[q])continue outer2;}
    zipStart=p+marker.length;foundMarker=true;break;
  }
  if(headerOff+EPI_HEADER_SIZE<=u8.length){
    try{
      var view=new DataView(u8.buffer,u8.byteOffset+headerOff,EPI_HEADER_SIZE);
      var payloadLen=view.getUint32(8,true)+view.getUint32(12,true)*4294967296;
      if(payloadLen>0&&zipStart+payloadLen<=u8.length){
        var sliced=u8.slice(zipStart,zipStart+payloadLen);
        if(sliced[0]===0x50&&sliced[1]===0x4b)return sliced;
      }
    }catch(_e){}
  }
  if(zipStart+1<u8.length&&u8[zipStart]===0x50&&u8[zipStart+1]===0x4b)return u8.slice(zipStart);
  var from=foundMarker?zipStart:headerOff+EPI_HEADER_SIZE;
  for(var r=from;r+3<u8.length;r++){
    if(u8[r]===0x50&&u8[r+1]===0x4b&&u8[r+2]===0x03&&u8[r+3]===0x04)return u8.slice(r);
  }
  return u8.slice(headerOff+EPI_HEADER_SIZE);
}

/*
  Canonical JSON encoder that matches Python json.dumps(sort_keys=True,
  separators=(',',':'), ensure_ascii=False).

  We also preserve the original text for every JSON number token.  Python keeps
  the trailing ".0" for floats (e.g. 900.0) while JavaScript's JSON.stringify
  drops it (900).  Without preservation, manifests/steps that contain float
  metrics would hash differently in the browser and signature verification would
  fail even for valid artifacts.
*/
function tokenizeJSON(str){
  var tokens=[],i=0;
  while(i<str.length){
    var c=str[i];
    if(c===' '||c==='\t'||c==='\n'||c==='\r'){i++;continue;}
    if(c==='"'){
      i++;var s='';
      while(i<str.length){
        var ch=str[i];
        if(ch==='\\'){
          i++;
          var e=str[i];
          if(e==='n')s+='\n';
          else if(e==='t')s+='\t';
          else if(e==='r')s+='\r';
          else if(e==='b')s+='\b';
          else if(e==='f')s+='\f';
          else if(e==='u'){
            s+=String.fromCharCode(parseInt(str.substring(i+1,i+5),16));
            i+=4;
          }
          else s+=e; // \" \\ \/
          i++;
        }
        else if(ch==='"'){i++;break;}
        else{s+=ch;i++;}
      }
      tokens.push({type:'string',value:s});
      continue;
    }
    if(c==='{'||c==='}'||c==='['||c===']'||c===':'||c===','){tokens.push({type:c});i++;continue;}
    if(str.substring(i,i+4)==='true'){tokens.push({type:'true',value:true});i+=4;continue;}
    if(str.substring(i,i+5)==='false'){tokens.push({type:'false',value:false});i+=5;continue;}
    if(str.substring(i,i+4)==='null'){tokens.push({type:'null',value:null});i+=4;continue;}
    if(c==='-'||(c>='0'&&c<='9')){
      var start=i;
      if(str[i]==='-')i++;
      while(i<str.length&&str[i]>='0'&&str[i]<='9')i++;
      if(str[i]==='.'){i++;while(i<str.length&&str[i]>='0'&&str[i]<='9')i++;}
      if(str[i]==='e'||str[i]==='E'){i++;if(str[i]==='+'||str[i]==='-')i++;while(i<str.length&&str[i]>='0'&&str[i]<='9')i++;}
      tokens.push({type:'number',raw:str.substring(start,i)});
      continue;
    }
    throw new Error('Unexpected character '+c+' at '+i);
  }
  return tokens;
}
function parseJSONPreserveNumbers(text){
  var tokens=tokenizeJSON(text),pos=0;
  function parseValue(){
    var tok=tokens[pos];
    if(tok.type==='number'){pos++;return{__num:tok.raw};}
    if(tok.type==='string'){pos++;return tok.value;}
    if(tok.type==='true'||tok.type==='false'||tok.type==='null'){pos++;return tok.value;}
    if(tok.type==='[')return parseArray();
    if(tok.type==='{')return parseObject();
    throw new Error('Unexpected token '+tok.type);
  }
  function parseArray(){
    pos++;
    var arr=[];
    if(tokens[pos]&&tokens[pos].type===']'){pos++;return arr;}
    while(true){
      arr.push(parseValue());
      var tok=tokens[pos++];
      if(tok.type===',')continue;
      if(tok.type===']')return arr;
      throw new Error('Expected , or ] got '+tok.type);
    }
  }
  function parseObject(){
    pos++;
    var obj={};
    if(tokens[pos]&&tokens[pos].type==='}'){pos++;return obj;}
    while(true){
      var keyTok=tokens[pos++];
      if(keyTok.type!=='string')throw new Error('Expected string key');
      var key=keyTok.value;
      if(tokens[pos++].type!==':')throw new Error('Expected :');
      obj[key]=parseValue();
      var tok=tokens[pos++];
      if(tok.type===',')continue;
      if(tok.type==='}')return obj;
      throw new Error('Expected , or } got '+tok.type);
    }
  }
  var val=parseValue();
  if(pos!==tokens.length)throw new Error('Unexpected trailing tokens');
  return val;
}
function sortedJSON(obj,numFmt){
  var fmt=numFmt||jcsNumberFromRaw;
  if(obj && typeof obj==='object' && obj.__num!==undefined)return fmt(obj.__num);
  if(obj===null)return'null';
  if(typeof obj==='string')return JSON.stringify(obj);
  if(typeof obj==='number')return String(Number.isFinite(obj)?obj:'null');
  if(typeof obj==='boolean')return String(obj);
  if(Array.isArray(obj))return'['+obj.map(function(v){return sortedJSON(v,fmt)}).join(',')+']';
  var keys=Object.keys(obj).sort(),p=[];
  for(var i=0;i<keys.length;i++){var k=keys[i];if(obj[k]!==undefined)p.push(JSON.stringify(k)+':'+sortedJSON(obj[k],fmt));}
  return'{'+p.join(',')+'}';
}
// JCS number encoding from raw JSON number text (matches Python rfc8785).
function jcsNumberFromRaw(raw){
  if(/^-?(0|[1-9][0-9]*)$/.test(raw))return raw;
  var n=Number(raw);
  if(!isFinite(n))return'null';
  return String(n);
}
// Python-legacy number encoding (json.dumps sort_keys, for pre-JCS specs):
// ints byte-exact from raw text; floats via Python float-repr layout
// (89.0 stays "89.0"; exponents switch at the same magnitudes as repr).
function legacyNumberFromRaw(raw){
  if(/^-?(0|[1-9][0-9]*)$/.test(raw))return raw==='-0'?'0':raw;
  var n=Number(raw);
  if(!isFinite(n))return'null';
  var neg=n<0||(n===0&&1/n===-Infinity);
  var a=Math.abs(n);
  if(a===0)return neg?'-0.0':'0.0';
  var parts=a.toExponential().split('e');
  var digits=parts[0].replace('.','').replace(/0+$/,'')||'0';
  var decpt=parseInt(parts[1],10)+1;
  var sign=neg?'-':'';
  var out;
  if(decpt<=-4||decpt>16){
    var exp=decpt-1;
    var expStr=(exp<0?'-':'+')+('0'+Math.abs(exp)).slice(-2);
    out=sign+digits.charAt(0)+(digits.length>1?'.'+digits.slice(1):'')+'e'+expStr;
  }else if(decpt<=0){
    out=sign+'0.';for(var i=0;i<-decpt;i++)out+='0';out+=digits;
  }else if(decpt>=digits.length){
    out=sign+digits;for(var j=0;j<decpt-digits.length;j++)out+='0';out+='.0';
  }else{
    out=sign+digits.slice(0,decpt)+'.'+digits.slice(decpt);
  }
  return out;
}
// True when the artifact predates JCS canonicalization (mirrors
// epi_core.serialize.canonical_format_for and epi-verify-core isPreJcsSpec:
// anything below 4.4.1 hashes steps the legacy way).
function isPreJcsSpecLocal(sv){
  var s=String(sv||'').replace(/^v/i,'');
  var a=s.split(/[^\d]+/).map(function(x){return parseInt(x,10)||0;});
  var maj=a[0]||0,min=a[1]||0,pat=a[2]||0;
  if(maj!==4)return maj<4&&maj>1?true:false;
  if(min!==4)return min<4;
  return pat<1;
}
// ISO-8601 -> UTC Z form (matches Python serialize.normalize_value).
function epiUtcZ(s){
  if(typeof s!=='string')return s;
  var m=/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:?\d{2})?$/.exec(s);
  if(!m||!m[8])return s;
  var ms=Date.UTC(+m[1],+m[2]-1,+m[3],+m[4],+m[5],+m[6]);
  var off=m[8];
  if(off!=='Z'){
    var sign=off[0]==='+'?1:-1;
    var parts=off.slice(1).split(':');
    ms-=((parseInt(parts[0],10)*60)+parseInt(parts[1]||'0',10))*sign*60000;
  }
  var d=new Date(ms);
  function p(n){return(n<10?'0':'')+n;}
  return d.getUTCFullYear()+'-'+p(d.getUTCMonth()+1)+'-'+p(d.getUTCDate())+'T'+p(d.getUTCHours())+':'+p(d.getUTCMinutes())+':'+p(d.getUTCSeconds())+'Z';
}
function normalizeCreatedAt(manifest){
  (function walk(o){
    if(!o||typeof o!=='object'||o.__num!==undefined)return;
    if(Array.isArray(o)){for(var i=0;i<o.length;i++){if(typeof o[i]==='string')o[i]=epiUtcZ(o[i]);else walk(o[i]);}return;}
    for(var k in o){if(typeof o[k]==='string')o[k]=epiUtcZ(o[k]);else walk(o[k]);}
  })(manifest);
  return manifest;
}
function computeManifestHash(rawManifestText){
  if(typeof globalThis.epiComputeManifestHash!=='function'){
    throw new Error('epi-manifest-preimage.js failed to load');
  }
  return globalThis.epiComputeManifestHash(rawManifestText);
}

async function canonicalStepHash(step,specVersion){
  // Matches epi_core.serialize.hash_normalized_dict(model_dict_for_hash(step)):
  // sort keys, no whitespace, exclude source_type, and normalize only the
  // top-level datetime field (timestamp) the way Pydantic model_dump does.
  // Pre-JCS specs (< 4.4.1) hash the legacy way (Python json sort_keys).
  var fields=['index','timestamp','kind','content','trace_id','span_id','parent_span_id','prev_hash','governance'];
  var canonical={};
  for(var i=0;i<fields.length;i++){
    var k=fields[i];
    var v=step[k]!==undefined?step[k]:null;
    if(k==='timestamp'&&typeof v==='string')v=epiUtcZ(v);
    canonical[k]=v;
  }
  var legacy=isPreJcsSpecLocal(specVersion);
  return sha256(new TextEncoder().encode(sortedJSON(canonical,legacy?legacyNumberFromRaw:jcsNumberFromRaw)));
}

function unwrapNum(v){
  return (v && typeof v==='object' && v.__num!==undefined)?Number(v.__num):v;
}
function auditStepSequence(steps){
  if(!steps||steps.length===0)return true;
  var indices=steps.map(function(s){var n=unwrapNum(s.index);return n!==undefined?n:0});
  if(indices[0]!==0)return false; // truncated prefix is monotonic but incomplete
  for(var i=1;i<indices.length;i++){
    if(indices[i]!==indices[i-1]+1)return false;
  }
  var times=steps.map(function(s){
    var t_ns=unwrapNum((s.content||{}).timestamp_ns);
    return t_ns!==undefined?t_ns:(s.timestamp||'');
  });
  for(var i=1;i<times.length;i++){
    if(times[i]<times[i-1])return false;
  }
  return true;
}

function auditStepCompleteness(steps){
  var pendingToolCalls=[];
  var pendingLlmRequests=[];
  var pendingApprovals=[];
  for(var i=0;i<steps.length;i++){
    var s=steps[i];
    var kind=s.kind||'';
    var content=s.content||{};
    var idx=s.index!==undefined?s.index:0;
    var span_id=s.span_id;
    if(kind==='tool.call'){
      pendingToolCalls.push({idx:idx,call_id:content.call_id});
    }else if(kind==='tool.response'){
      var call_id=content.call_id;
      var matched=false;
      if(call_id!==undefined&&call_id!==null){
        for(var ti=pendingToolCalls.length-1;ti>=0;ti--){
          if(pendingToolCalls[ti].call_id===call_id){
            pendingToolCalls.splice(ti,1);
            matched=true;
            break;
          }
        }
      }
      if(!matched&&pendingToolCalls.length>0)pendingToolCalls.shift();
    }else if(kind==='llm.request'){
      pendingLlmRequests.push({idx:idx,span_id:span_id});
    }else if(kind==='llm.response'||kind==='llm.error'){
      var matched=false;
      if(span_id!==undefined&&span_id!==null){
        for(var li=pendingLlmRequests.length-1;li>=0;li--){
          if(pendingLlmRequests[li].span_id===span_id){
            pendingLlmRequests.splice(li,1);
            matched=true;
            break;
          }
        }
      }
      if(!matched&&pendingLlmRequests.length>0)pendingLlmRequests.shift();
    }else if(kind==='agent.approval.request'){
      pendingApprovals.push({idx:idx,action:content.action});
    }else if(kind==='agent.approval.response'){
      var action=content.action;
      var matched=false;
      if(action!==undefined&&action!==null){
        for(var ai=pendingApprovals.length-1;ai>=0;ai--){
          if(pendingApprovals[ai].action===action){
            pendingApprovals.splice(ai,1);
            matched=true;
            break;
          }
        }
      }
      if(!matched&&pendingApprovals.length>0)pendingApprovals.shift();
    }
  }
  return pendingToolCalls.length===0&&pendingLlmRequests.length===0&&pendingApprovals.length===0;
}

async function auditStepChain(steps,specVersion){
  if(!steps||steps.length===0)return true;
  var first=unwrapNum(steps[0].prev_hash);
  if(first!==null&&first!==undefined&&first!=='CHAIN_START')return false;
  if(steps.length===1)return true;
  var anyLink=false;
  for(var j=1;j<steps.length;j++){var h=unwrapNum(steps[j].prev_hash);if(h!==null&&h!==undefined&&h!=='CHAIN_START'){anyLink=true;break;}}
  if(!anyLink)return true; // pre-chain artifact: nothing verifiable
  for(var i=1;i<steps.length;i++){
    // Genesis marker mid-chain means restart (possible truncation)
    var claimed=unwrapNum(steps[i].prev_hash);
    if(claimed===null||claimed===undefined||claimed==='CHAIN_START')return false;
    var expected=await canonicalStepHash(steps[i-1],specVersion);
    if(claimed!==expected)return false;
  }
  return true;
}

function auditStepCount(steps,manifest){
  var total=unwrapNum(manifest.total_steps);
  if(total===undefined||total===null)return true;
  return steps.length===total;
}

async function auditSteps(steps,manifest){
  var seq=auditStepSequence(steps);
  var comp=auditStepCompleteness(steps);
  var chain=await auditStepChain(steps,manifest&&manifest.spec_version);
  var count=auditStepCount(steps,manifest);
  return{sequence_ok:seq,completeness_ok:comp,chain_ok:chain,step_count_ok:count};
}

// ── Signed approvals (review ledger, 1.2.0) ─────────────────────────────────
// What the browser CAN check offline: the record's canonical hash, its Ed25519
// signature, and that its artifact_binding is this file. It cannot check the
// approver registry — that is `epi verify --require-human-approval`.
async function reviewContentHash(record){
  var payload={};
  for(var k in record){if(k==='review_hash'||k==='review_signature')continue;payload[k]=record[k];}
  return sha256(new TextEncoder().encode(sortedJSON(payload)));
}

async function computeArtifactBinding(zip,manifest,rawManifestBytes,containerFmt){
  var fileManifest=manifest.file_manifest||{},names=Object.keys(fileManifest).sort(),entries=[];
  for(var i=0;i<names.length;i++){
    var name=names[i],entry=zip.file(name),digest='__missing__';
    if(entry){try{digest=await sha256(await entry.async('uint8array'))}catch(e){digest='__missing__'}}
    entries.push({path:name,sha256:digest});
  }
  return {
    binding_version:'1.0.0',
    binding_type:'epi_artifact',
    workflow_id:String(manifest.workflow_id),
    manifest_sha256:await sha256(rawManifestBytes),
    manifest_signature:manifest.signature===undefined?null:manifest.signature,
    manifest_public_key:manifest.public_key===undefined?null:manifest.public_key,
    sealed_evidence_sha256:await sha256(new TextEncoder().encode(sortedJSON({files:entries}))),
    container_format:containerFmt
  };
}

async function verifyApprovalRecords(zip,manifest,rawManifestBytes,containerFmt){
  var out=[];
  var names=Object.keys(zip.files).filter(function(n){return n.indexOf('reviews/')===0&&/\.json$/.test(n)});
  if(!names.length&&zip.file('review.json'))names=['review.json'];
  var expected=null;
  for(var i=0;i<names.length;i++){
    var raw,rec;
    try{raw=await zip.file(names[i]).async('string');rec=parseJSONPreserveNumbers(raw)}catch(e){continue}
    var entries=Array.isArray(rec.reviews)?rec.reviews:[];
    if(entries.length!==1||!entries[0]||entries[0].entry_type!=='approval')continue;
    var entry=entries[0];
    var claimed=entry.approver&&typeof entry.approver==='object'?String(entry.approver.name||''):'';
    var res={
      approval_id:entry.approval_id?String(entry.approval_id):null,
      case_level:entry.case_level===true,
      decision:entry.decision==='deny'?'deny':'approve',
      claimed_name:claimed,
      status:'invalid',
      fingerprint:null
    };
    try{
      if(!expected)expected=await computeArtifactBinding(zip,manifest,rawManifestBytes,containerFmt);
      var expectedHash=await reviewContentHash(rec);
      if(String(rec.review_hash||'')!==expectedHash)throw new Error('hash');
      var sig=String(rec.review_signature||'').split(':');
      if(sig.length!==3||sig[0]!=='ed25519'||sig[1].length!==64||sig[2].length!==128)throw new Error('sig');
      if(!await verifyEd25519Raw(sig[1],sig[2],hexToBytes(expectedHash)))throw new Error('sig');
      if(sortedJSON(rec.artifact_binding||null)!==sortedJSON(expected))throw new Error('binding');
      res.key=sig[1];
      res.fingerprint=await keyFingerprintHex(sig[1]);
      res.status=(manifest.public_key&&String(sig[1]).toLowerCase()===String(manifest.public_key).toLowerCase())
        ?'sealing_key':'valid';
    }catch(e){res.status='invalid'}
    out.push(res);
  }
  return out;
}

async function processFile(f){
  var nm=(f&&f.name?f.name:'').toLowerCase();
  lastFile=f||lastFile;
  if(f&&f.size>25*1024*1024){showResult('fail','<strong>This file is too large to check in the browser</strong><br>Files over 25 MB cannot be checked here — use <code style="font-size:0.75em">epi verify</code> on your own machine.');return}
  showResult('warn','<em>Reading '+esc(f.name||'file')+'...</em>');

  try{
    if(typeof JSZip==='undefined'){
      showResult('fail','<strong>Verifier not loaded</strong><br>JSZip missing — hard-refresh (Ctrl+Shift+R) and try again.');
      return;
    }
    var buf=await f.arrayBuffer();
    if(!buf||buf.byteLength<4){
      showResult('fail','<strong>This isn\'t an EPI evidence file</strong><br>The file is empty or too small to be a sealed .epi ('+(buf?buf.byteLength:0)+' bytes).');
      return;
    }
    var u8=toU8(buf);
    var containerFmt=detectContainer(u8);
    // Prefer magic-byte detection over file extension (pickers / email renames)
    if(!containerFmt){
      var kind=sniffFileKind(u8);
      var hint='';
      if(kind)hint=' It looks like '+kind+' — drop the sealed .epi file, not a document or image.';
      else if(u8[0]===0x3c&&u8[1]===0x21&&u8[2]===0x44)hint=' This looks like an HTML page (broken download), not a sealed .epi.';
      else if(nm&&!nm.endsWith('.epi')&&!nm.endsWith('.zip'))hint=' Expected a .epi file.';
      showResult('fail','<strong>This isn\'t an EPI evidence file</strong><br>No EPI envelope or ZIP header detected.'+hint);
      return;
    }

    // Check 1b: outer polyglot viewer HTML (reserved_tail[0:32]). A byte
    // flipped in the display layer fails exactly like the CLI.
    var viewerNote=null;
    if(containerFmt==='envelope-v2'){
      var vw=await verifyPolyglotViewer(u8);
      if(vw.fail){
        // Still show what the file claims (labelled as possibly forged), so a
        // reviewer sees what was altered; the verdict stays a red fail.
        var claims='';
        try{
          var tz=await JSZip.loadAsync(extractZIPPayload(u8,containerFmt));
          var tm=tz.file('manifest.json')?parseJSONPreserveNumbers(await tz.file('manifest.json').async('string')):{};
          var ts=[],tf=tz.file('steps.jsonl');
          if(tf){(await tf.async('string')).split('\n').forEach(function(l){l=l.trim();if(l){try{ts.push(parseJSONPreserveNumbers(l))}catch(e){}}})}
          claims=storyHTML(buildStory(ts,tm),true);
        }catch(e){claims=''}
        showResult('fail','<strong>This file was changed after it was sealed. Don\'t rely on it.</strong><br><span style="font-size:0.68rem;opacity:.85">'+esc(vw.detail)+'</span>'+claims);return}
      viewerNote=vw.note;
    }

    var zipBuf;
    try{zipBuf=extractZIPPayload(u8,containerFmt)}
    catch(ex){showResult('fail','<strong>Could not locate ZIP payload</strong><br>'+esc(ex.message));return}
    var zip;
    try{zip=await JSZip.loadAsync(zipBuf)}catch(e){showResult('fail','<strong>ZIP extraction failed</strong><br>'+esc(e.message)+' (container: '+containerFmt+')');return}

    var report={facts:{structure_ok:false,integrity_ok:false,signature_valid:null,has_signature:false,mismatches:{},chain_ok:true,sequence_ok:true,completeness_ok:true,transparency_ok:null},identity:{status:'UNKNOWN',name:null,detail:null,registry_verified:false,public_key_id:null},metadata:{spec_version:'?',workflow_id:'?',created_at:'?',files_checked:0,verifier_version:'browser',steps_count:null},trust_level:'NONE',trust_message:''};

    // Check 1: mimetype
    if(!zip.file('mimetype')){report.facts.structure_ok=false;showReport(report,'<strong>This isn\'t an EPI evidence file</strong><br><span style="font-size:0.68rem;opacity:.85">This archive has no mimetype file.</span>');return}
    var mt=await zip.file('mimetype').async('string');
    var mtNorm=mt.trim().replace(/\r/g,'');
    if(mtNorm!==EPI_MIMETYPE&&mtNorm!=='application/vnd.epi'&&mtNorm!=='application/vnd.epi+zip'){
      report.facts.structure_ok=false;showReport(report,'Invalid mimetype: '+esc(mtNorm));return
    }
    report.facts.structure_ok=true;

    // Check 2: manifest.json
    var mf=zip.file('manifest.json');
    if(!mf){showResult('fail','<strong>No manifest.json found</strong>');return}
    var rawManifest;
    try{rawManifest=await mf.async('string')}catch(e){showResult('fail','<strong>Could not read manifest.json</strong><br>'+esc(e.message));return}
    var manifest;
    try{manifest=parseJSONPreserveNumbers(rawManifest)}catch(e){showResult('fail','<strong>manifest.json parse error</strong><br>'+esc(e.message));return}
    if(!manifest||typeof manifest!=='object'||Array.isArray(manifest)){showResult('fail','<strong>Invalid manifest</strong><br>manifest.json is not a JSON object.');return}
    report.metadata.spec_version=manifest.spec_version||'?';
    report.metadata.workflow_id=manifest.workflow_id||'?';
    report.metadata.created_at=manifest.created_at||'?';

    // Check 3: steps.jsonl — parse and count steps
    var steps=[],stepsFile=zip.file('steps.jsonl');
    if(stepsFile){
      var st=await stepsFile.async('string');
      var lines=st.split('\n');
      for(var si=0;si<lines.length;si++){
        var line=lines[si].trim();
        if(!line)continue;
        try{steps.push(parseJSONPreserveNumbers(line))}catch(e){}
      }
    }
    report.metadata.steps_count=steps.length;
    report.story=buildStory(steps,manifest);
    var manifestHashForWitness=null;
    try{manifestHashForWitness=await computeManifestHash(rawManifest);}catch(e){}
    try{
      var rawManifestBytes=await mf.async('uint8array');
      report.story.approvals=await verifyApprovalRecords(zip,manifest,rawManifestBytes,containerFmt);
    }catch(e){report.story.approvals=[]}

    // Check 4: file_manifest integrity
    var fileManifest=manifest.file_manifest||{},mismatches={},checked=0;
    var manifestFiles=Object.keys(fileManifest);
    for(var j=0;j<manifestFiles.length;j++){
      var fname=manifestFiles[j],expected=fileManifest[fname],entry=zip.file(fname);
      if(!entry){mismatches[fname]='File missing from archive';continue}
      var data=await entry.async('uint8array'),actualHash=await sha256(data);
      checked++;
      if(actualHash!==expected){mismatches[fname]='Hash mismatch: expected '+expected.substring(0,12)+'... got '+actualHash.substring(0,12)+'...'}
    }
    // Check for extra unlisted files (not mimetype/manifest/viewer/review/artifacts)
    // review_timestamps/ is added by `epi review approve` AFTER sealing (the RFC 3161
    // token for that approval). reviews/ and review.json are the same kind of
    // post-seal addition; leaving the timestamps out told every approved file it
    // had been tampered with.
    var excludePrefixes=['mimetype','manifest.json','viewer.html','VERIFY.txt','review.json','review_index.json','reviews/','review_timestamps/','artifacts/scitt/'];
    Object.keys(zip.files).forEach(function(nm){
      var excluded=false;
      for(var k=0;k<excludePrefixes.length;k++){if(nm.indexOf(excludePrefixes[k])===0){excluded=true;break}}
      if(!excluded&&!fileManifest[nm])mismatches[nm]='Extra file not in manifest';
    });
    report.metadata.files_checked=checked;
    report.facts.mismatches=mismatches;
    if(viewerNote)report.facts.viewer_note=viewerNote;

    // Check 5: forensic audits on the step timeline
    var forensic=await auditSteps(steps,manifest);
    report.facts.sequence_ok=forensic.sequence_ok;
    report.facts.completeness_ok=forensic.completeness_ok;
    report.facts.chain_ok=forensic.chain_ok;
    report.facts.step_count_ok=forensic.step_count_ok;
    // File-hash integrity only (matches Python). Completeness gaps are not a broken seal.
    // Zero files checked is not a pass: an empty file_manifest proves nothing.
    var hashesOk=Object.keys(mismatches).length===0&&checked>0;
    if(checked===0)mismatches['(no files listed)']='Manifest lists no files to check';
    if(manifest.content_truncated===true)hashesOk=false;
    report.facts.integrity_ok=hashesOk;
    report.facts.content_truncated=manifest.content_truncated===undefined?null:manifest.content_truncated;

    // Check 6: Signature + key-name binding + trust registry
    var registry=null;
    try{registry=await (await fetch('/.well-known/epi-trust-registry.json')).json();}catch(e){}
    report.facts.has_signature=!!manifest.signature;
    if(manifest.signature&&manifest.public_key){
      try{
        // Compute canonical hash matching Python's get_canonical_hash
        var manifestHash=await computeManifestHash(rawManifest);
        var sigResult=await verifyEd25519(manifest.signature,manifest.public_key,manifestHash);
        report.facts.signature_valid=sigResult.valid;
        report.identity.public_key_id=manifest.public_key.substring(0,16);
        var nameParts=manifest.signature.split(':',2);
        if(nameParts.length>=2)report.identity.name=esc(nameParts[1]);
        if(sigResult.valid===true){
          if(registry&&registry.trusted_keys&&registry.trusted_keys[manifest.public_key]){
            // Same rule as WP-SEC-4: a public list is informational only. The
            // visitor never pinned this key, so it must not read as pinned.
            report.identity.status='UNKNOWN';
            report.identity.name=esc(registry.trusted_keys[manifest.public_key]);
            report.identity.detail='Listed in EPI Labs public registry (informational; not a pin) — pin the key yourself before trusting it';
            report.identity.registry_verified=false;
          }else{
            report.identity.status='UNKNOWN';
            report.identity.detail='Valid signature from unverified identity — verify signer independently';
          }
        }else{
          report.identity.status='UNKNOWN';
          report.identity.detail=sigResult.msg||'Signature could not be verified';
        }
      }catch(e){report.facts.signature_valid=null;report.identity.detail='WebCrypto not available: '+e.message}
    }else if(!manifest.signature){report.facts.signature_valid=null;report.identity.detail='Artifact is unsigned'}

    // Trust level: green HIGH only when identity pinned. Valid unpinned seal is
    // LOW (amber) — never a pass-level label (skim must not imply claim safety).
    if(report.facts.integrity_ok&&report.facts.signature_valid===true&&report.identity.status==='KNOWN'){report.trust_level='HIGH';report.trust_message='Seal valid · identity pinned (org trust list)'}
    else if(report.facts.integrity_ok&&report.facts.signature_valid===true&&report.identity.status!=='KNOWN'){report.trust_level='LOW';report.trust_message='Seal valid · identity not pinned — not claim-ready. Anyone can re-sign a rebuilt chain. CLI: epi keys trust + epi verify --policy strict'}
    else if(report.facts.integrity_ok&&!report.facts.has_signature){report.trust_level='LOW';report.trust_message='Integrity intact · no signature — anyone could have produced this file'}
    else if(!report.facts.integrity_ok){report.trust_level='NONE';report.trust_message='Integrity compromised — do not trust this copy'}
    else if(report.facts.signature_valid===false){report.trust_level='NONE';report.trust_message='Signature invalid — artifact may be tampered'}
    else{report.trust_level='NONE';report.trust_message='Verification incomplete in browser — not verified, use epi verify --policy strict offline for claim audit'}

    try{report.witness=await witnessForFile(manifest,manifestHashForWitness,u8);}catch(e){report.witness={status:'NOT CHECKED'}}
    showReport(report,'');
  }catch(e){showResult('fail','<strong>Verification error</strong><br>'+esc(e.message))}
}


/* ── CUSTOMER WITNESS LOG ──────────────────────────────────────────────────
   Drop the log YOUR receiver wrote (received.jsonl) next to the .epi. The
   file itself proves it was not edited; the log proves the vendor reported
   THIS case. A re-sealed forgery is a valid file - only the log catches it.
   Matching mirrors epi_cli/verify.py: exact bytes/manifest hash, then the
   content digest (a repacked file keeps it), then the case (goal). */
var wz=document.getElementById('witnessZoneEl'),wi=document.getElementById('witnessInput'),ws=document.getElementById('witnessStatus');
var witnessLog=null,lastFile=null;

function parseWitnessLog(text){
  var reports=[],signed=false;
  var trimmed=String(text||'').trim();
  if(!trimmed)return{reports:[],signed:false,error:'the log is empty'};
  var doc=null;
  try{doc=JSON.parse(trimmed)}catch(e){}
  var items=[];
  if(doc&&typeof doc==='object'&&Array.isArray(doc.lines)){items=doc.lines}
  else{trimmed.split('\n').forEach(function(line){line=line.trim();if(!line)return;try{items.push(JSON.parse(line))}catch(e){}})}
  items.forEach(function(item){
    if(!item||typeof item!=='object')return;
    if(typeof item.payload_raw==='string'&&item.receipt&&typeof item.receipt==='object'){
      signed=true;
      var inner=null;try{inner=JSON.parse(item.payload_raw)}catch(e){}
      if(!inner||typeof inner!=='object')return;
      inner.received_at=inner.received_at||(item.receipt&&item.receipt.received_at)||item.received_at||null;
      reports.push(inner);
      return;
    }
    if(item.workflow_id)reports.push(item);
  });
  return{reports:reports,signed:signed,error:reports.length?'':'no witness reports in that file'};
}

// Same digest as epi_core.webhook.witness_content_digest: the manifest minus
// the signature, presentation fields and post-seal transparency additions.
async function witnessContentDigest(manifest){
  try{
    var data=JSON.parse(JSON.stringify(manifest));
    delete data.signature;delete data.viewer_version;
    if(data.governance&&typeof data.governance==='object'){
      delete data.governance.scitt;delete data.governance.transparency;
      if(!Object.keys(data.governance).length)data.governance=null;
    }
    if(data.file_manifest&&typeof data.file_manifest==='object'){
      var keep={};
      Object.keys(data.file_manifest).forEach(function(k){
        if(k.indexOf('artifacts/scitt/')===0||k.indexOf('artifacts/transparency/')===0)return;
        if(k==='viewer.html'||k==='VERIFY.txt')return;
        keep[k]=data.file_manifest[k];
      });
      data.file_manifest=keep;
    }
    var text=typeof globalThis.epiSortedJSON==='function'
      ?globalThis.epiSortedJSON(data)
      :sortedJSON(data,jcsNumberFromRaw);
    return await sha256(new TextEncoder().encode(text));
  }catch(e){return null}
}

function witnessVerdict(manifest,manifestHash,fileSha,contentDigest,log){
  var goal=String((manifest&&manifest.goal)||'').trim();
  var wf=String((manifest&&manifest.workflow_id)||'');
  var sameId=[],sameCase=[];
  (log.reports||[]).forEach(function(r){
    if(wf&&String(r.workflow_id||'')===wf)sameId.push(r);
    if(goal&&String(r.goal||'').trim()===goal)sameCase.push(r);
  });
  function exact(r){
    if(manifestHash&&String(r.manifest_hash||'')===manifestHash)return true;
    if(fileSha&&String(r.file_sha256||'')===fileSha)return true;
    if(contentDigest&&String(r.content_digest||'')===contentDigest)return true;
    return false;
  }
  function latest(list){
    var t='';
    list.forEach(function(r){var v=String(r.received_at||'');if(v>t)t=v});
    return t||null;
  }
  if(log.signed){
    // Fail closed, exactly like the CLI: a receipt signs a key we have not
    // pinned here, so this page cannot call the stamp verified.
    return{status:'NOT CONFIRMED',reports:sameId.length,
      detail:'this log carries signed witness receipts; pin the witness key to check them (epi verify --witness-pubkey)'};
  }
  var hit=sameId.filter(exact)[0]||(log.reports||[]).filter(exact)[0];
  if(hit){
    return{status:'WITNESSED',reports:(log.reports||[]).length,received_at:hit.received_at||latest(sameId),
      detail:'your own log (unsigned) records this case; the bytes you were handed match what was reported'};
  }
  if(sameId.length){
    return{status:'MISMATCH',reports:sameId.length,received_at:latest(sameId),
      detail:'a different version of this case was reported to you ('+sameId.length+' report(s), latest '+(latest(sameId)||'unknown time')+'); this copy was never reported'};
  }
  if(sameCase.length){
    return{status:'MISMATCH',reports:sameCase.length,received_at:latest(sameCase),
      detail:'a different version of "'+goal+'" was reported to you ('+sameCase.length+' report(s), latest '+(latest(sameCase)||'unknown time')+'); this copy was never reported'};
  }
  return{status:'NOT IN WITNESS LOG',reports:(log.reports||[]).length,received_at:null,
    detail:'this file was never reported to the customer; a missing entry for a case you know happened is itself evidence'};
}

function setWitnessStatus(html,kind){
  if(!ws)return;
  var colors={ok:'var(--verified)',warn:'var(--warn)',bad:'var(--tamper)',dim:'var(--ink-dim)'};
  ws.style.display='block';
  ws.style.color=colors[kind]||colors.dim;
  ws.innerHTML=html; // static-html: callers pass fixed text + escaped file names
}

async function loadWitnessFile(f){
  if(!f)return;
  try{
    var text=await f.text();
    var parsed=parseWitnessLog(text);
    if(parsed.error){
      witnessLog=null;
      setWitnessStatus('<strong>'+esc(parsed.error)+'</strong><br>Drop the <code>received.jsonl</code> your own <code>epi witness serve</code> wrote.','bad');
      return;
    }
    witnessLog=parsed;
    witnessLog.name=f.name||'received.jsonl';
    setWitnessStatus('<strong>WITNESS LOG LOADED</strong> — '+parsed.reports.length+' report(s) from '+esc(witnessLog.name)+(parsed.signed?' (signed receipts)':' (unsigned, your own record)'),'ok');
    if(lastFile)processFile(lastFile);
  }catch(e){
    setWitnessStatus('<strong>Could not read that log</strong><br>'+esc(e.message),'bad');
  }
}

async function witnessForFile(manifest,manifestHash,u8){
  if(!witnessLog)return{status:'NOT CHECKED'};
  var fileSha=null,contentDigest=null;
  try{fileSha=await sha256(u8)}catch(e){}
  contentDigest=await witnessContentDigest(manifest);
  return witnessVerdict(manifest,manifestHash,fileSha,contentDigest,witnessLog);
}

function setDropSealState(type){
  if(!dz)return;
  dz.classList.remove('seal-ok','seal-fail','seal-warn');
  if(type==='pass')dz.classList.add('seal-ok');
  else if(type==='fail')dz.classList.add('seal-fail');
  else if(type==='warn')dz.classList.add('seal-warn');
}

function showResult(type,msg){
  var colors={pass:['var(--verified-bg)','var(--verified)','var(--verified)'],warn:['var(--warn-bg)','var(--warn)','var(--warn)'],fail:['var(--tamper-bg)','var(--tamper)','var(--tamper)']};
  var c=colors[type]||colors.fail;
  dr.style.display='block';dr.style.background=c[0];dr.style.border='1px solid '+c[1];dr.style.color=c[2];dr.innerHTML=msg; // esc-built-html: msg HTML built by audited call sites above; every dynamic part escaped with esc()
  if(type==='pass'||type==='fail'||type==='warn')setDropSealState(type);
  else setDropSealState(null);
}

// What the AI did, read from the sealed steps: goal, the human review, the
// final decision and a short timeline. Same verdict words as the offline
// viewer (web_viewer/app.js renderVerdict). Data only — storyHTML escapes it.
function normalizeVerdict(raw){
  var d=String(raw||'').toUpperCase();
  if(!d)return'';
  var yes=['APPROVED','APPROVE','PASS','PASSED','ACCEPT','ACCEPTED'];
  var no=['REJECTED','REJECT','DENY','DENIED','FAIL','FAILED','DECLINE','DECLINED','BLOCKED'];
  var negated=['DIS','UN','NON','DE'].some(function(p){return d.indexOf(p)===0});
  var isYes=yes.some(function(v){return d.indexOf(v)>=0});
  var isNo=no.some(function(v){return d.indexOf(v)>=0});
  if(isYes&&!negated)return'APPROVED';
  if(isNo||(isYes&&negated))return'REJECTED';
  return d.replace(/_/g,' ');
}

function stepLine(s){
  var k=String(s&&s.kind||''),c=(s&&s.content&&typeof s.content==='object')?s.content:{};
  var tool=c.tool||c.tool_name||c.name||'';
  switch(k){
    case'session.start':return'Run started'+(c.workflow_name?': '+c.workflow_name:'');
    case'session.end':return'Run ended';
    case'agent.run.start':return'Agent '+(c.agent_name||'')+' started';
    case'agent.run.end':return'Agent '+(c.agent_name||'')+' finished';
    case'tool.call':return'Called tool'+(tool?' '+tool:'');
    case'tool.response':return'Tool'+(tool?' '+tool:'')+' answered'+(c.ok===false?' with an error':'');
    case'llm.request':return'Asked AI model'+(c.model?' '+c.model:'');
    case'llm.response':return'AI model'+(c.model?' '+c.model:'')+' answered';
    case'model.inference':return'AI model'+(c.model?' '+c.model:'')+' planned'+(c.plan?': '+c.plan:'');
    case'policy.check':return'Rule check'+(c.rule_name?' "'+c.rule_name+'"':'')+(c.status||c.policy_decision?': '+(c.status||c.policy_decision):'');
    case'agent.approval.request':return'Asked a human to approve'+(c.action?' '+c.action:'')+(c.reason?': '+c.reason:'');
    case'agent.approval.response':return approvalStepLine(c);
    case'agent.decision':return'Decision: '+normalizeVerdict(c.decision||c.verdict||c.outcome)+(c.rationale||c.reason?' — '+(c.rationale||c.reason):'');
    case'security.redaction':return'Hid '+(c.count||'some')+' secret value(s) before sealing';
    case'environment.captured':return'';
    default:return k?k.replace(/[._]/g,' '):'';
  }
}

function buildStory(steps,manifest){
  steps=Array.isArray(steps)?steps:[];
  var story={goal:manifest&&typeof manifest.goal==='string'?manifest.goal:'',workflow:'',verdict:'',rationale:'',review:null,lines:[],total:steps.length};
  for(var i=0;i<steps.length;i++){
    var s=steps[i]||{},k=s.kind||'',c=(s.content&&typeof s.content==='object')?s.content:{};
    if(k==='session.start'&&c.workflow_name&&!story.workflow)story.workflow=String(c.workflow_name);
    if(k==='agent.decision'){story.verdict=normalizeVerdict(c.decision||c.verdict||c.outcome);story.rationale=String(c.rationale||c.reason||'')}
    if(k==='policy.check'&&!story.verdict){
      var st=String(c.status||c.policy_decision||'').toLowerCase();
      if(st==='deny'||st==='blocked')story.verdict='REJECTED';
    }
    if(k==='agent.approval.response')story.review={approved:c.approved===true?true:c.approved===false?false:null,reviewer:String(c.reviewer||''),reason:String(c.reason||''),label:approvalStepLine(c)};
    var line=stepLine(s);
    if(line)story.lines.push(line);
  }
  return story;
}

function trunc(t,n){t=String(t||'');return t.length>n?t.slice(0,n-1)+'…':t}

// altered: the seal check failed, so everything here may be forged.
function storyHTML(story,altered){
  if(!story||!story.total)return'';
  var ink='color:var(--ink,inherit)';
  var head=altered
    ?'<div style="font-size:0.72rem;font-weight:600;color:var(--tamper)">WHAT THIS FILE CLAIMS — changed after sealing, may be forged</div>'
    :'<div style="font-size:0.72rem;font-weight:600;color:var(--ink-dim)">WHAT THE AI DID (as sealed)</div>';
  var h='<div style="margin:0.4rem 0 0.6rem;padding:0.6rem 0.7rem;border:1px solid var(--border);border-radius:6px;font-size:0.8rem;'+ink+'">'+head;
  var title=story.goal||story.workflow;
  if(title)h+='<div style="margin-top:0.35rem"><strong>Task:</strong> '+esc(trunc(title,240))+'</div>';
  if(story.verdict){
    // The decision comes from the run's own steps, so it is the agent's claim:
    // label it, and never paint it as a green approved badge.
    var vc=story.verdict==='REJECTED'?'var(--tamper)':'var(--ink,inherit)';
    h+='<div style="margin-top:0.35rem"><strong>Decision (agent-reported):</strong> <span style="font-weight:700;color:'+vc+'">'+esc(story.verdict)+'</span>'+(story.rationale?' — '+esc(trunc(story.rationale,240)):'')+'</div>';
  }
  if(story.review){
    var r=story.review;
    h+='<div style="margin-top:0.35rem"><strong>Approval (in-run step):</strong> '+esc(trunc(r.label||'Agent-reported',300))+'</div>';
  }
  var approvals=Array.isArray(story.approvals)?story.approvals:[];
  for(var ap=0;ap<approvals.length;ap++){
    var a=approvals[ap]||{};
    var what=a.case_level?'the whole run':(a.approval_id?('approval "'+a.approval_id+'"'):'an approval');
    var verb=a.decision==='deny'?'deny':'approve';
    var claimedName=a.claimed_name?' <span style="color:var(--ink-dim)">(claimed name: '+esc(a.claimed_name)+')</span>':'';
    if(a.status==='invalid'){
      h+='<div style="margin-top:0.35rem;color:var(--tamper)"><strong>Signed approval ('+esc(verb)+') for '+esc(what)+': approval signature does not verify for this file.</strong></div>';
    }else if(a.status==='sealing_key'){
      h+='<div style="margin-top:0.35rem"><strong>Not a human approval ('+esc(verb)+') for '+esc(what)+':</strong> signed by the same key that sealed the run (not independent of the agent).'+claimedName+'</div>';
    }else{
      // A valid signature this page cannot make green: it has no pinned
      // approver list, so it can only say the signer is not trusted HERE.
      var who=a.claimed_name||'an approver';
      var trust='epi approvers add '+String(a.key||'<their public key>')+" --name '"+who+"' --role approver --fingerprint '"+(a.fingerprint||'')+"'";
      h+='<div style="margin-top:0.35rem"><strong>SIGNED — APPROVER NOT TRUSTED HERE ('+esc(verb)+' '+esc(what)+').</strong> A signature verifies for the key with fingerprint '+esc(a.fingerprint||'')+'. This browser has no pinned approver list, so it cannot confirm that signer is trusted; it is not shown as approved here. To trust it: <code>'+esc(trust)+'</code> then run <code>epi verify --require-human-approval</code> on your machine.'+claimedName+'</div>';
    }
  }
  var shown=story.lines.slice(0,15);
  if(shown.length){
    h+='<details style="margin-top:0.45rem"><summary style="cursor:pointer;font-size:0.72rem;color:var(--ink-dim)">Steps ('+story.total+')</summary><ol style="margin:0.35rem 0 0 1.1rem;padding:0;font-size:0.74rem">';
    for(var i=0;i<shown.length;i++)h+='<li>'+esc(trunc(shown[i],200))+'</li>';
    if(story.lines.length>shown.length)h+='<li style="list-style:none;color:var(--ink-dim)">… '+(story.lines.length-shown.length)+' more — open with epi view for the full record</li>';
    h+='</ol></details>';
  }
  return h+'</div>';
}

// One plain sentence first; technical detail under a toggle. No jargon.

function witnessLineHTML(report){
  var w=report.witness||{};
  if(!w.status||w.status==='NOT CHECKED')return'';
  var colors={WITNESSED:'var(--verified)',MISMATCH:'var(--tamper)','NOT IN WITNESS LOG':'var(--warn)','NOT CONFIRMED':'var(--warn)'};
  var color=colors[w.status]||'var(--ink-dim)';
  var label=w.status==='WITNESSED'?'Witness: matches your log':('Witness: '+w.status);
  var when=w.received_at?(' <span style="color:var(--ink-dim)">(reported '+esc(String(w.received_at).slice(0,19).replace('T',' '))+' UTC)</span>'):'';
  return '<div style="margin-top:0.45rem;font-size:0.72rem;color:'+color+'"><strong>'+esc(label)+'</strong>'+when+'<br><span style="color:var(--ink-dim)">'+esc(w.detail||'')+'</span></div>';
}

function plainHeadline(report){
  var f=report.facts||{},w=report.witness||{};
  // The witness log is the only thing that can call a re-sealed forgery out,
  // so its verdict leads when the seal itself is intact.
  var sealOk=f.integrity_ok===true&&f.signature_valid!==false;
  if(sealOk&&w.status==='MISMATCH')return'This is not the version your witness recorded. Don\'t rely on it.';
  if(sealOk&&w.status==='NOT CONFIRMED')return'Your witness log carries signed receipts - pin the witness key to check them (epi verify --witness-pubkey).';
  if(sealOk&&w.status==='NOT IN WITNESS LOG')return'This file is not in your witness log - it was never reported to you.';
  if(report.trust_level==='LOW'&&f.signature_valid===true){
    return'This file hasn\'t been changed since it was sealed. We can\'t confirm WHO sealed it — ask the sender for their key fingerprint.';
  }
  if(report.trust_level==='LOW'&&!f.has_signature){
    return'This file has no signature — anyone could have made it. Don\'t rely on it for decisions.';
  }
  if(f.signature_valid===false||f.integrity_ok===false){
    return'This file was changed after it was sealed. Don\'t rely on it.';
  }
  return'We couldn\'t fully check this file in the browser. Run epi verify on your own machine for a complete answer.';
}

function showReport(report,errMsg){
  if(errMsg){showResult('fail',errMsg);return}
  var tl=report.trust_level||'';
  var type='fail';
  // Green only for org-pinned HIGH. Unpinned valid seal is warn, not pass.
  if(tl==='HIGH')type='pass';
  else if(tl==='LOW'||tl==='MEDIUM')type='warn';
  else if(tl==='NONE')type='fail';
  // Do not upgrade unpinned integrity to green pass
  if(type==='fail'&&report.facts&&report.facts.structure_ok&&report.facts.integrity_ok&&report.facts.signature_valid!==false){
    var idOk=report.identity&&report.identity.status==='KNOWN';
    type=idOk?'pass':'warn';
  }
  showResult(type,'<div style="font-size:1rem;margin-bottom:0.6rem">'+esc(plainHeadline(report))+'</div>'+witnessLineHTML(report)+storyHTML(report.story,!!report.facts&&(report.facts.integrity_ok===false||report.facts.signature_valid===false))+'<details style="margin-top:0.4rem"><summary style="cursor:pointer;font-size:0.72rem;color:var(--ink-dim)">Details</summary>'+reportDOM(report)+'</details>');
  updateChecks(report);
}

function resetChecks(){
  // Restore the six original neutral labels (one dot each). Never derive
  // labels from previous results: after a bad file the old PASS/FAIL text
  // must not linger under the new error.
  var labels={'chk1':'01 · Structure','chk2':'02 · File hashes','chk3':'03 · Signature','chk4':'04 · Step chain','chk5':'05 · Identity (browser)','chk6':'06 · Full audit → CLI'};
  ['chk1','chk2','chk3','chk4','chk5','chk6'].forEach(function(id){var el=document.getElementById(id);if(el){el.classList.remove('pass');el.innerHTML='<span class="cd"></span> '+labels[id];}}); // static-html: restores the fixed neutral labels above
  if(dr)dr.style.display='none';
  setDropSealState(null);
}

if(dz&&fi&&dr){
  dz.addEventListener('click',function(){fi.click()});
  dz.addEventListener('keydown',function(e){
    if(e.key==='Enter'||e.key===' '){e.preventDefault();fi.click()}
  });
  ['dragenter','dragover','dragleave','drop'].forEach(function(ev){dz.addEventListener(ev,function(e){e.preventDefault()});document.body.addEventListener(ev,function(e){e.preventDefault()})});
  ['dragenter','dragover'].forEach(function(ev){dz.addEventListener(ev,function(){dz.classList.add('drag-over')})});
  ['dragleave','drop'].forEach(function(ev){dz.addEventListener(ev,function(){dz.classList.remove('drag-over')})});
  dz.addEventListener('drop',function(e){if(e.dataTransfer.files[0])resetChecks();lastFile=e.dataTransfer.files[0]||null;processFile(e.dataTransfer.files[0])});
  fi.addEventListener('change',function(){if(fi.files[0]){resetChecks();lastFile=fi.files[0];processFile(fi.files[0])}});
}
if(wz&&wi){
  wz.addEventListener('click',function(){wi.click()});
  wz.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();wi.click()}});
  ['dragenter','dragover','dragleave','drop'].forEach(function(ev){wz.addEventListener(ev,function(e){e.preventDefault()})});
  ['dragenter','dragover'].forEach(function(ev){wz.addEventListener(ev,function(){wz.classList.add('drag-over')})});
  ['dragleave','drop'].forEach(function(ev){wz.addEventListener(ev,function(){wz.classList.remove('drag-over')})});
  wz.addEventListener('drop',function(e){if(e.dataTransfer.files[0])loadWitnessFile(e.dataTransfer.files[0])});
  wi.addEventListener('change',function(){if(wi.files[0])loadWitnessFile(wi.files[0])});
}
if(typeof window!=='undefined'){
  window.epiVerifyDroppedFile=processFile;
  window.epiLoadWitnessLog=loadWitnessFile;
  window.epiWitnessVerdict=witnessVerdict;
  window.epiWitnessContentDigest=witnessContentDigest;
  window.epiIsPreJcsSpec=typeof globalThis.epiIsPreJcsSpec==='function'?globalThis.epiIsPreJcsSpec:undefined;
  // Read-only label helpers. The browser tests use these to assert the exact
  // wording and that the fingerprint matches epi_core.keys.key_fingerprint.
  window.epiApprovalLabels={
    approvalSourceLabel:approvalSourceLabel,
    approvalStepLine:approvalStepLine,
    keyFingerprintHex:keyFingerprintHex
  };
}
})();
