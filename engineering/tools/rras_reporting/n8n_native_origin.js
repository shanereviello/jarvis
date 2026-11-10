// Native read observations are supplied only by the fixed n8n OAuth HTTP node.
// A responsible human is context, never a proxy for the triggering comment author.
function verifyOrigin(envelope, reply, policy, handoff = null) {
  const deny = () => ({permitted:false,correlated_handoff_id:null,
    observation:{status:'unconfirmed',detail:'Native origin is unconfirmed; no coding turn was started.'}});
  const d=reply.body?.data, s=d?.agentSession;
  const canonical=v=>JSON.stringify(v&&typeof v==='object'&&!Array.isArray(v)?
    Object.fromEntries(Object.keys(v).sort().map(k=>[k,JSON.parse(canonical(v[k]))])):v);
  if(reply.statusCode!==200 || reply.body?.errors || d?.viewer?.id!==policy.app_user_id ||
      d?.viewer?.organization?.id!==policy.organization_id || s?.id!==envelope.session_id ||
      s?.appUser?.id!==policy.app_user_id || s?.issue?.id!==envelope.issue_id ||
      canonical(envelope.binding)!==canonical(policy.issues[envelope.issue_id])) return deny();
  let actor,basis,comment=null;
  if(envelope.action==='prompted') {
    actor=d?.sourceActor;
    if(!actor || actor.id!==envelope.source_actor_id || actor.app!==false ||
       policy.agent_actor_ids.includes(actor.id))return deny();
    basis='signed_prompt_actor_and_native_user_read';
  } else {
    comment=s.sourceComment || s.comment || null;
    if(envelope.origin_comment_id && comment?.id!==envelope.origin_comment_id)return deny();
    // Linear creates an authorless root thread for a session that did not
    // originate in another comment. Its responsible creator is meaningful
    // only when the signed event, native session, and user read all agree.
    // An actual source comment or any correlated handoff must follow the
    // existing author/handoff path, even if the display root is artificial.
    if(s.sourceComment===null && s.sourceMetadata===null && comment && comment===s.comment &&
       comment.isArtificialAgentSessionRoot===true && comment.agentSession?.id===s.id &&
       comment.user===null && envelope.origin_comment_id===comment.id && !handoff) {
      actor=s.creator;
      if(!actor || actor.app!==false || !envelope.responsible_human_id ||
         actor.id!==envelope.responsible_human_id || d?.sourceActor?.id!==actor.id ||
         d?.sourceActor?.app!==false || policy.agent_actor_ids.includes(actor.id))return deny();
      return {permitted:true,correlated_handoff_id:null,observation:{status:'native_human_context',
        source_actor_id:null,actor_basis:'native_artificial_root_and_verified_creator',
        source_comment_id:null,session_thread_comment_id:comment.id,
        responsible_human_id:actor.id,human_approval_inferred:false}};
    }
    if(comment) {
      actor=comment.user;basis='native_source_comment_author';
      if(!actor || typeof actor.app!=='boolean')return deny();
      if(actor.app) {
        const h=handoff?.body;
        if(!h || handoff.organization_id!==policy.organization_id || h.issue_id!==envelope.issue_id ||
            h.recipient_app_user_id!==policy.app_user_id || h.sender_app_user_id!==actor.id ||
            handoff.comment_id!==comment.id || handoff.comment_state!=='confirmed' ||
            !handoff.source_quiescence || !['uncertain','bound'].includes(handoff.session_state) ||
            handoff.state==='declined' || (handoff.target_session_id && handoff.target_session_id!==s.id) ||
            canonical(h.binding)!==canonical(envelope.binding))return deny();
        return {permitted:true,correlated_handoff_id:handoff.id,observation:{status:'correlated_agent_handoff',
          source_actor_id:actor.id,source_comment_id:comment.id,responsible_human_id:s.creator?.id||null,
          human_approval_inferred:false}};
      }
      if(handoff || policy.agent_actor_ids.includes(actor.id))return deny();
    } else {
      actor=s.creator;basis='native_responsible_human_for_commentless_session';
      if(!actor || actor.app!==false || policy.agent_actor_ids.includes(actor.id) || handoff)return deny();
    }
  }
  return {permitted:true,correlated_handoff_id:null,observation:{status:'native_human_context',source_actor_id:actor.id,
    actor_basis:basis,source_comment_id:comment?.id||null,responsible_human_id:s.creator?.id||null,
    human_approval_inferred:false}};
}
