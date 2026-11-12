// Input is supplied by the verified ingress and the fixed native Linear read,
// never by model-authored text. This verifier grants planning only.
function planningOriginQuery(envelope, policy) {
  const uuid = x => typeof x === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(x);
  if (!envelope || !policy || !uuid(envelope.session_id) || !uuid(policy.app_user_id)) throw new Error('exact native session required');
  const actor=envelope.source_actor_id || envelope.responsible_human_id || policy.app_user_id;
  if (!uuid(actor)) throw new Error('exact native actor required');
  return {query:'query PlanningNativeOrigin($id:String!,$actor:String!){viewer{id organization{id}} '+
    'sourceActor:user(id:$actor){id app} agentSession(id:$id){id sourceMetadata appUser{id} '+
    'issue{id team{id} project{id url}} creator{id app} '+
    'comment{id user{id app}} sourceComment{id user{id app}}}}',
    variables:{id:envelope.session_id,actor}};
}

function planningIssueQuery(issueId) {
  if (typeof issueId !== 'string' || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(issueId))
    throw new Error('exact native issue required');
  return {query:'query PlanningNativeIssue($id:String!){viewer{id organization{id}} issue(id:$id){id identifier url team{id} project{id}}}',
    variables:{id:issueId}};
}

function verifyPlanningOrigin(envelope, reply, policy, resolution) {
  const deny = () => ({permitted:false, human_approval_inferred:false});
  const uuid = x => typeof x === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(x);
  if (!envelope || !reply || !policy || !resolution || !['jarvis','codex'].includes(envelope.agent) ||
      !['created','prompted'].includes(envelope.action) || !uuid(envelope.session_id) || !uuid(envelope.issue_id) ||
      !uuid(policy.organization_id) || !policy.agents || !uuid(policy.agents.jarvis) || !uuid(policy.agents.codex) ||
      policy.agents.jarvis === policy.agents.codex || !Array.isArray(policy.team_ids) || !Array.isArray(policy.scopes)) return deny();
  const d=reply.body?.data, session=d?.agentSession, issue=session?.issue, project=issue?.project;
  if (reply.statusCode!==200 || reply.body?.errors || d?.viewer?.id!==policy.agents[envelope.agent] ||
      d?.viewer?.organization?.id!==policy.organization_id || session?.id!==envelope.session_id ||
      session?.appUser?.id!==policy.agents[envelope.agent] || issue?.id!==envelope.issue_id ||
      !uuid(issue?.team?.id) || !policy.team_ids.includes(issue.team.id) || !uuid(project?.id) ||
      typeof project?.url!=='string') return deny();
  let url;
  try { url=new URL(project.url); } catch (_) { return deny(); }
  if (url.protocol!=='https:' || url.host!=='linear.app' || url.username || url.password || url.search || url.hash || !url.pathname.startsWith('/')) return deny();
  // The resolver is a separately trusted, configured source; user or agent
  // text cannot choose a scope or smuggle a repository path.
  if (resolution.organization_id!==policy.organization_id || resolution.project_id!==project.id ||
      !resolution.scope || !policy.scopes.some(s=>s.kind===resolution.scope.kind && s.id===resolution.scope.id)) return deny();
  let actor;
  if (envelope.action==='prompted') {
    actor=d?.sourceActor;
    if (!uuid(envelope.source_actor_id) || actor?.id!==envelope.source_actor_id || actor?.app!==false) return deny();
  } else {
    const comment=session.sourceComment || session.comment || null;
    // A responsible creator can also be assigned by an automation; without a
    // verifiable human-authored source comment it is not proof of direction.
    if (!comment || !envelope.origin_comment_id || comment.id!==envelope.origin_comment_id) return deny();
    actor=comment.user;
    if (!actor || actor.app!==false) return deny();
  }
  if (!uuid(actor?.id) || actor.id===policy.agents.jarvis || actor.id===policy.agents.codex) return deny();
  return {permitted:true, human_approval_inferred:false, origin:{organization_id:policy.organization_id,
    team_id:issue.team.id,project_id:project.id,
    project_identifier:/^P-[A-Z0-9]+-[0-9]+$/.test(project.identifier || '') ? project.identifier : project.id,project_url:project.url,
    scope:{kind:resolution.scope.kind,id:resolution.scope.id},source_session:session.id,source_actor:actor.id,agent:envelope.agent}};
}

// A separate native Linear read resolves each proposed issue. The caller must
// select the issue UUID from its protected request, not from the model's claim.
function verifyPlanningIssue(origin, expectedIssueId, reply, policy) {
  const deny = () => ({permitted:false});
  const uuid = x => typeof x === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(x);
  if (!origin || !policy || !uuid(expectedIssueId) || !['jarvis','codex'].includes(origin.agent) ||
      !policy.agents || !uuid(policy.agents[origin.agent]) || origin.organization_id!==policy.organization_id) return deny();
  const data=reply?.body?.data, issue=data?.issue;
  if (reply?.statusCode!==200 || reply.body?.errors || data?.viewer?.id!==policy.agents[origin.agent] ||
      data?.viewer?.organization?.id!==origin.organization_id || issue?.id!==expectedIssueId ||
      issue?.project?.id!==origin.project_id || issue?.team?.id!==origin.team_id ||
      typeof issue?.identifier!=='string' || !/^[A-Z0-9]+-[0-9]+$/.test(issue.identifier)) return deny();
  let url;
  try { url=new URL(issue.url); } catch (_) { return deny(); }
  if (url.protocol!=='https:' || url.host!=='linear.app' || url.username || url.password ||
      url.search || url.hash || !url.pathname.startsWith('/')) return deny();
  return {permitted:true,issue:{organization_id:origin.organization_id,team_id:origin.team_id,
    project_id:origin.project_id,id:issue.id,identifier:issue.identifier,url:issue.url}};
}
