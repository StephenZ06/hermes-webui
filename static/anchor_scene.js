// Anchor activity-scene helpers for the live chat stream.
//
// Moved out of messages.js's attachLiveStream() closure: these build, compare
// and settle activity_scene_v1 rows (see static/assistant_turn_anchors.js for
// the Anchor registry and projection) without touching per-stream state, so
// one top-level copy serves every stream. Loaded before messages.js
// (index.html, sw.js precache).

function _anchorSceneActiveMode(){
  const normalize=value=>value==='transparent_stream'||value==='compact_worklog'||value==='hide_all_activity'?value:'';
  if(typeof window!=='undefined'){
    if(typeof window.chatActivityMode==='function'){
      try{
        const mode=normalize(window.chatActivityMode());
        if(mode) return mode;
      }catch(_){}
    }
    const displayMode=normalize(window._chatActivityDisplayMode);
    if(displayMode) return displayMode;
    if(window._transparentStream) return 'transparent_stream';
  }
  return 'compact_worklog';
}

function _anchorSceneRowDisplayHintForMode(row, sceneMode){
  const hints=row&&typeof row==='object'&&row.display_hints&&typeof row.display_hints==='object'
    ? row.display_hints
    : null;
  if(sceneMode==='transparent_stream') return (hints&&hints.transparent_stream)||'chronological_activity';
  if(sceneMode==='compact_worklog') return (hints&&hints.compact_worklog)||row.display_hint||'activity_row';
  if(sceneMode==='hide_all_activity') return (hints&&hints.hidden_activity)||'hidden_activity';
  return row&&row.display_hint||'activity_row';
}

function _anchorSceneMessageRef(message){
  if(!message||typeof message!=='object') return '';
  let content=message.content||'';
  if(Array.isArray(content)){
    try{
      content=content.map(part=>{
        if(part&&typeof part==='object') return part.text||part.content||part.input_text||'';
        return String(part||'');
      }).join('\n');
    }catch(_){ content=''; }
  }
  const payload={
    role:String(message.role||''),
    content:String(content||'').replace(/\s+/g,' ').trim(),
    timestamp:message._ts||message.timestamp||'',
  };
  return JSON.stringify(payload);
}

function _anchorSceneMessageText(message){
  if(!message||typeof message!=='object') return '';
  let content=message.content||'';
  if(Array.isArray(content)){
    try{
      content=content.map(part=>{
        if(part&&typeof part==='object') return part.text||part.content||part.input_text||'';
        return String(part||'');
      }).join('\n');
    }catch(_){ content=''; }
  }
  return typeof content==='string'?content:String(content||'');
}

function _anchorSceneContentText(part){
  if(part===undefined||part===null) return '';
  if(typeof part==='string') return part;
  if(typeof part!=='object') return String(part||'');
  return String(part.text||part.content||part.input_text||part.output_text||part.thinking||part.reasoning||part.summary||'');
}

function _anchorSceneContentVisibleText(part){
  if(part===undefined||part===null) return '';
  if(typeof part==='string') return part;
  if(typeof part!=='object') return String(part||'');
  const partType=String(part.type||'');
  if(partType==='thinking'||partType==='reasoning') return '';
  const contentText=(partType==='text'||partType==='input_text'||partType==='output_text')?part.content:'';
  return String(part.text||part.input_text||part.output_text||contentText||'');
}

function _anchorSceneMessageHasContentToolUse(message){
  return !!(message&&Array.isArray(message.content)&&message.content.some(part=>part&&typeof part==='object'&&part.type==='tool_use'));
}

function _anchorSceneFinalAnswerText(message){
  if(!_anchorSceneMessageHasContentToolUse(message)) return _anchorSceneMessageText(message);
  const content=Array.isArray(message.content)?message.content:[];
  let lastToolIndex=-1;
  for(let i=0;i<content.length;i+=1){
    const part=content[i];
    if(part&&typeof part==='object'&&part.type==='tool_use') lastToolIndex=i;
  }
  const tailText=content.slice(lastToolIndex+1)
    .map(part=>_anchorSceneContentVisibleText(part))
    .filter(text=>_anchorSceneCleanText(text))
    .join('\n');
  return _anchorSceneCleanText(tailText)?tailText:'';
}

function _anchorSceneCleanText(value){
  return String(value||'').replace(/\s+/g,' ').trim();
}

function _anchorSceneTextKey(value){
  return _anchorSceneCleanText(value).toLowerCase();
}

