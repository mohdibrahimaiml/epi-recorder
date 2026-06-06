/* EPI Live Terminal — typewriter animation */
(function(){
  var liveTerm = document.getElementById('liveTerminal');
  if(!liveTerm)return;

  var lines = [
    {c:'pip install epi-recorder',              cls:'code-cmt', t:500},
    {c:'  Downloading epi-recorder-4.2.0...',    cls:'code-cmt', t:250},
    {c:'  Installing collected packages...',      cls:'code-cmt', t:250},
    {c:'Successfully installed epi-recorder-4.2.0', cls:'code-cmt', t:600},
    {c:'', cls:'', t:400},
    {c:'cat agent.py',            cls:'code-cmt', t:400},
    {c:'', cls:'', t:250},
    {c:'from', cls:'code-kw', t:60},{c:' openai ', cls:'', t:80},{c:'import', cls:'code-kw', t:60},{c:' OpenAI', cls:'', t:350},
    {c:'from', cls:'code-kw', t:60},{c:' epi_recorder ', cls:'', t:80},{c:'import', cls:'code-kw', t:60},{c:' record', cls:'code-fn', t:80},{c:', ', cls:'', t:60},{c:'wrap_openai', cls:'code-fn', t:350},
    {c:'', cls:'', t:250},
    {c:'client = wrap_openai(OpenAI())', cls:'', t:400},
    {c:'', cls:'', t:300},
    {c:'with record("loan-decision.epi"):', cls:'code-kw', t:300},
    {c:'', cls:'', t:300},
    {c:'    result = client.chat.completions.create(', cls:'', t:150},
    {c:'        model="gpt-4o",',          cls:'code-str', t:120},
    {c:'        messages=[{',              cls:'', t:100},
    {c:'            "role": "user",',       cls:'code-str', t:100},
    {c:'            "content": "Assess applicant #421"', cls:'code-str', t:120},
    {c:'        }]',                       cls:'', t:100},
    {c:'    )',                            cls:'', t:600},
    {c:'', cls:'', t:400},
    {c:'# Sealed and signed',             cls:'code-cmt', t:200},
    {c:'# $ epi verify loan-decision.epi', cls:'code-cmt', t:200},
    {c:'', cls:'', t:300},
    {c:'  VERIFIED   Ed25519   SHA-256   42 steps   chain intact', cls:'code-g', t:200},
  ];

  var i=0,timer=null,active=false,observed=false;
  var promptLines = [0,4]; // line indices that get $ prompt

  function reset(){
    if(timer)clearTimeout(timer);
    i=0;active=false;
    liveTerm.textContent='';
    var f=document.createElement('div');
    f.style.cssText='position:absolute;bottom:12px;right:16px;font-size:0.6rem;color:rgba(255,255,255,0.12);letter-spacing:0.06em;font-family:var(--mono)';
    f.textContent='EPI_TERMINAL v4.2.0';
    liveTerm.appendChild(f);
  }

  function writeLine(){
    if(!active)return;
    if(i>=lines.length){
      // Final cursor
      var dl=document.createElement('div');
      dl.style.lineHeight='2.1';
      var ps=document.createElement('span');ps.className='code-cmt';ps.textContent='$ ';
      dl.appendChild(ps);
      var cr=document.createElement('span');cr.className='code-cmt';
      cr.style.animation='blink 0.8s step-end infinite';cr.textContent='_';
      dl.appendChild(cr);
      liveTerm.appendChild(dl);
      return;
    }

    var step=lines[i];
    if(step.c===''){
      var el=document.createElement('div');el.style.lineHeight='0.6';el.textContent='\u00A0';
      liveTerm.appendChild(el);
      i++;timer=setTimeout(writeLine,step.t);return;
    }

    var lineDiv=document.createElement('div');lineDiv.style.lineHeight='2.1';

    // Prompt for shell lines
    if(promptLines.indexOf(i)>=0){
      var pr=document.createElement('span');pr.className='code-cmt';pr.textContent='$ ';
      lineDiv.appendChild(pr);
    }else if(i>4){
      var pad=document.createElement('span');pad.className='code-cmt';pad.textContent='  ';
      lineDiv.appendChild(pad);
    }

    var ch=document.createElement('span');
    if(step.cls)ch.className=step.cls;
    ch.textContent=step.c;
    lineDiv.appendChild(ch);
    liveTerm.appendChild(lineDiv);
    liveTerm.scrollTop=liveTerm.scrollHeight;
    i++;
    timer=setTimeout(writeLine,step.t);
  }

  function play(){
    if(!liveTerm||active)return;
    reset();active=true;timer=setTimeout(writeLine,400);
  }

  window.replayTerminal=function(){reset();setTimeout(play,200);};

  if('IntersectionObserver' in window){
    var obs=new IntersectionObserver(function(e){e.forEach(function(x){if(x.isIntersecting&&!observed){observed=true;play();obs.unobserve(liveTerm);}});},{threshold:0.2});
    obs.observe(liveTerm);
  }else{setTimeout(play,800);}
})();
