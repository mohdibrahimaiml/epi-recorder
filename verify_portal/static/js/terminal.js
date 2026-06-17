var terminalSteps=[
  /* ── PHASE 1: INSTALL ── */
  {text:'<span class="term-dim">┌─ PHASE 1 ──────────────────────────┐</span>',delay:60},
  {text:'<span class="term-dim">│</span> <span class="term-kw">Install</span> <span class="term-dim">— get the package</span>            <span class="term-dim">│</span>',delay:80},
  {text:'',delay:20},
  {text:'<span class="term-dim">$</span> <span class="term-kw">pip</span> <span class="term-fn">install</span> epi-recorder',delay:40},
  {text:'<span class="term-dim">Collecting epi-recorder</span>',delay:30},
  {text:'<span class="term-dim">  Downloading epi_recorder-4.2.0-py3-none-any.whl (124 kB)</span>',delay:40},
  {text:'<span class="term-dim">Requirement already satisfied: openai&gt;=1.0.0 in ./venv</span>',delay:30},
  {text:'<span class="term-dim">Requirement already satisfied: cryptography&gt;=41.0.0 in ./venv</span>',delay:30},
  {text:'<span class="term-green">Successfully installed epi-recorder-4.2.0</span>',delay:70},
  {text:'',delay:50},

  /* ── PHASE 2: WRITE THE CODE ── */
  {text:'<span class="term-dim">┌─ PHASE 2 ──────────────────────────┐</span>',delay:60},
  {text:'<span class="term-dim">│</span> <span class="term-kw">Write Code</span> <span class="term-dim">— wrap your LLM client</span>      <span class="term-dim">│</span>',delay:80},
  {text:'',delay:20},
  {text:'<span class="term-dim">$</span> <span class="term-fn">cat</span> agent.py',delay:40},
  {text:'',delay:20},
  {text:'<span class="term-dim">1</span>  <span class="term-kw">from</span> openai <span class="term-kw">import</span> OpenAI',delay:30},
  {text:'<span class="term-dim">2</span>  <span class="term-kw">from</span> epi_recorder <span class="term-kw">import</span> <span class="term-fn">record</span>, <span class="term-fn">wrap_openai</span>',delay:30},
  {text:'<span class="term-dim">3</span>  ',delay:10},
  {text:'<span class="term-dim">4</span>  <span class="term-cmt"># Wrap once — EPI intercepts every API call</span>',delay:40},
  {text:'<span class="term-dim">5</span>  client = <span class="term-fn">wrap_openai</span>(OpenAI())',delay:30},
  {text:'<span class="term-dim">6</span>  ',delay:10},
  {text:'<span class="term-dim">7</span>  <span class="term-kw">with</span> <span class="term-fn">record</span>(<span class="term-str">"loan-decision.epi"</span>):',delay:40},
  {text:'<span class="term-dim">8</span>      result = client.chat.completions.create(',delay:30},
  {text:'<span class="term-dim">9</span>          model=<span class="term-str">"gpt-4"</span>,',delay:30},
  {text:'<span class="term-dim">10</span>          messages=[{<span class="term-str">"role"</span>:<span class="term-str">"user"</span>,',delay:30},
  {text:'<span class="term-dim">11</span>                    <span class="term-str">"content"</span>:<span class="term-str">"Assess loan applicant #421"</span>}]',delay:40},
  {text:'<span class="term-dim">12</span>      )',delay:20},
  {text:'<span class="term-dim">13</span>  ',delay:10},
  {text:'<span class="term-dim">14</span>  <span class="term-cmt"># → loan-decision.epi written — signed and sealed</span>',delay:60},
  {text:'',delay:50},

  /* ── PHASE 3: RECORD ── */
  {text:'<span class="term-dim">┌─ PHASE 3 ──────────────────────────┐</span>',delay:60},
  {text:'<span class="term-dim">│</span> <span class="term-kw">Record</span> <span class="term-dim">— execute the agent</span>              <span class="term-dim">│</span>',delay:80},
  {text:'',delay:20},
  {text:'<span class="term-dim">$</span> <span class="term-kw">python</span> agent.py',delay:40},
  {text:'',delay:30},
  {text:'<span class="term-dim">[epi] Session ID:</span>   <span class="term-amber">e7f3a8b2-4c1d-9e6f</span>',delay:50},
  {text:'<span class="term-dim">[epi] Recording:</span>     loan-decision.epi',delay:40},
  {text:'',delay:20},
  {text:'<span class="term-cmt"># LLM call intercepted — request + response captured</span>',delay:50},
  {text:'<span class="term-dim">[epi] API call:</span>      chat.completions.create (model=gpt-4)',delay:40},
  {text:'<span class="term-dim">[epi] Tokens:</span>        in=142 · out=387 · total=529',delay:40},
  {text:'<span class="term-dim">[epi] Tool calls:</span>     prompt_injection_check · credit_report_lookup',delay:40},
  {text:'',delay:20},
  {text:'<span class="term-dim">[epi] Steps recorded:</span>  <span class="term-amber">42</span>',delay:40},
  {text:'<span class="term-dim">[epi] Files embedded:</span>  <span class="term-amber">11</span>',delay:40},
  {text:'<span class="term-dim">[epi] Manifest hash:</span>   SHA-256 computed',delay:30},
  {text:'<span class="term-dim">[epi] Signing key:</span>     ed25519:prod:v2',delay:30},
  {text:'<span class="term-dim">[epi] Status:</span>          <span class="term-green">SIGNED ✓</span>',delay:60},
  {text:'',delay:50},

  /* ── PHASE 4: FILE CREATED ── */
  {text:'<span class="term-dim">┌─ PHASE 4 ──────────────────────────┐</span>',delay:60},
  {text:'<span class="term-dim">│</span> <span class="term-green">File Created</span> <span class="term-dim">— evidence sealed forever</span>  <span class="term-dim">│</span>',delay:80},
  {text:'',delay:20},
  {text:'<span class="term-dim">$</span> <span class="term-fn">ls</span> -lh loan-decision.epi',delay:40},
  {text:'<span class="term-green">-rw-r--r--  1 user  staff   142K  loan-decision.epi</span>',delay:60},
  {text:'',delay:20},
  {text:'<span class="term-dim">$</span> <span class="term-fn">file</span> loan-decision.epi',delay:40},
  {text:'<span class="term-dim">loan-decision.epi: Zip archive + HTML document</span>',delay:50},
  {text:'',delay:20},
  {text:'<span class="term-cmt"># A polyglot container: valid ZIP and valid HTML.</span>',delay:50},
  {text:'<span class="term-cmt"># Opens in any browser. Verifiable offline, forever.</span>',delay:50},
  {text:'',delay:50},

  /* ── PHASE 5: VERIFY ── */
  {text:'<span class="term-dim">┌─ PHASE 5 ──────────────────────────┐</span>',delay:60},
  {text:'<span class="term-dim">│</span> <span class="term-green">Verify</span> <span class="term-dim">— cryptographic checks, all local</span> <span class="term-dim">│</span>',delay:80},
  {text:'',delay:20},
  {text:'<span class="term-dim">$</span> <span class="term-green">epi verify</span> loan-decision.epi',delay:40},
  {text:'',delay:30},
  {text:'<span class="term-dim">  ── EPI VERIFIER v4.2.0 ──</span>',delay:40},
  {text:'',delay:20},
  {text:'<span class="term-dim">  [1/5]</span> Structure  <span class="term-dim">········</span> <span class="term-green">PASS</span>  <span class="term-dim">(valid polyglot ZIP+HTML)</span>',delay:50},
  {text:'<span class="term-dim">  [2/5]</span> Manifest     <span class="term-dim">······</span> <span class="term-green">PASS</span>  <span class="term-dim">(SHA-256: d4e2f1a8b3c7...)</span>',delay:50},
  {text:'<span class="term-dim">  [3/5]</span> Integrity     <span class="term-dim">·····</span> <span class="term-green">PASS</span>  <span class="term-dim">(11 files, all hashes match)</span>',delay:50},
  {text:'<span class="term-dim">  [4/5]</span> Hash Chain    <span class="term-dim">·····</span> <span class="term-green">PASS</span>  <span class="term-dim">(42 steps, chain intact)</span>',delay:50},
  {text:'<span class="term-dim">  [5/5]</span> Signature     <span class="term-dim">····</span> <span class="term-green">PASS</span>  <span class="term-dim">(Ed25519: valid · identity: KNOWN)</span>',delay:60},
  {text:'',delay:20},
  {text:'<span class="term-dim">  ───────────────────────</span>',delay:30},
  {text:'  <span class="term-dim">Trust Level:</span>  <span class="term-green">HIGH</span>',delay:50},
  {text:'  <span class="term-dim">Verification:</span> <span class="term-green">PASSED — 5/5 checks</span>',delay:50},
  {text:'  <span class="term-dim">Modified:</span>     <span class="term-green">No — artifact intact since sealing</span>',delay:60},
  {text:'',delay:50},

  /* ── PHASE 6: OPEN ── */
  {text:'<span class="term-dim">┌─ PHASE 6 ──────────────────────────┐</span>',delay:60},
  {text:'<span class="term-dim">│</span> <span class="term-kw">Open</span> <span class="term-dim">— view in any browser</span>             <span class="term-dim">│</span>',delay:80},
  {text:'',delay:20},
  {text:'<span class="term-dim">$</span> <span class="term-fn">open</span> loan-decision.epi',delay:40},
  {text:'',delay:30},
  {text:'<span class="term-cmt"># Opens in your default browser.</span>',delay:40},
  {text:'<span class="term-cmt"># Full audit log, decision tree, step-by-step replay.</span>',delay:50},
  {text:'<span class="term-cmt"># No server. No upload. Just the file.</span>',delay:50},
  {text:'',delay:30},
  {text:'<span class="term-dim">══════════════════════════════════════════════════</span>',delay:40},
  {text:'',delay:10},
  {text:'<span class="term-green">  EVIDENCE SEALED. VERIFIABLE FOREVER.</span>',delay:120},
  {text:'<span class="term-dim">    install  →  wrap  →  record  →  verify  →  open</span>',delay:100},
  {text:'',delay:30},
  {text:'<span class="term-dim">$</span> _',delay:6000}
];
var termEl=document.getElementById('terminalBody'),termRunning=false,termTimer=null;
function resetTerminal(){if(termTimer)clearTimeout(termTimer);termRunning=false;termEl.innerHTML='<span class="terminal-cursor"></span>';termEl.scrollTop=termEl.scrollHeight}
function playTerminal(){if(!termEl)return;if(termRunning)resetTerminal();termRunning=true;var lines=[],i=0;function next(){if(i>=terminalSteps.length){termEl.innerHTML=lines.join('\n')+'<span class="terminal-cursor"></span>';termEl.scrollTop=termEl.scrollHeight;termRunning=false;return}lines.push(terminalSteps[i].text);termEl.innerHTML=lines.join('\n')+'<span class="terminal-cursor"></span>';termEl.scrollTop=termEl.scrollHeight;i++;termTimer=setTimeout(next,terminalSteps[i-1].delay||40)}next()}
window.replayTerminal=function(){resetTerminal();setTimeout(playTerminal,200)};
var termObs=new IntersectionObserver(function(e){if(e[0].isIntersecting&&!termObs.triggered){termObs.triggered=true;setTimeout(playTerminal,300);termObs.unobserve(termEl)}},{threshold:0.2});
if(termEl)termObs.observe(termEl);
window._terminalPlayed=false;
window.ensureTerminalPlays=function(){
  if(window._terminalPlayed||!termEl)return;
  var rect=termEl.getBoundingClientRect();
  if(rect.top<window.innerHeight&&rect.bottom>0){
    window._terminalPlayed=true;
    setTimeout(playTerminal,400);
  }
};
setTimeout(window.ensureTerminalPlays,500);
setTimeout(window.ensureTerminalPlays,1200);
setTimeout(window.ensureTerminalPlays,2500);

})();