function _anchorSceneSafePayload(value){
  if(value===undefined) return undefined;
  if(value===null||typeof value!=='object') return value;
  try{
    return JSON.parse(JSON.stringify(value));
  }catch(_){
    return String(value);
  }
}

function _anchorSceneToolId(tool){
  return String(tool&&(tool.tid||tool.id||tool.tool_call_id||tool.tool_use_id||tool.call_id)||'').trim();
}

function _anchorSceneToolName(tool){
  const fn=tool&&tool.function&&typeof tool.function==='object'?tool.function:{};
  return String(tool&&(tool.name||tool.tool_name)||fn.name||'tool').trim()||'tool';
}

function _anchorSceneToolArgs(tool){
  if(!tool||typeof tool!=='object') return {};
  if(tool.args&&typeof tool.args==='object') return _anchorSceneSafePayload(tool.args)||{};
  if(tool.input&&typeof tool.input==='object') return _anchorSceneSafePayload(tool.input)||{};
  const fn=tool.function&&typeof tool.function==='object'?tool.function:{};
  if(typeof fn.arguments==='string'&&fn.arguments.trim()){
    try{
      const parsed=JSON.parse(fn.arguments);
      return parsed&&typeof parsed==='object'?_anchorSceneSafePayload(parsed):{};
    }catch(_){}
  }
  return {};
}

function _anchorSceneContentTool(part){
  if(!part||typeof part!=='object') return {};
  const fn=part.function&&typeof part.function==='object'?part.function:{};
  return {
    id:part.id||part.tid||part.tool_call_id||part.tool_use_id||part.call_id,
    tid:part.tid||part.id||part.tool_call_id||part.tool_use_id||part.call_id,
    tool_call_id:part.tool_call_id,
    tool_use_id:part.tool_use_id,
    call_id:part.call_id,
    name:part.name||part.tool_name||fn.name||'tool',
    tool_name:part.tool_name,
    args:part.args,
    input:part.input,
    function:part.function,
    command:part.command||part.raw_command||part.original_command||part.display_command,
    preview:part.preview||part.summary,
    snippet:part.snippet||part.result||part.output,
    result:part.result,
    output:part.output,
    is_error:part.is_error,
    error:part.error,
    duration:part.duration,
    started_at:part.started_at,
  };
}

function _anchorSceneStringPayload(value){
  if(value===undefined||value===null) return '';
  if(typeof value==='string') return value;
  try{
    return JSON.stringify(value);
  }catch(_){
    return String(value);
  }
}

function _anchorSceneToolRowName(row){
  const tool=row&&row.tool&&typeof row.tool==='object'?row.tool:{};
  const payload=row&&row.payload&&typeof row.payload==='object'?row.payload:{};
  return String(tool.name||payload.name||'tool').trim().toLowerCase();
}

function _anchorSceneToolRowId(row){
  const tool=row&&row.tool&&typeof row.tool==='object'?row.tool:{};
  const payload=row&&row.payload&&typeof row.payload==='object'?row.payload:{};
  return String(
    (row&&row.tool_call_id)||
    tool.id||
    tool.tid||
    tool.tool_call_id||
    tool.tool_use_id||
    tool.call_id||
    payload.tid||
    payload.id||
    ''
  ).trim();
}

function _anchorSceneToolRowsHaveNonConflictingIds(existing, incoming){
  const existingId=_anchorSceneToolRowId(existing);
  const incomingId=_anchorSceneToolRowId(incoming);
  return !existingId||!incomingId||existingId===incomingId;
}

function _anchorSceneToolRowsHaveDifferentExplicitIds(existing, incoming){
  const existingId=_anchorSceneToolRowId(existing);
  const incomingId=_anchorSceneToolRowId(incoming);
  return !!existingId&&!!incomingId&&existingId!==incomingId;
}

function _anchorSceneToolRowStartedAt(row){
  const tool=row&&row.tool&&typeof row.tool==='object'?row.tool:{};
  const payload=row&&row.payload&&typeof row.payload==='object'?row.payload:{};
  const value=tool.started_at!==undefined&&tool.started_at!==null&&tool.started_at!==''?tool.started_at:payload.started_at;
  return value!==undefined&&value!==null&&value!==''?String(value):'';
}

