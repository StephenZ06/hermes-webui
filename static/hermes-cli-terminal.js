const HERMES_CLI_UI={
  open:false,
  sessionId:null,
  term:null,
  fitAddon:null,
  source:null,
  resizeObserver:null,
  resizeTimer:null,
};

function _hermesCliEls(){
  return {
    panel:$('hermesCliPanel'),
    viewport:$('hermesCliViewport'),
    surface:$('hermesCliSurface'),
  };
}

function _ensureHermesCliXterm(){
  const {surface}=_hermesCliEls();
  if(!surface)return null;
  if(HERMES_CLI_UI.term)return HERMES_CLI_UI.term;
  if(!_xtermReady()){
    surface.textContent='Terminal library failed to load. Check network access to cdn.jsdelivr.net.';
    return null;
  }
  const term=new window.Terminal({
    cursorBlink:true,
    fontSize:13,
    fontFamily:'Menlo, Monaco, Consolas, "Liberation Mono", monospace',
    scrollback:2000,
    convertEol:false,
    theme:_terminalTheme(),
  });
  let fitAddon=null;
  if(window.FitAddon&&typeof window.FitAddon.FitAddon==='function'){
    fitAddon=new window.FitAddon.FitAddon();
    term.loadAddon(fitAddon);
  }
  if(window.WebLinksAddon&&typeof window.WebLinksAddon.WebLinksAddon==='function'){
    term.loadAddon(new window.WebLinksAddon.WebLinksAddon());
  }
  term.open(surface);
  term.onData(data=>{
    const sid=HERMES_CLI_UI.sessionId;
    if(!sid)return;
    api('/api/terminal/input',{method:'POST',body:JSON.stringify({
      session_id:sid,
      data,
    })}).catch(e=>showToast(t('terminal_input_failed')+e.message,2600,'error'));
  });
  HERMES_CLI_UI.term=term;
  HERMES_CLI_UI.fitAddon=fitAddon;
  return term;
}

function _fitHermesCliTerminal(){
  const term=HERMES_CLI_UI.term;
  if(!term)return;
  try{if(HERMES_CLI_UI.fitAddon)HERMES_CLI_UI.fitAddon.fit();}catch(_){}
  _scheduleHermesCliResize();
}

function _hermesCliDimensions(){
  const term=HERMES_CLI_UI.term;
  if(term&&term.cols&&term.rows)return {rows:term.rows,cols:term.cols};
  return {rows:24,cols:80};
}

function _scheduleHermesCliResize(){
  clearTimeout(HERMES_CLI_UI.resizeTimer);
  HERMES_CLI_UI.resizeTimer=setTimeout(_resizeHermesCliTerminal,120);
}

async function _resizeHermesCliTerminal(){
  const sid=HERMES_CLI_UI.sessionId;
  if(!sid||!HERMES_CLI_UI.open)return;
  const dims=_hermesCliDimensions();
  try{
    await api('/api/terminal/resize',{method:'POST',body:JSON.stringify({
      session_id:sid,
      rows:dims.rows,
      cols:dims.cols,
    })});
  }catch(_){}
}

function _connectHermesCliOutput(){
  const sid=HERMES_CLI_UI.sessionId;
  if(!sid)return;
  if(HERMES_CLI_UI.source){
    try{if(HERMES_CLI_UI.source.readyState!==2)HERMES_CLI_UI.source.close();}catch(_){}
    HERMES_CLI_UI.source=null;
  }
  const url=new URL('api/terminal/output',document.baseURI||location.href);
  url.searchParams.set('session_id',sid);
  const source=new EventSource(url.href,{withCredentials:true});
  HERMES_CLI_UI.source=source;
  source.addEventListener('output',ev=>{
    if(HERMES_CLI_UI.source!==source)return;
    let text='';
    try{text=(JSON.parse(ev.data)||{}).text||'';}
    catch(_){text=ev.data||'';}
    if(HERMES_CLI_UI.term&&text)HERMES_CLI_UI.term.write(text);
  });
  source.addEventListener('terminal_closed',()=>{
    if(HERMES_CLI_UI.source!==source)return;
    if(HERMES_CLI_UI.term)HERMES_CLI_UI.term.writeln('\r\n[hermes cli closed]\r\n');
    try{if(source&&source.readyState!==2)source.close();}catch(_){}
    HERMES_CLI_UI.source=null;
  });
  source.addEventListener('terminal_error',ev=>{
    if(HERMES_CLI_UI.source!==source)return;
    let msg=t('terminal_error');
    try{msg=(JSON.parse(ev.data)||{}).error||msg;}catch(_){}
    if(HERMES_CLI_UI.term)HERMES_CLI_UI.term.writeln('\r\n[hermes cli error] '+msg+'\r\n');
    try{if(source&&source.readyState!==2)source.close();}catch(_){}
    HERMES_CLI_UI.source=null;
  });
  source.addEventListener('error',()=>{
    if(HERMES_CLI_UI.source!==source)return;
    if(source.readyState===EventSource.CLOSED){
      if(HERMES_CLI_UI.term)HERMES_CLI_UI.term.writeln('\r\n[hermes cli disconnected]\r\n');
      try{source.close();}catch(_){}
      HERMES_CLI_UI.source=null;
    }
  });
}

