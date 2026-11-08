function sorted(value) {
  if(Array.isArray(value))return value.map(sorted);
  if(value && typeof value==='object')return Object.fromEntries(Object.keys(value).sort().map(k=>[k,sorted(value[k])]));
  return value;
}
function handoffComment(h) {
  const literal=s=>s.replaceAll('@','＠').replace(/([\\`*_{}\[\]<>()#!|~])/g,'\\$1');
  const title=s=>s[0].toUpperCase()+s.slice(1);
  return ('Engineering handoff '+h.id+'\n\n'+title(h.sender)+' → '+title(h.recipient)+'\n\n'+literal(h.summary)+
    '\n\nRequested action: '+literal(h.requested_action)+'\n\nPinned engineering context:\n```json\n'+
    JSON.stringify(sorted(h.binding),null,2)+'\n```\n\nEvidence references:\n```json\n'+
    JSON.stringify(sorted(h.references),null,2)+'\n```\n\nKnown limitations: '+
    literal('['+h.limitations.map(x=>JSON.stringify(x)).join(', ')+']')+
    '\n\nThis handoff supplies context and responsibility. It grants no new execution, spending, architecture approval, merge or deployment permission.').replaceAll('@','＠');
}
function validateHandoff(h,policy,role) {
  const expected=['contract','id','organization_id','sender','recipient','sender_app_user_id','recipient_app_user_id',
    'source_session_id','issue_id','binding','parent_handoff_id','depth','summary','requested_action','references',
    'limitations','execution_authority_granted','human_approval_inferred','comment_id'].sort();
  const uuid=x=>typeof x==='string'&&/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(x);
  const bounded=(x,n)=>typeof x==='string'&&!!x.trim()&&!x.includes('\0')&&new TextEncoder().encode(x).length<=n;
  const recipient=role==='jarvis'?'codex':'jarvis';
  if(!h || JSON.stringify(Object.keys(h).sort())!==JSON.stringify(expected) || h.contract!=='native-agent-handoff.v1' ||
      h.organization_id!==policy.organization_id || h.sender!==role || h.recipient!==recipient ||
      h.sender_app_user_id!==policy.agents[role] || h.recipient_app_user_id!==policy.agents[recipient] ||
      ![h.id,h.comment_id,h.source_session_id,h.issue_id].every(uuid) ||
      (h.parent_handoff_id!==null&&!uuid(h.parent_handoff_id)) || !Number.isInteger(h.depth) || h.depth<1 || h.depth>4 ||
      !bounded(h.summary,8192) || !bounded(h.requested_action,4096) || !Array.isArray(h.references) || h.references.length>32 ||
      !Array.isArray(h.limitations) || h.limitations.length>32 || !h.limitations.every(x=>bounded(x,4096)) ||
      h.execution_authority_granted!==false || h.human_approval_inferred!==false ||
      !policy.issues[h.issue_id] || JSON.stringify(sorted(h.binding))!==JSON.stringify(sorted(policy.issues[h.issue_id])) ||
      new TextEncoder().encode(JSON.stringify(h)).length>32768)throw new Error('Exact installed handoff context required');
  for(const r of h.references)if(!r || JSON.stringify(Object.keys(r).sort())!==JSON.stringify(['id','namespace','sha256']) ||
    !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$/.test(r.namespace) || !bounded(r.id,512) ||
    (r.sha256!==null&&!/^[0-9a-f]{64}$/.test(r.sha256)))throw new Error('Exact handoff evidence reference required');
  return {intent:h,comment_body:handoffComment(h)};
}