function _anchorSceneToolRowsHaveSameStartedAt(existing, incoming){
  const existingStartedAt=_anchorSceneToolRowStartedAt(existing);
  const incomingStartedAt=_anchorSceneToolRowStartedAt(incoming);
  return !!existingStartedAt&&!!incomingStartedAt&&existingStartedAt===incomingStartedAt;
}

function _anchorSceneToolRowBodyText(row){
  const tool=row&&row.tool&&typeof row.tool==='object'?row.tool:{};
  const payload=row&&row.payload&&typeof row.payload==='object'?row.payload:{};
  for(const value of [tool.snippet,payload.snippet,tool.output,payload.output,tool.result,payload.result,tool.preview,payload.preview]){
    const text=_anchorSceneStringPayload(value).trim();
    if(text) return text;
  }
  return '';
}

function _anchorSceneToolRowsHaveCompatibleBody(existing, incoming){
  const existingBody=_anchorSceneToolRowBodyText(existing);
  const incomingBody=_anchorSceneToolRowBodyText(incoming);
  return !!existingBody&&!!incomingBody&&(
    existingBody===incomingBody||
    existingBody.startsWith(incomingBody)||
    incomingBody.startsWith(existingBody)
  );
}

function _anchorSceneToolRowsHaveCompatibleNames(existing, incoming){
  const existingName=_anchorSceneToolRowName(existing);
  const incomingName=_anchorSceneToolRowName(incoming);
  return !existingName||!incomingName||existingName==='tool'||incomingName==='tool'||existingName===incomingName;
}

function _anchorSceneToolRowArgs(row){
  const tool=row&&row.tool&&typeof row.tool==='object'?row.tool:{};
  const payload=row&&row.payload&&typeof row.payload==='object'?row.payload:{};
  const args=(tool.args&&typeof tool.args==='object'&&!Array.isArray(tool.args))?tool.args:payload.args;
  return args&&typeof args==='object'&&!Array.isArray(args)?args:null;
}

function _anchorSceneObjectContainsSubset(base, subset){
  if(!base||!subset||typeof base!=='object'||typeof subset!=='object') return false;
  const stableStringify=(candidate)=>{
    const normalize=(value)=>{
      if(!value||typeof value!=='object') return value;
      if(Array.isArray(value)) return value.map(normalize);
      const normalized={};
      Object.keys(value).sort().forEach((key)=>{normalized[key]=normalize(value[key]);});
      return normalized;
    };
    try{return JSON.stringify(normalize(candidate));}catch(_){return JSON.stringify(candidate);}
  };
  for(const [key,value] of Object.entries(subset)){
    if(!Object.prototype.hasOwnProperty.call(base,key)) return false;
    if(stableStringify(base[key])!==stableStringify(value)) return false;
  }
  return true;
}

function _anchorSceneToolRowsHaveCompatibleInvocation(existing, incoming){
  const existingTool=existing&&existing.tool&&typeof existing.tool==='object'?existing.tool:{};
  const incomingTool=incoming&&incoming.tool&&typeof incoming.tool==='object'?incoming.tool:{};
  const existingPayload=existing&&existing.payload&&typeof existing.payload==='object'?existing.payload:{};
  const incomingPayload=incoming&&incoming.payload&&typeof incoming.payload==='object'?incoming.payload:{};
  const existingCommand=_anchorSceneStringPayload(existingTool.command||existingPayload.command).trim();
  const incomingCommand=_anchorSceneStringPayload(incomingTool.command||incomingPayload.command).trim();
  if(existingCommand&&incomingCommand) return existingCommand===incomingCommand;
  const existingArgs=_anchorSceneToolRowArgs(existing);
  const incomingArgs=_anchorSceneToolRowArgs(incoming);
  if(!existingArgs||!incomingArgs||!Object.keys(existingArgs).length||!Object.keys(incomingArgs).length) return false;
  return _anchorSceneObjectContainsSubset(existingArgs,incomingArgs)||_anchorSceneObjectContainsSubset(incomingArgs,existingArgs);
}

function _anchorSceneToolRowHasInvocationEvidence(row){
  const tool=row&&row.tool&&typeof row.tool==='object'?row.tool:{};
  const payload=row&&row.payload&&typeof row.payload==='object'?row.payload:{};
  const command=_anchorSceneStringPayload(tool.command||payload.command).trim();
  const args=_anchorSceneToolRowArgs(row);
  return !!command||!!(args&&Object.keys(args).length);
}

