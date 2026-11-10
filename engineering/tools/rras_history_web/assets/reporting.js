'use strict';
// Imported text is evidence. Every value is rendered through textContent.
function referenceLink(panel, url, label) {
  let target; try { target = new URL(url); } catch (_) { return; }
  if (target.protocol !== 'https:' || !['linear.app', 'github.com'].includes(target.hostname) || target.username || target.password) return;
  const a = node('a', 'evidence-link', label); a.href = target.href; a.target = '_blank'; a.rel = 'noopener noreferrer'; panel.append(a);
}
function agentLabel(actor) { return actor ? actor.role + ' · ' + actor.runtime + (actor.source_actor_id ? ' · ' + actor.source_actor_id : '') : 'Not recorded'; }
function reportingSummary(panel, summary) {
  panel.append(node('h3', 'section-label', 'Engineering reporting'));
  if (!summary || !summary.available) { panel.append(node('p', 'empty', 'Reporting stream unavailable at this historical boundary.')); return; }
  field(panel, 'Mapped execution work', String(summary.execution_mapping_count));
  for (const mapping of summary.mappings || []) {
    const b = mapping.body;
    referenceLink(panel, b.linear.url, (b.plan_id ? b.plan_id + ' · ' : '') + b.linear.identifier + ' · ' + b.kind);
  }
  if (summary.mappings_has_more) panel.append(node('p', 'limit-note', 'Additional mappings are retained in reporting history.'));
  field(panel, 'Latest reporting receipt', when(summary.latest_recorded_at));
  if (summary.latest_attempt) { const b = summary.latest_attempt.body; field(panel, 'Latest reported attempt', b.phase + ' · ' + agentLabel(b.actor)); if (b.coordinator) field(panel, 'Coordinator', agentLabel(b.coordinator)); }
  if (summary.latest_checkpoint) field(panel, 'Latest checkpoint excerpt', summary.latest_checkpoint.observation || 'See retained checkpoint.');
  field(panel, 'Retained reference counts', summary.artifact_count + ' captured sessions · ' + summary.handoff_count + ' handoffs · ' + summary.decision_count + ' decision observations');
  for (const item of summary.freshness || []) field(panel, 'Capture / sync source', item.body.source.namespace + ':' + item.body.source.id + ' · ' + item.body.status + ' · Source observed ' + when(item.body.source_observed_at));
  if (summary.freshness_has_more) panel.append(node('p', 'limit-note', 'Additional source states are retained in reporting history.'));
  panel.append(node('p', 'limit-note', 'Source states are the last retained observations; they do not establish that a collector is running now.'));
}
function reportingRecord(item) {
  const r = item.submission, b = r.body, receipt = item.receipt;
  const card = node('article', 'record-card reporting-record');
  card.append(node('h3', '', r.operation), badge(r.source.kind));
  if (r.operation === 'mapping.record') {
    field(card, 'Mapping', b.kind + (b.plan_id ? ' · ' + b.plan_id : '') + ' · v' + b.version); referenceLink(card, b.linear.url, b.linear.identifier); field(card, 'Reason', b.reason);
  } else if (r.operation === 'attempt.record') {
    field(card, 'Executor / state', agentLabel(b.actor) + ' · ' + b.phase); if (b.coordinator) field(card, 'Coordinator', agentLabel(b.coordinator));
    field(card, 'Result', b.result); field(card, 'Attempt / baseline', b.attempt_id + ' · ' + (b.baseline_commit || 'Not recorded'));
    for (const s of b.sessions) field(card, 'Session', s.namespace + ':' + s.id);
  } else if (r.operation === 'checkpoint.report') {
    for (const [key, label] of [['observations', 'Observation'], ['alternatives_and_reasons', 'Approach / rationale'], ['changes', 'Change'], ['open_questions', 'Open question']]) for (const text of b[key]) field(card, label, text);
    for (const test of b.validation) field(card, 'Reported validation · ' + test.result, test.description);
    field(card, 'Next step', b.next_step);
  } else if (r.operation === 'session.describe') {
    field(card, 'Native session', b.session.namespace + ':' + b.session.id); field(card, 'Agent', agentLabel(b.actor));
    field(card, 'Linear agent session / activity', (b.linear_agent_session_id || 'Unknown') + ' / ' + (b.linear_agent_activity_id || 'Unknown'));
    field(card, 'Native session tree', b.native_session_tree_id); field(card, 'Parent / fork source', (b.parent_native_thread_id || 'Unknown') + ' / ' + (b.forked_from_native_thread_id || 'Unknown'));
    field(card, 'Host / workspace', (b.host_identity || 'Unknown') + ' / ' + (b.workspace_identity || 'Unknown'));
    field(card, 'Source version', b.source_version); field(card, 'Model observation', (b.model || 'Unknown') + ' · ' + b.model_basis);
    field(card, 'Thread token total', b.tokens === null ? 'Unknown' : JSON.stringify(b.tokens)); field(card, 'Cost USD', b.cost_usd === null ? 'Unknown' : String(b.cost_usd));
    if (b.tokens_basis) field(card, 'Usage scope', b.tokens_basis === 'native_thread_summary' ? 'Native thread total and last report; no per-turn billing allocation' : 'Unknown');
    if (b.last_reported_tokens) field(card, 'Last native token report', JSON.stringify(b.last_reported_tokens));
    if (b.usage_native_turn_id) field(card, 'Native turn of usage observation', b.usage_native_turn_id);
    for (const limit of b.limitations) field(card, 'Provenance limitation', limit);
  } else if (r.operation === 'session.relate') {
    field(card, 'Session relationship', b.relationship + ' · ' + b.session.namespace + ':' + b.session.id);
    if (b.related_session) field(card, 'Related session', b.related_session.namespace + ':' + b.related_session.id);
    field(card, 'Agent', agentLabel(b.actor)); field(card, 'Reason', b.reason);
  } else if (r.operation === 'handoff.record') {
    field(card, 'Handoff', agentLabel(b.sender) + ' → ' + agentLabel(b.recipient) + ' · ' + b.state);
    field(card, 'Request', b.requested_action); field(card, 'Result', b.result);
  } else if (r.operation === 'decision.observe') {
    field(card, 'Decision observation', b.kind + ' · ' + b.state + ' · ' + b.attribution);
    field(card, 'Attributed author', agentLabel(b.attributed_author)); field(card, 'Recorded statement', b.decision_text);
    card.append(node('p', 'limit-note', 'An observed or agent-reported statement does not independently authenticate human approval.'));
  } else if (r.operation === 'artifact.record') {
    field(card, 'Capture', b.collector + ' ' + b.collector_version + ' · v' + b.version + ' · ' + b.completeness);
    field(card, 'Session', b.session.namespace + ':' + b.session.id); field(card, 'Source / capture time', when(b.source_updated_at) + ' / ' + when(b.captured_at));
    for (const gap of b.gaps) field(card, 'Coverage limitation', gap);
    card.append(button('Inspect captured evidence v' + b.version, () => openArtifact(b.artifact_id, b.version, receipt.request_sha256), 'quiet'));
  } else if (r.operation === 'artifact.associate') {
    field(card, 'Association correction', b.reason); card.append(button('Inspect associated evidence', () => openArtifact(b.artifact_id, b.artifact_version, b.manifest_sha256), 'quiet'));
  } else if (r.operation === 'source.observe') {
    field(card, 'Capture / sync state', b.source.namespace + ':' + b.source.id + ' · ' + b.status); field(card, 'Detail', b.detail);
    field(card, 'Source observed / cursor', when(b.source_observed_at) + ' · ' + (b.cursor || 'Unknown')); for (const gap of b.gaps) field(card, 'Gap', gap);
  } else if (r.operation === 'linear.observe') {
    field(card, 'Linear observation', b.object_kind + ' · ' + b.object_id); field(card, 'Source updated', when(b.source_updated_at));
    card.append(node('pre', 'document-source', b.snapshot_text));
  }
  for (const ref of b.references || []) {
    if (ref.namespace === 'external') referenceLink(card, ref.id, ref.id);
    else field(card, 'Evidence reference', ref.namespace + ':' + ref.id + (ref.sha256 ? ' · ' + ref.sha256 : ''));
  }
  const context = item.effective_context === undefined ? r.context : item.effective_context;
  field(card, 'Association', context ? context.project_id + ' · Architecture v' + context.architecture.version + (context.work ? ' · ' + context.work.work_item_id : '') : 'Unmapped; explicit association required');
  card.append(node('code', '', receipt.request_sha256));
  attribution(card, {...receipt, source: r.source, occurred_at: r.occurred_at});
  return card;
}
async function reportingHistory(panel, params, version) {
  panel.append(node('h3', 'section-label', 'Engineering reporting history'));
  await paged(panel, 'reporting', params, version, reportingRecord);
}
async function openArtifact(artifactId, revision, expectedManifest) {
  const version = ++state.detailVersion, snapshot = state.detailSnapshot, scope = state.scope;
  try {
    const answer = await workspace('artifact', {artifact_id: artifactId, version: revision}, scope, snapshot);
    if (version !== state.detailVersion) return;
    if (answer.manifest_sha256 !== expectedManifest || JSON.stringify(answer.snapshot) !== JSON.stringify(snapshot)) throw new Error('manifest association');
    const b = answer.manifest, panel = $('detail');
    panel.replaceChildren(button('← Back to record', () => route(), 'back'), node('h2', '', 'Captured engineering evidence'), badge('Operator private'), node('code', '', artifactId + ' · v' + revision));
    field(panel, 'Collector', b.collector + ' ' + b.collector_version); field(panel, 'Completeness', b.completeness); field(panel, 'Redaction profile', b.redaction_profile);
    field(panel, 'Content SHA-256', b.content_sha256); field(panel, 'Source digest / range', (b.source_range.source_sha256 || 'Unknown') + ' · ' + (b.source_range.start || '?') + ' → ' + (b.source_range.end || '?'));
    field(panel, 'Source / capture time', when(b.source_updated_at) + ' / ' + when(b.captured_at));
    field(panel, 'Selected-source reference', b.authorization_reference);
    for (const gap of b.gaps) field(panel, 'Coverage limitation', gap);
    if (answer.association) field(panel, 'Append-only association correction', answer.association.submission.body.reason);
    const output = node('pre', 'document-source');
    const progress = node('p', 'event-time');
    async function bytes(maximum) {
      const chunks = []; let length = 0;
      const selected = b.chunks.slice(0, maximum);
      for (let offset = 0; offset < selected.length; offset += 8) {
        if (version !== state.detailVersion) return null;
        const batch = selected.slice(offset, offset + 8);
        const value = await workspace('artifact', {artifact_id: artifactId, version: revision, index: batch[0].index, count: batch.length}, scope, snapshot);
        if (version !== state.detailVersion) return null;
        if (value.manifest_sha256 !== expectedManifest || !Array.isArray(value.chunks) || value.chunks.length !== batch.length) throw new Error('artifact association');
        for (let i = 0; i < batch.length; i++) {
          const part = batch[i], data = value.chunks[i];
          if (data.index !== part.index) throw new Error('artifact association');
          const raw = Uint8Array.from(atob(data.data_base64), c => c.charCodeAt(0));
          const sha = [...new Uint8Array(await crypto.subtle.digest('SHA-256', raw))].map(x => x.toString(16).padStart(2, '0')).join('');
          if (sha !== part.sha256 || raw.length !== part.byte_length) throw new Error('chunk digest');
          chunks.push(raw); length += raw.length; progress.textContent = 'Verified ' + length + ' of ' + b.byte_length + ' bytes';
        }
      }
      const raw = new Uint8Array(length); let offset = 0; for (const chunk of chunks) { raw.set(chunk, offset); offset += chunk.length; }
      return raw;
    }
    let busy = false;
    async function read(all) {
      if (busy) return; busy = true;
      try {
        const raw = await bytes(all ? 1024 : 4); if (!raw || version !== state.detailVersion) return;
        if (all || b.chunks.length <= 4) {
          const sha = [...new Uint8Array(await crypto.subtle.digest('SHA-256', raw))].map(x => x.toString(16).padStart(2, '0')).join('');
          if (sha !== b.content_sha256 || raw.length !== b.byte_length) throw new Error('content digest');
        }
        if (all) {
          const url = URL.createObjectURL(new Blob([raw], {type: b.media_type + ';charset=utf-8'})), a = node('a');
          a.href = url; a.download = artifactId + '-v' + revision + (b.media_type === 'text/markdown' ? '.md' : '.txt'); document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
          progress.textContent = 'Exact full artifact verified and downloaded · ' + raw.length + ' bytes';
        } else {
          output.textContent = new TextDecoder().decode(raw); progress.textContent = raw.length < b.byte_length ? 'Partial preview: first ' + raw.length + ' of ' + b.byte_length + ' bytes; full-artifact digest not yet verified.' : 'Exact full artifact verified · ' + raw.length + ' bytes';
        }
      } catch (_) { if (version === state.detailVersion) clearPrivate('Captured evidence could not be read or verified. Request a fresh authorized view.'); }
      finally { busy = false; }
    }
    panel.append(button('Preview captured text', () => read(false), 'quiet'), button('Download verified full export', () => read(true), 'quiet'), progress, output);
  } catch (_) { if (version === state.detailVersion) clearPrivate('Captured evidence is unavailable. Request a fresh authorized view.'); }
}