async function _startHermesCliTerminal(restart=false){
  const term=_ensureHermesCliXterm();
  if(!term)return;
  const dims=_hermesCliDimensions();
  let resp;
  try{
    resp=await api('/api/terminal/start',{method:'POST',body:JSON.stringify({
      hermes_cli:true,
      rows:dims.rows,
      cols:dims.cols,
      restart:!!restart,
    })});
  }catch(e){
    showToast(t('terminal_start_failed')+e.message,3200,'error');
    return;
  }
  HERMES_CLI_UI.sessionId=resp&&resp.session_id||null;
  _connectHermesCliOutput();
  _fitHermesCliTerminal();
}

async function openHermesCliTerminal(){
  const {panel}=_hermesCliEls();
  if(!panel)return;
  if(HERMES_CLI_UI.open){
    focusHermesCliInput();
    return;
  }
  const mainChat=$('mainChat');
  if(mainChat)mainChat.classList.add('hermes-cli-active');
  panel.hidden=false;
  HERMES_CLI_UI.open=true;
  if(typeof renderSessionListFromCache==='function')renderSessionListFromCache();
  if(!HERMES_CLI_UI.resizeObserver&&window.ResizeObserver){
    HERMES_CLI_UI.resizeObserver=new ResizeObserver(()=>_fitHermesCliTerminal());
    HERMES_CLI_UI.resizeObserver.observe(panel);
  }
  requestAnimationFrame(()=>{
    _fitHermesCliTerminal();
    focusHermesCliInput();
  });
  await _startHermesCliTerminal(false);
}

function closeHermesCliPanel(){
  const {panel}=_hermesCliEls();
  const mainChat=$('mainChat');
  if(HERMES_CLI_UI.source){
    try{if(HERMES_CLI_UI.source.readyState!==2)HERMES_CLI_UI.source.close();}catch(_){}
    HERMES_CLI_UI.source=null;
  }
  if(mainChat)mainChat.classList.remove('hermes-cli-active');
  if(panel)panel.hidden=true;
  HERMES_CLI_UI.open=false;
  if(typeof renderSessionListFromCache==='function')renderSessionListFromCache();
}

function focusHermesCliInput(){
  if(HERMES_CLI_UI.term)HERMES_CLI_UI.term.focus();
}

function clearHermesCliTerminal(){
  if(HERMES_CLI_UI.term)HERMES_CLI_UI.term.clear();
}

async function restartHermesCliTerminal(){
  if(!HERMES_CLI_UI.open)return;
  if(HERMES_CLI_UI.source){
    try{if(HERMES_CLI_UI.source.readyState!==2)HERMES_CLI_UI.source.close();}catch(_){}
    HERMES_CLI_UI.source=null;
  }
  if(HERMES_CLI_UI.term)HERMES_CLI_UI.term.reset();
  await _startHermesCliTerminal(true);
}

window.addEventListener('resize',()=>{
  if(!HERMES_CLI_UI.open)return;
  _fitHermesCliTerminal();
});

window.addEventListener('beforeunload',()=>{
  if(HERMES_CLI_UI.source)try{if(HERMES_CLI_UI.source.readyState!==2)HERMES_CLI_UI.source.close();}catch(_){}
});

if(window.MutationObserver){
  new MutationObserver(()=>{if(HERMES_CLI_UI.term)HERMES_CLI_UI.term.options.theme=_terminalTheme();}).observe(document.documentElement,{
    attributes:true,
    attributeFilter:['class','data-skin'],
  });
}
