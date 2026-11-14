// Append after n8n_codex_admission.js in a reviewed, authenticated workflow.
// This is a planning envelope only; the execution runtime must reject it.
function admitPlanning(input, policy, now = Date.now()) {
  if (!policy || policy.planning_enabled !== true || !policy.issues ||
      typeof policy.issues !== 'object') throw new Error('planning is not configured');
  const session=input?.body?.agentSession || {};
  const nested=session.issue?.id || null, flat=session.issueId || null;
  if (nested && flat && nested!==flat) throw new Error('conflicting issue');
  const issue=nested || flat;
  if (typeof issue !== 'string' || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(issue))
    throw new Error('explicit issue required');
  // Existing mapped issues continue on their established dispatch route.
  if (Object.hasOwn(policy.issues,issue)) throw new Error('existing execution issue');
  const issues=Object.assign(Object.create(null),policy.issues);
  issues[issue]={planning_only:true};
  const admitted=admit(input,{...policy,issues},now);
  const envelope={...admitted.envelope,contract:'codex-planning-event.v1',mode:'planning'};
  delete envelope.binding;
  // The native origin/project/team and explicit scope are verified by the
  // following trusted read, before any planning runtime can be launched.
  const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value==='object' ?
    Object.fromEntries(Object.keys(value).sort().map(k=>[k,canonical(value[k])])) : value;
  return {...admitted,envelope,canonical:JSON.stringify(canonical(envelope))};
}

function admitCodexRoute(input, policy, now = Date.now()) {
  const session=input?.body?.agentSession || {};
  const nested=session.issue?.id || null,flat=session.issueId || null;
  if (nested && flat && nested!==flat) throw new Error('conflicting issue');
  const issue=nested || flat;
  if (typeof issue!=='string' || !policy || !policy.issues || typeof policy.issues!=='object')
    throw new Error('exact issue and configured policy required');
  return Object.hasOwn(policy.issues,issue) ?
    {route:'execution',...admit(input,policy,now)} : {route:'planning',...admitPlanning(input,policy,now)};
}