function _anchorSceneToolRowsCanNameMatch(existing, incoming){
  if(!_anchorSceneToolRowsHaveCompatibleNames(existing,incoming)) return false;
  if(_anchorSceneToolRowHasInvocationEvidence(existing)&&_anchorSceneToolRowHasInvocationEvidence(incoming)){
    return _anchorSceneToolRowsHaveCompatibleInvocation(existing,incoming);
  }
  return true;
}

function _anchorSceneMatchingContentToolRow(contentToolRows, incomingRow, ordinal, usedRows, incomingTotal, idFlexibleRows){
  if(!Array.isArray(contentToolRows)||!incomingRow) return null;
  const incomingTid=incomingRow.tool_call_id||(incomingRow.tool&&incomingRow.tool.id);
  for(const row of contentToolRows){
    if(!row||usedRows.has(row)) continue;
    const tid=row.tool_call_id||(row.tool&&row.tool.id);
    if(tid&&incomingTid&&tid===incomingTid) return row;
  }
  if(contentToolRows.length===1&&Number(incomingTotal)===1){
    const onlyRow=contentToolRows[0];
    if(onlyRow&&!usedRows.has(onlyRow)&&_anchorSceneToolRowsCanNameMatch(onlyRow,incomingRow)) return onlyRow;
  }
  const availableRows=contentToolRows.filter(row=>row&&!usedRows.has(row));
  if(availableRows.length===1){
    if(Number(incomingTotal)===1&&_anchorSceneToolRowsCanNameMatch(availableRows[0],incomingRow)) return availableRows[0];
    if(
      _anchorSceneToolRowsHaveCompatibleNames(availableRows[0],incomingRow)&&
      _anchorSceneToolRowsHaveCompatibleInvocation(availableRows[0],incomingRow)
    ) return availableRows[0];
  }
  const reusableRows=contentToolRows.filter(row=>row&&usedRows.has(row));
  if(
    reusableRows.length===1&&
    Number(incomingTotal)===1&&
    (
      (
        _anchorSceneToolRowId(reusableRows[0])&&
        _anchorSceneToolRowId(incomingRow)&&
        _anchorSceneToolRowId(reusableRows[0])===_anchorSceneToolRowId(incomingRow)
      )||
      (
        idFlexibleRows&&
        idFlexibleRows.has(reusableRows[0])&&
        _anchorSceneToolRowsHaveSameStartedAt(reusableRows[0],incomingRow)&&
        _anchorSceneToolRowsHaveCompatibleBody(reusableRows[0],incomingRow)
      )
    )&&
    _anchorSceneToolRowsHaveCompatibleNames(reusableRows[0],incomingRow)&&
    _anchorSceneToolRowsHaveCompatibleInvocation(reusableRows[0],incomingRow)
  ) return reusableRows[0];
  for(const row of contentToolRows){
    if(!row||usedRows.has(row)) continue;
    const tid=row.tool_call_id||(row.tool&&row.tool.id);
    if(!tid&&!incomingTid&&_anchorSceneToolRowsCanNameMatch(row,incomingRow)) return row;
  }
  return null;
}

function _anchorSceneMessageReasoningText(message){
  if(!message||typeof message!=='object') return '';
  return String(message.reasoning||message._reasoning||message.reasoning_content||message.thinking||'');
}

function _anchorSceneExistingRowKey(row){
  if(!row||typeof row!=='object') return '';
  if(row.role==='tool'){
    const tool=row.tool&&typeof row.tool==='object'?row.tool:{};
    return `tool:${row.tool_call_id||tool.id||tool.tid||tool.tool_call_id||tool.tool_use_id||tool.call_id||row.row_id||''}`;
  }
  if(row.role==='prose'||row.role==='thinking') return `${row.role}:${_anchorSceneTextKey(row.text)}`;
  return `${row.role||row.kind}:${row.source_event_type||''}:${row.status||''}:${row.row_id||''}`;
}

function _anchorSceneRowHasLiveIdentity(row){
  if(!row||typeof row!=='object') return false;
  const identity=row.identity&&typeof row.identity==='object'?row.identity:{};
  const values=[row.row_id,row.local_id,row.event_id,identity.local_id,identity.event_id];
  if(values.some(value=>String(value||'').startsWith('live-'))) return true;
  // Provider tool-call IDs do not use the live prefix. A stream owner without
  // a settled assistant index still identifies a projected live row.
  const group=row.group&&typeof row.group==='object'?row.group:{};
  const hasStreamOwner=!!(row.stream_id||row.run_id||identity.stream_id||identity.run_id);
  const hasAssistantMessageIndex=group.assistant_msg_idx!==undefined&&group.assistant_msg_idx!==null;
  return hasStreamOwner&&!hasAssistantMessageIndex;
}

