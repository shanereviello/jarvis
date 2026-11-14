// The database row comes from an exact run/delivery join. The retained payload
// remains untrusted until the subsequent live Linear origin verification.
function hermesPlanningEnvelope(native, row) {
  const uuid=x=>typeof x==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(x);
  if (!native || !row || row.hermes_run_id!==native.run_id || row.status!=='running' ||
      row.organization_id!==native.organization_id || row.receipt_organization_id!==native.organization_id ||
      row.agent_session_id!==native.session_id || row.receipt_session_id!==native.session_id ||
      row.hermes_session_id!==native.hermes_session_id || row.event_type!=='AgentSessionEvent' ||
      !['created','prompted'].includes(row.action) || !uuid(row.issue_id) || !uuid(row.delivery_id) ||
      !row.raw_payload || typeof row.raw_payload!=='object' || Array.isArray(row.raw_payload))
    throw new Error('Exact active native delivery required');
  const payload=row.raw_payload, session=payload.agentSession, activity=payload.agentActivity || {};
  if (!session || typeof session!=='object' || session.id!==native.session_id ||
      (payload.action && payload.action!==row.action)) throw new Error('Retained event differs');
  const issue=session.issue?.id || session.issueId;
  if (issue!==row.issue_id) throw new Error('Retained issue differs');
  return {agent:'jarvis',action:row.action,session_id:native.session_id,issue_id:row.issue_id,
    source_actor_id:row.action==='prompted'?(activity.userId || activity.user?.id || null):null,
    origin_comment_id:session.sourceCommentId || session.commentId || session.sourceComment?.id || session.comment?.id || null,
    responsible_human_id:session.creatorId || session.creator?.id || null};
}
