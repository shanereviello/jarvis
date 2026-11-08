// Pure admission for n8n Code nodes. The authenticated webhook node is mandatory.
// Policy is installed by the renderer, never supplied by a webhook or model.
function admit(input, policy, now = Date.now()) {
  const uuid = value => {
    if (typeof value !== 'string' ||
        !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value)) {
      throw new Error('canonical UUID required');
    }
    return value;
  };
  const text = value => {
    if (typeof value !== 'string' || !value.trim() || value.includes('\0') ||
        new TextEncoder().encode(value).length > 65536) throw new Error('bounded prompt required');
    return value;
  };
  const headers = Object.fromEntries(Object.entries(input.headers || {}).map(([k,v]) => [k.toLowerCase(),v]));
  if (headers['x-rras-codex-verified'] !== 'v1') throw new Error('trusted Codex ingress required');
  if (!/^[0-9a-f]{64}$/.test(headers['x-rras-codex-body-sha256'] || '')) throw new Error('verified raw-body digest required');
  const delivery = uuid(headers['linear-delivery']);
  const body = input.body;
  if (!body || body.type !== 'AgentSessionEvent' || !['created','prompted'].includes(body.action) ||
      typeof body.webhookTimestamp !== 'number' || !Number.isFinite(body.webhookTimestamp) ||
      Math.abs(now-body.webhookTimestamp) > 60000) throw new Error('fresh directed agent event required');
  if (body.organizationId !== policy.organization_id) throw new Error('wrong organization');
  // An app-specific signature and ingress route identify the receiving app.
  // Validate optional payload actor/client fields whenever present; they are not
  // assumed to exist in all native payload versions.
  for (const [field, expected] of [['appUserId',policy.app_user_id],['oauthClientId',policy.oauth_client_id]]) {
    if (body[field] != null && body[field] !== expected) throw new Error('wrong receiving app');
  }
  const session = body.agentSession || {};
  const sessionId = uuid(session.id);
  if (session.organizationId != null && session.organizationId !== policy.organization_id) throw new Error('wrong session organization');
  if (session.appUserId != null && session.appUserId !== policy.app_user_id) throw new Error('wrong session app');
  const nestedIssue = session.issue?.id || null;
  const flatIssue = session.issueId || null;
  if (nestedIssue && flatIssue && nestedIssue !== flatIssue) throw new Error('conflicting issue');
  const issue = uuid(nestedIssue || flatIssue);
  if (!Object.hasOwn(policy.issues,issue)) throw new Error('unmapped issue');
  const activity = body.agentActivity || {};
  const signal = activity.signal == null ? null : activity.signal;
  if (signal != null && !['stop','continue'].includes(signal)) throw new Error('unsupported signal');
  let source, message, actor = null, responsibleHuman = null, originComment = null;
  if (body.action === 'created') {
    source = 'created:'+sessionId;
    message = text(body.promptContext);
    responsibleHuman = session.creatorId || session.creator?.id || null;
    if (responsibleHuman != null) uuid(responsibleHuman);
    if (policy.agent_actor_ids.includes(responsibleHuman)) throw new Error('invalid responsible human');
    originComment = session.sourceCommentId || session.commentId || session.sourceComment?.id || session.comment?.id || null;
    if (originComment != null) uuid(originComment);
  } else {
    if (activity.agentSessionId != null && activity.agentSessionId !== sessionId) throw new Error('wrong activity session');
    if (activity.content?.type != null && activity.content.type !== 'prompt') throw new Error('only user prompts admitted');
    actor = activity.userId || activity.user?.id || null;
    if (actor == null) throw new Error('actual directed prompt actor required');
    source = 'prompt:'+uuid(activity.id);
    message = signal === 'stop' ? 'Stop requested for this agent session.' :
      text(activity.content?.body || activity.body);
  }
  if (actor != null) uuid(actor);
  if (policy.agent_actor_ids.includes(actor)) throw new Error('agent echo requires an explicit correlated handoff');
  const envelope = {
    contract:'codex-admitted-event.v1', organization_id:policy.organization_id,
    app_user_id:policy.app_user_id, session_id:sessionId, issue_id:issue,
    source_key:source, source_actor_id:actor, responsible_human_id:responsibleHuman, origin_comment_id:originComment, message, signal,
    binding:policy.issues[issue], action:body.action
  };
  // Canonical content is used for SQL semantic replay checking, independent of
  // delivery timestamp/order. The edge verified the unchanged raw request body.
  const canonical = value => Array.isArray(value) ? value.map(canonical) :
    value && typeof value === 'object' ?
      Object.fromEntries(Object.keys(value).sort().map(k=>[k,canonical(value[k])])) : value;
  return {delivery_id:delivery, envelope, canonical:JSON.stringify(canonical(envelope)),
    raw_body_sha256:headers['x-rras-codex-body-sha256']};
}