function _anchorSceneMessageRowsHaveThinking(messageRows){
  if(!(messageRows instanceof Map)) return false;
  for(const bucket of messageRows.values()){
    if(Array.isArray(bucket)&&bucket.some(row=>row&&row.role==='thinking')) return true;
  }
  return false;
}

function _anchorSceneSettleLiveRunningRow(row, hasSettledThinking){
  if(!row||typeof row!=='object') return row;
  if(row.role!=='thinking'&&row.role!=='prose'&&row.role!=='tool') return row;
  if(String(row.status||'').toLowerCase()!=='running') return row;
  if(!_anchorSceneRowHasLiveIdentity(row)) return row;
  if(row.role==='thinking'&&hasSettledThinking) return null;
  const sealed={...row,status:'completed'};
  if(row.payload&&typeof row.payload==='object'){
    sealed.payload={...row.payload,status:'completed'};
    if(row.role==='tool') sealed.payload.done=true;
  }
  if(row.role==='tool'&&row.tool&&typeof row.tool==='object'){
    sealed.tool={...row.tool,done:true};
  }
  return sealed;
}

function _anchorSceneRowLooksLikeFinalAnswer(rowTextKey, finalKey){
  if(!rowTextKey||!finalKey) return false;
  if(rowTextKey===finalKey) return true;
  // #4587: align with the renderer's _anchorSceneProseMatchesFinalAnswer — a
  // prefix-like overlap only counts as "the final answer" (and is dropped from
  // the scene) when it's a NEAR-complete match (ratio>=0.9). A shorter
  // intermediate-prose row that merely happens to be a prefix of the final
  // answer is legitimate progress narration and must be PRESERVED, not dropped.
  if(!(finalKey.startsWith(rowTextKey)||rowTextKey.startsWith(finalKey))) return false;
  const shorter=Math.min(rowTextKey.length,finalKey.length);
  const longer=Math.max(rowTextKey.length,finalKey.length);
  return shorter>=80&&longer>0&&(shorter/longer)>=0.9;
}

function _anchorSceneRowTextOverlapsExisting(rowTextKey, seenTextKeys){
  if(!rowTextKey||!Array.isArray(seenTextKeys)) return false;
  for(const existing of seenTextKeys){
    if(!existing) continue;
    if(rowTextKey===existing) return true;
    const minLen=Math.min(rowTextKey.length,existing.length);
    if(minLen>=80&&(rowTextKey.includes(existing)||existing.includes(rowTextKey))) return true;
  }
  return false;
}

function _anchorSceneTurnDurationForSettlement(lastAsst, base){
  if(lastAsst&&lastAsst._turnDuration!==undefined&&lastAsst._turnDuration!==null) return lastAsst._turnDuration;
  if(base&&base.turn_duration!==undefined&&base.turn_duration!==null) return base.turn_duration;
  const session=(typeof S!=='undefined'&&S&&S.session)?S.session:null;
  // The `pending_started_at` fallback below is the START of an IN-FLIGHT turn.
  // For a SETTLED turn that recorded no live duration, computing
  // `now - pending_started_at` is wrong: pending_started_at is either stale
  // (left over from an earlier turn / a session that sat idle) or belongs to a
  // different, still-pending turn — which rendered a bogus "Processed 15h 32m"
  // on fresh conversations (#4930). Only use it while a turn is actually in
  // flight; otherwise show no duration rather than a fabricated one.
  const turnInFlight=!!(session&&(session.active_stream_id||session.pending_user_message));
  if(!turnInFlight) return undefined;
  const candidates=[
    session&&session.pending_started_at,
    session&&session.active_started_at,
    session&&session.run_started_at,
    session&&session.started_at,
  ];
  for(const raw of candidates){
    const started=Number(raw);
    if(Number.isFinite(started)&&started>0){
      const elapsed=(Date.now()/1000)-started;
      if(Number.isFinite(elapsed)&&elapsed>=0) return elapsed;
    }
  }
  return undefined;
}

function _anchorSceneMessageOffsetForPersist(){
  const raw=(typeof _oldestIdx!=='undefined')?_oldestIdx:0;
  const offset=Number(raw);
  return Number.isFinite(offset)&&offset>0?Math.floor(offset):0;
}

