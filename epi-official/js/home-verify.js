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
  else if(levelLabel==='UNVERIFIED_IDENTITY')title='SEAL VALID · IDENTITY NOT PINNED';
  else if(levelLabel.indexOf('SEAL')===0||levelLabel==='UNSIGNED'||levelLabel==='INCOMPLETE')title=levelLabel;
  else if(levelLabel)title=levelLabel+' TRUST';
  return '<div style="font-size:0.82rem;margin-bottom:0.6rem"><strong style="font-size:1.05rem;color:'+trustColor+'">'+trustIcon+' '+title+'</strong> <span style="color:var(--ink-muted);font-size:0.72rem">v'+m.spec_version+steps+'</span></div>'
    +chks.join('<br>')
    +'<div style="margin-top:0.5rem;font-size:0.68rem;color:var(--ink-dim);border-top:1px solid var(--border);padding-top:0.5rem">'+report.trust_message+'</div>'
    +(i.detail?'<div style="margin-top:0.3rem;font-size:0.68rem;color:var(--ink-dim)">'+i.detail+'</div>':'');
}

function updateChecks(report){
  function set(id,pass,text){var el=document.getElementById(id);if(!el)return;if(pass)el.classList.add('pass');el.innerHTML='<span class="check-dot"></span> '+text}
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

function toU8(buffer){
  if(buffer instanceof Uint8Array)return buffer;
  if(buffer instanceof ArrayBuffer)return new Uint8Array(buffer);
  if(ArrayBuffer.isView(buffer))return new Uint8Array(buffer.buffer,buffer.byteOffset,buffer.byteLength);
  return new Uint8Array(buffer||[]);
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
function sortedJSON(obj){
  if(obj && typeof obj==='object' && obj.__num!==undefined)return jcsNumberFromRaw(obj.__num);
  if(obj===null)return'null';
  if(typeof obj==='string')return JSON.stringify(obj);
  if(typeof obj==='number')return String(Number.isFinite(obj)?obj:'null');
  if(typeof obj==='boolean')return String(obj);
  if(Array.isArray(obj))return'['+obj.map(sortedJSON).join(',')+']';
  var keys=Object.keys(obj).sort(),p=[];
  for(var i=0;i<keys.length;i++){var k=keys[i];if(obj[k]!==undefined)p.push(JSON.stringify(k)+':'+sortedJSON(obj[k]));}
  return'{'+p.join(',')+'}';
}
// JCS number encoding from raw JSON number text (matches Python rfc8785).
function jcsNumberFromRaw(raw){
  if(/^-?(0|[1-9][0-9]*)$/.test(raw))return raw;
  var n=Number(raw);
  if(!isFinite(n))return'null';
  return String(n);
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

async function canonicalStepHash(step){
  // Matches epi_core.serialize.get_canonical_hash(StepModel, format='json'):
  // sort keys, no whitespace, exclude source_type, and normalize only the
  // top-level datetime field (timestamp) the way Pydantic model_dump does.
  var fields=['index','timestamp','kind','content','trace_id','span_id','parent_span_id','prev_hash','governance'];
  var canonical={};
  for(var i=0;i<fields.length;i++){
    var k=fields[i];
    var v=step[k]!==undefined?step[k]:null;
    if(k==='timestamp'&&typeof v==='string')v=epiUtcZ(v);
    canonical[k]=v;
  }
  return sha256(new TextEncoder().encode(sortedJSON(canonical)));
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

async function auditStepChain(steps){
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
    var expected=await canonicalStepHash(steps[i-1]);
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
  var chain=await auditStepChain(steps);
  var count=auditStepCount(steps,manifest);
  return{sequence_ok:seq,completeness_ok:comp,chain_ok:chain,step_count_ok:count};
}

async function processFile(f){
  var nm=(f&&f.name?f.name:'').toLowerCase();
  showResult('warn','<em>Reading '+(f.name||'file')+'...</em>');

  try{
    if(typeof JSZip==='undefined'){
      showResult('fail','<strong>Verifier not loaded</strong><br>JSZip missing — hard-refresh (Ctrl+Shift+R) and try again.');
      return;
    }
    var buf=await f.arrayBuffer();
    if(!buf||buf.byteLength<4){
      showResult('fail','<strong>Not a valid EPI file</strong><br>File is empty or too small ('+(buf?buf.byteLength:0)+' bytes).');
      return;
    }
    var u8=toU8(buf);
    var containerFmt=detectContainer(u8);
    // Prefer magic-byte detection over file extension (pickers / email renames)
    if(!containerFmt){
      var peek=hexPreview(u8,16);
      var hint='';
      if(u8[0]===0x3c&&u8[1]===0x21&&u8[2]===0x44)hint=' This looks like an HTML page (broken download), not a sealed .epi.';
      else if(nm&&!nm.endsWith('.epi')&&!nm.endsWith('.zip'))hint=' Expected a .epi file.';
      showResult('fail','<strong>Not a valid EPI file</strong><br>No EPI envelope or ZIP header detected.'+hint+'<br><span style="font-size:0.68rem;opacity:.85">First bytes: '+peek+'</span>');
      return;
    }

    var zipBuf;
    try{zipBuf=extractZIPPayload(u8,containerFmt)}
    catch(ex){showResult('fail','<strong>Could not locate ZIP payload</strong><br>'+ex.message);return}
    var zip;
    try{zip=await JSZip.loadAsync(zipBuf)}catch(e){showResult('fail','<strong>ZIP extraction failed</strong><br>'+e.message+' (container: '+containerFmt+')');return}

    var report={facts:{structure_ok:false,integrity_ok:false,signature_valid:null,has_signature:false,mismatches:{},chain_ok:true,sequence_ok:true,completeness_ok:true,transparency_ok:null},identity:{status:'UNKNOWN',name:null,detail:null,registry_verified:false,public_key_id:null},metadata:{spec_version:'?',workflow_id:'?',created_at:'?',files_checked:0,verifier_version:'browser',steps_count:null},trust_level:'NONE',trust_message:''};

    // Check 1: mimetype
    if(!zip.file('mimetype')){report.facts.structure_ok=false;showReport(report,'No mimetype file in archive');return}
    var mt=await zip.file('mimetype').async('string');
    var mtNorm=mt.trim().replace(/\r/g,'');
    if(mtNorm!==EPI_MIMETYPE&&mtNorm!=='application/vnd.epi'&&mtNorm!=='application/vnd.epi+zip'){
      report.facts.structure_ok=false;showReport(report,'Invalid mimetype: '+mtNorm);return
    }
    report.facts.structure_ok=true;

    // Check 2: manifest.json
    var mf=zip.file('manifest.json');
    if(!mf){showResult('fail','<strong>No manifest.json found</strong>');return}
    var rawManifest;
    try{rawManifest=await mf.async('string')}catch(e){showResult('fail','<strong>Could not read manifest.json</strong><br>'+e.message);return}
    var manifest;
    try{manifest=parseJSONPreserveNumbers(rawManifest)}catch(e){showResult('fail','<strong>manifest.json parse error</strong><br>'+e.message);return}
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
    var excludePrefixes=['mimetype','manifest.json','viewer.html','VERIFY.txt','review.json','review_index.json','reviews/','artifacts/scitt/'];
    Object.keys(zip.files).forEach(function(nm){
      var excluded=false;
      for(var k=0;k<excludePrefixes.length;k++){if(nm.indexOf(excludePrefixes[k])===0){excluded=true;break}}
      if(!excluded&&!fileManifest[nm])mismatches[nm]='Extra file not in manifest';
    });
    report.metadata.files_checked=checked;
    report.facts.mismatches=mismatches;

    // Check 5: forensic audits on the step timeline
    var forensic=await auditSteps(steps,manifest);
    report.facts.sequence_ok=forensic.sequence_ok;
    report.facts.completeness_ok=forensic.completeness_ok;
    report.facts.chain_ok=forensic.chain_ok;
    report.facts.step_count_ok=forensic.step_count_ok;
    // File-hash integrity only (matches Python). Completeness gaps are not a broken seal.
    var hashesOk=Object.keys(mismatches).length===0;
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
        if(nameParts.length>=2)report.identity.name=nameParts[1];
        if(sigResult.valid===true){
          if(registry&&registry.trusted_keys&&registry.trusted_keys[manifest.public_key]){
            report.identity.status='KNOWN';
            report.identity.name=registry.trusted_keys[manifest.public_key];
            report.identity.detail='Verified via remote anchor: '+(registry.name||'EPI Labs Trust Registry');
            report.identity.registry_verified=true;
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
    // UNVERIFIED_IDENTITY (amber) — never "SEAL OK" (skim must not imply claim safety).
    if(report.facts.integrity_ok&&report.facts.signature_valid===true&&report.identity.status==='KNOWN'){report.trust_level='HIGH';report.trust_message='Seal valid · identity pinned (org trust list)'}
    else if(report.facts.integrity_ok&&report.facts.signature_valid===true&&report.identity.status!=='KNOWN'){report.trust_level='UNVERIFIED_IDENTITY';report.trust_message='Seal valid · identity not pinned — not claim-ready. Anyone can re-sign a rebuilt chain. CLI: epi keys trust + epi verify --policy strict'}
    else if(report.facts.integrity_ok&&!report.facts.has_signature){report.trust_level='UNSIGNED';report.trust_message='Integrity intact · no signature — anyone could have produced this file'}
    else if(!report.facts.integrity_ok){report.trust_level='SEAL FAIL';report.trust_message='Integrity compromised — do not trust this copy'}
    else if(report.facts.signature_valid===false){report.trust_level='SEAL FAIL';report.trust_message='Signature invalid — artifact may be tampered'}
    else{report.trust_level='INCOMPLETE';report.trust_message='Verification incomplete in browser — use epi verify --policy strict offline for claim audit'}

    showReport(report,'');
  }catch(e){showResult('fail','<strong>Verification error</strong><br>'+e.message)}
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
  dr.style.display='block';dr.style.background=c[0];dr.style.border='1px solid '+c[1];dr.style.color=c[2];dr.innerHTML=msg;
  if(type==='pass'||type==='fail'||type==='warn')setDropSealState(type);
  else setDropSealState(null);
}

function showReport(report,errMsg){
  if(errMsg){showResult('fail',errMsg);return}
  var tl=report.trust_level||'';
  var type='fail';
  // Green only for org-pinned HIGH. Unpinned valid seal is warn, not pass.
  if(tl==='HIGH')type='pass';
  else if(tl==='UNVERIFIED_IDENTITY'||tl==='UNSIGNED'||tl==='INCOMPLETE'||tl==='MEDIUM'||tl==='LOW'||tl==='SEAL OK')type='warn';
  else if(tl==='SEAL FAIL'||tl==='NONE')type='fail';
  // Do not upgrade unpinned integrity to green pass
  if(type==='fail'&&report.facts&&report.facts.structure_ok&&report.facts.integrity_ok&&report.facts.signature_valid!==false){
    var idOk=report.identity&&report.identity.status==='KNOWN';
    type=idOk?'pass':'warn';
  }
  showResult(type,reportDOM(report));
  updateChecks(report);
}

function resetChecks(){
  ['chk1','chk2','chk3','chk4','chk5','chk6'].forEach(function(id){var el=document.getElementById(id);if(el){el.classList.remove('pass');el.innerHTML='<span class="check-dot"></span> '+el.innerHTML.replace(/^.*?\d{2}\s*·\s*/,'')}});
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
  dz.addEventListener('drop',function(e){if(e.dataTransfer.files[0])resetChecks();processFile(e.dataTransfer.files[0])});
  fi.addEventListener('change',function(){if(fi.files[0]){resetChecks();processFile(fi.files[0])}});
}
if(typeof window!=='undefined'){
  window.epiVerifyDroppedFile=processFile;
  window.epiIsPreJcsSpec=typeof globalThis.epiIsPreJcsSpec==='function'?globalThis.epiIsPreJcsSpec:undefined;
}
})();
