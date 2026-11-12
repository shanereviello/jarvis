// Input is supplied by the verified ingress and the fixed native Linear read,
// never by model-authored text. This verifier grants planning only.
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
    if (session.sourceComment===null && session.sourceMetadata===null && comment && comment===session.comment &&
        comment.isArtificialAgentSessionRoot===true && comment.agentSession?.id===session.id && comment.user===null &&
        envelope.origin_comment_id===comment.id) {
      actor=session.creator;
      if (!uuid(envelope.responsible_human_id) || actor?.id!==envelope.responsible_human_id ||
          actor?.app!==false || d?.sourceActor?.id!==actor.id || d?.sourceActor?.app!==false) return deny();
    } else {
      if (!comment || !envelope.origin_comment_id || comment.id!==envelope.origin_comment_id) return deny();
      actor=comment.user;
      if (!actor || actor.app!==false) return deny();
    }
  }
  if (!uuid(actor?.id) || actor.id===policy.agents.jarvis || actor.id===policy.agents.codex) return deny();
  return {permitted:true, human_approval_inferred:false, origin:{organization_id:policy.organization_id,
    team_id:issue.team.id,project_id:project.id,
    project_identifier:/^P-[A-Z0-9]+-[0-9]+$/.test(project.identifier || '') ? project.identifier : project.id,project_url:project.url,
    scope:{kind:resolution.scope.kind,id:resolution.scope.id},source_session:session.id,source_actor:actor.id,agent:envelope.agent}};
}