function _anchorSceneAbsoluteMessageIndexForPersist(messageIndex, offset){
  const idx=Number(messageIndex);
  const off=Number(offset);
  if(!Number.isFinite(idx)||idx<0) return messageIndex;
  return idx+(Number.isFinite(off)&&off>0?Math.floor(off):0);
}

function _anchorSceneHasWorklogWorthyRows(scene){
  if(scene&&scene.mode==='hide_all_activity') return false;
  if(typeof window!=='undefined'&&typeof window.isFinalAnswerOnlyMode==='function'&&window.isFinalAnswerOnlyMode()) return false;
  // A worklog (the collapsible "已处理 …" rail) is only meaningful when the turn
  // actually DID worklog-worthy work — a tool call, a thinking/reasoning pass, or
  // a compression lifecycle card. A turn that only streamed prose (e.g. a long
  // plain-text answer, or a degeneration burst that flooded the body with repeated
  // tokens) projects an activity scene whose rows are ALL `prose`/`terminal`. Folding
  // such a turn into a collapsed worklog hides the whole answer and, at STREAM_DONE,
  // shrinks the transcript by the full streamed height → the browser clamps a
  // bottom-pinned viewport back to the top (the "jump back" report). Require at least
  // one genuinely worklog-worthy row before promoting the turn to a worklog.
  const rows=Array.isArray(scene&&scene.activity_rows)?scene.activity_rows:[];
  for(const row of rows){
    if(!row||typeof row!=='object') continue;
    const role=String(row.role||'');
    if(role==='tool'||role==='thinking') return true;
    if(role==='lifecycle'){
      const source=String(row.source_event_type||'');
      // compression cards are worklog-worthy; a bare terminal/done lifecycle is not.
      if(source==='compressing'||source==='compressed') return true;
    }
  }
  return false;
}

function _anchorSceneHasOwnedOutcomes(scene){
  return !!(
    (Array.isArray(scene&&scene.artifacts)&&scene.artifacts.length)
    || (Array.isArray(scene&&scene.side_effects)&&scene.side_effects.length)
  );
}

function _sourceEventTypeForSnapshotAnchorRow(row){
  const source=String(row&&row.source_event_type||'').trim();
  if(source&&source!=='runtime_journal_snapshot') return source;
  const role=String(row&&row.role||'').trim();
  const kind=String(row&&row.kind||'').trim();
  if(role==='prose'||kind==='process_prose') return 'token';
  if(role==='thinking'||kind==='reasoning') return 'reasoning';
  if(role==='tool') return row&&row.status==='running'?'tool':'tool_complete';
  // Terminal statuses are done/cancel/error/apperror — never invent a
  // compression start from a running terminal row (false "Compressing context").
  if(role==='terminal'||kind==='terminal_status'){
    const termStatus=String(row&&row.status||'').trim().toLowerCase();
    if(termStatus==='cancelled'||termStatus==='canceled'||termStatus==='interrupted') return 'cancel';
    if(termStatus==='error'||termStatus==='failed'||termStatus==='errored') return 'error';
    if(termStatus==='running') return '';
    return 'done';
  }
  // lifecycle_status is shared by compressing + compressed. Prefer explicit
  // cues; do not default every lifecycle row to a running compress divider.
  if(role==='lifecycle'||kind==='lifecycle_status'){
    const phase=String(row&&(row.phase||row.status)||'').trim().toLowerCase();
    const text=String(row&&(row.text||row.message||row.label)||'').trim().toLowerCase();
    if(
      phase==='done'||phase==='completed'||phase==='compressed'
      || text.includes('auto-compressed')
      || text.includes('compression finished')
      || (text.includes('compressed')&&!text.includes('compressing'))
    ) return 'compressed';
    if(
      phase==='running'||phase==='compressing'
      || text.includes('compressing context')
      || text.includes('compacting context')
      || text.includes('preflight compression')
      || text.includes('pre-api compression')
      || text.includes('context too large')
      || text.includes('compression attempt')
      || (text.includes('compressing')&&!text.includes('skipping'))
    ) return 'compressing';
    return '';
  }
  return '';
}

function _isHistoricalAnchorActivityScene(scene){
  if(!scene||typeof scene!=='object') return false;
  const identity=scene.identity&&typeof scene.identity==='object'?scene.identity:null;
  const turnId=identity&&typeof identity.turn_id==='string'?identity.turn_id:'';
  return turnId.indexOf('historical:')===0;
}
