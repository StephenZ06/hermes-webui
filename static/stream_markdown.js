// Streaming-markdown helpers shared by every live chat stream.
//
// Moved out of messages.js's attachLiveStream() closure: none of these touch
// per-stream state (the media tail map and parser sentinel stay in the
// closure and are passed in), so one top-level copy serves every stream.
// Loaded before messages.js (index.html, sw.js precache).

function _smdRendererWithoutUnderscoreEmphasis(renderer){
  if(!renderer||!window.smd) return renderer;
  const baseAddToken=renderer.add_token;
  const baseEndToken=renderer.end_token;
  const baseAddText=renderer.add_text;
  const tokenStack=[];
  renderer.add_token=(data,token)=>{
    if(token===window.smd.ITALIC_UND||token===window.smd.STRONG_UND){
      const marker=token===window.smd.STRONG_UND?'__':'_';
      tokenStack.push(marker);
      baseAddText(data,marker);
      return;
    }
    tokenStack.push(null);
    baseAddToken(data,token);
  };
  renderer.end_token=(data)=>{
    const marker=tokenStack.pop();
    if(marker){
      baseAddText(data,marker);
      return;
    }
    baseEndToken(data);
  };
  return renderer;
}

// ui.js owns the image-only data URI policy. It loads before this script;
// fail closed if that contract is unavailable rather than inventing a second
// allowlist that can drift from settled rendering.
const _SMD_SAFE_IMG_URL_RE=/^(?:https?:|mailto:|tel:|\/|#|\?|\.)/i;

function _smdImgSrcAllowed(v){
  const s=String(v||'');
  if(/^data:/i.test(s)) return typeof _isSafeDataImageUri==='function'&&_isSafeDataImageUri(s);
  return _SMD_SAFE_IMG_URL_RE.test(s);
}

function _smdLinkHref(raw){
  const href=String(raw||'');
  if(/^session:\/\//i.test(href)){
    const sid=href.replace(/^session:\/\//i,'').split(/[?#]/)[0];
    try{
      const decoded=decodeURIComponent(sid);
      if(typeof _sessionUrlForSid==='function') return _sessionUrlForSid(decoded);
      return 'session/'+encodeURIComponent(decoded);
    }catch(_){
      return 'session/'+encodeURIComponent(sid);
    }
  }
  if(/^workspace:\/\//i.test(href)){
    try{
      const rel=decodeURIComponent(href.replace(/^workspace:\/\//i,'')).replace(/^~\//,'').replace(/^\.\//,'');
      return '#workspace='+encodeURIComponent(rel);
    }catch(_){
      return '#';
    }
  }
  if(!/^file:\/\//i.test(href)) return href;
  try{
    const path=decodeURIComponent(href.replace(/^file:\/\//i,''));
    return 'api/media?path='+encodeURIComponent(path)+'&inline=1';
  }catch(_){
    return 'api/media?path='+encodeURIComponent(href.replace(/^file:\/\//i,''))+'&inline=1';
  }
}

function _smdFileHref(raw){
  return _smdLinkHref(raw);
}

// Safe renderer: wraps default_renderer with a set_attr hook that validates
// href/src URL schemes inline — no post-hoc DOM-wide querySelectorAll needed.
// Unlike _streamFadeRenderer, this does NOT wrap add_text, so smd adds new
// DOM nodes as plain text nodes (no animation spans). Used on the non-fade
// streaming path to eliminate _sanitizeSmdLinks(assistantBody) O(DOM) scans
// on every token event (#WebUI-perf).
// MEDIA-in-stream fix: also wraps add_text so MEDIA:<ref> tokens that arrive
// mid-turn are converted to inline media elements at insert time, matching
// what the full renderMd() pipeline does on the settled assistant message.
// Without this, streamed prose shows MEDIA:C:\... as literal text until the
// turn settles and the full re-render swaps it for the real <img>.
// SAFETY & CROSS-CHUNK SPLITS (Greptile #1 + #2):
//   1. Prose slices go back to the owning text writer (text nodes or
//      fade spans), NOT through DOMParser — mixed prose with HTML entities /
//      malicious <img onerror> stays as literal text.
//   2. Each MEDIA token's HTML (from _inlineMediaHtmlForRef) is handed
//      to DOMParser one at a time — only trusted markup is parsed.
//   3. A MEDIA prefix split across smd flushes (e.g. "MEDIA:" then
//      "foo.png") is buffered in a per-parser tail buffer and completed
//      on the next add_text call.
const _MEDIA_TAIL_MAX = 4096; // bytes; defensive cap on per-parser buffer

const _SMD_MEDIA_PREFIX = 'MEDIA:';

function _smdMediaPrefixTail(value){
  const text=String(value||'');
  const max=Math.min(_SMD_MEDIA_PREFIX.length,text.length);
  for(let len=max;len>0;len-=1){
    const suffix=text.slice(text.length-len);
    if(_SMD_MEDIA_PREFIX.startsWith(suffix)) return suffix;
  }
  return '';
}

function _smdAppendPlainText(parent, data, text, baseAddText){
  const value=String(text||'');
  if(parent&&parent.appendChild&&typeof document!=='undefined'&&document.createTextNode){
    parent.appendChild(document.createTextNode(value));
    return;
  }
  if(baseAddText) baseAddText(data,value);
}

function _smdMediaWriteText(parent, data, baseAddText, writeText, text){
  if(writeText){
    writeText(parent, data, String(text||''));
    return;
  }
  if(baseAddText) baseAddText(data,String(text||''));
}

function _smdMediaTailSet(tailMap, parser, chunk, parent, baseAddText, data, writeText){
  if(!tailMap||!parser) return;
  if(chunk) tailMap.set(parser, {chunk, parent, baseAddText, data, writeText});
  else tailMap.delete(parser);
}

function _smdMediaTailEntryChunk(entry){
  return entry && typeof entry==='object' && Object.prototype.hasOwnProperty.call(entry,'chunk') ? entry.chunk : entry;
}

function _smdMediaTailSameOwner(entry, parent, baseAddText, writeText){
  return !!entry && entry.parent===parent && entry.baseAddText===baseAddText && entry.writeText===writeText;
}

function _smdMediaRefHasReliableBoundary(rawRef){
  const raw=String(rawRef||'');
  if(/[?#]$/.test(raw)) return false;
  const ref=raw.split(/[?#]/,1)[0];
  return /\.(?:png|jpe?g|gif|webp|bmp|ico|svg|avif|mp4|webm|mov|m4v|mkv|avi|ogv|mp3|wav|ogg|m4a|aac|wma|opus|flac|oga|pdf|html?|csv|diff|patch|excalidraw)$/i.test(ref);
}

function _smdMediaTailFlushEntry(entry){
  const chunk=_smdMediaTailEntryChunk(entry);
  if(!chunk) return;
  const m=/^MEDIA:([^\s\)\]]+)$/.exec(String(chunk));
  const emitted=!!(m && entry && entry.parent && _smdAppendMediaNode(entry.parent, m[1]));
  if(!emitted && entry) _smdMediaWriteText(entry.parent, entry.data, entry.baseAddText, entry.writeText, chunk);
}

function _smdMediaAwareAddText(baseAddText, parent, data, text, tailMap, parser, writeText){
  const value=String(text||'');
  const tails=tailMap||(typeof _SMD_MEDIA_TAIL!=='undefined'&&_SMD_MEDIA_TAIL)||null;
  const writeCurrent=(chunk)=>_smdMediaWriteText(parent, data, baseAddText, writeText, chunk);
  if(!value){
    writeCurrent('');
    return;
  }
  // Pull any pending tail from a previous (split) chunk, then clear it;
  // this call will either complete it, re-buffer it, or flush it as text.
  let leadEntry = tails && parser && tails.get ? tails.get(parser) : null;
  let lead = _smdMediaTailEntryChunk(leadEntry);
  if(lead && !_smdMediaTailSameOwner(leadEntry, parent, baseAddText, writeText)){
    if(tails && parser && tails.delete) tails.delete(parser);
    _smdMediaTailFlushEntry(leadEntry);
    leadEntry=null;
    lead='';
  }else if(lead && tails && parser && tails.delete){
    tails.delete(parser);
  }
  const combined = lead ? lead + value : value;
  // Fast path: no MEDIA tokens in the (possibly combined) string.
  if(!/MEDIA:/.test(combined)){
    const prefixTail=_smdMediaPrefixTail(combined);
    if(prefixTail && tails && parser && prefixTail.length < _MEDIA_TAIL_MAX){
      const stable=combined.slice(0, combined.length-prefixTail.length);
      if(stable) writeCurrent(stable);
      _smdMediaTailSet(tails, parser, prefixTail, parent, baseAddText, data, writeText);
      return;
    }
    writeCurrent(combined);
    return;
  }
  // Walk the combined string, slicing into prose + MEDIA token runs.
  // Prose runs go through the owning text writer. MEDIA tokens go through
  // the single-token DOMParser helper only after a delimiter or
  // reliable filename suffix proves the ref is complete.
  const re=/MEDIA:([^\s\)\]]+)/g;
  let last=0, m;
  let unmatchedTail=null;
  while((m=re.exec(combined))){
    const matchEnd = m.index + m[0].length;
    if(m.index>last){
      const slice = combined.slice(last, m.index);
      writeCurrent(slice);
    }
    if(matchEnd===combined.length && !_smdMediaRefHasReliableBoundary(m[1])){
      const candidate = combined.slice(m.index);
      if(candidate.length < _MEDIA_TAIL_MAX){
        unmatchedTail = candidate;
      } else {
        writeCurrent(candidate);
      }
      last = combined.length;
      break;
    }
    if(!_smdAppendMediaNode(parent, m[1])) writeCurrent(m[0]);
    last = matchEnd;
  }
  // Tail buffer — hold trailing bytes that look like an unterminated
  // MEDIA prefix; flush any prose before the partial MEDIA suffix.
  const rest = combined.slice(last);
  if(rest){
    const tailMatch = /MEDIA:[^\s\)\]]*$/.exec(rest);
    const prefixTail = tailMatch ? '' : _smdMediaPrefixTail(rest);
    const tailValue = tailMatch ? tailMatch[0] : prefixTail;
    if(tailValue && rest.length < _MEDIA_TAIL_MAX){
      const tailStart = tailMatch ? tailMatch.index : rest.length-prefixTail.length;
      if(tailStart>0) writeCurrent(rest.slice(0, tailStart));
      unmatchedTail = tailValue;
    } else {
      writeCurrent(rest);
    }
  }
  if(tails && parser){
    _smdMediaTailSet(tails, parser, unmatchedTail, parent, baseAddText, data, writeText);
  }
}

// Single-token DOM splice. Only ever fed the output of
// _inlineMediaHtmlForRef (trusted markup fragment). Plain text
// goes through baseAddText → createTextNode — NEVER here.
function _smdAppendMediaNode(parent, rawRef){
  if(!parent||!rawRef) return false;
  const mediaHtml = (typeof _inlineMediaHtmlForRef==='function')
    ? _inlineMediaHtmlForRef(String(rawRef))
    : '';
  if(!mediaHtml) return false;
  let host=null;
  try{
    const doc=new DOMParser().parseFromString('<div>'+mediaHtml+'</div>','text/html');
    host=doc.body&&doc.body.firstChild;
  }catch(_){ host=null; }
  if(!host||!host.childNodes||!host.childNodes.length) return false;
  const frag=document.createDocumentFragment();
  while(host.firstChild) frag.appendChild(host.firstChild);
  parent.appendChild(frag);
  _smdScheduleMediaPostProcess(parent);
  return true;
}

function _smdScheduleMediaPostProcess(root){
  if(!root) return;
  if(typeof _postProcessWithAnchorSuppression!=='function'
    && typeof postProcessRenderedMessages!=='function'
    && typeof _applyMediaPlaybackPreferences!=='function') return;
  const run=()=>{
    try{
      if(typeof _postProcessWithAnchorSuppression==='function') _postProcessWithAnchorSuppression(root);
      else if(typeof postProcessRenderedMessages==='function') postProcessRenderedMessages(root);
      if(typeof _applyMediaPlaybackPreferences==='function') _applyMediaPlaybackPreferences(root);
    }catch(_){}
  };
  if(typeof requestAnimationFrame==='function') requestAnimationFrame(run);
  else if(typeof setTimeout==='function') setTimeout(run,0);
  else run();
}

function _smdBindParserIdentity(renderer, parser, el){
  if(renderer&&renderer.data) renderer.data.parser=parser;
  if(el) el.__smdParser=parser;
}

function _smdClearParserIdentity(el, parser){
  if(!el || (parser && el.__smdParser!==parser)) return;
  try{delete el.__smdParser;}catch(_){el.__smdParser=null;}
}
