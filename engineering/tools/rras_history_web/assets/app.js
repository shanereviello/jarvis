'use strict';
const $ = id => document.getElementById(id);
const state = {scopes: [], scopeMetadata: [], detailScopeMetadata: null, scopeFilter: 'all', view: 'projects', projects: [], items: [], project: null, closeout: null, detail: null, selected: null, scope: null, listVersion: 0, detailVersion: 0, cursors: {}, snapshots: {}, detailSnapshot: null};
const labels = {'work.create': 'Work recorded', 'work.revise': 'Scope revised', 'session.attach': 'Session attached', 'checkpoint.append': 'Checkpoint recorded', 'outcome.record': 'Outcome reported', 'document.render': 'Document retained'};
const projectTabs = ['Overview', 'Work', 'Architecture', 'Baselines', 'History'];
let searchTimer;
function node(tag, cls, text) { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined && text !== null) n.textContent = String(text); return n; }
function button(label, fn, cls = '') { const b = node('button', cls, label); b.type = 'button'; b.addEventListener('click', fn); return b; }
function badge(text) { return node('span', 'badge', text); }
function when(value) { if (!value) return 'Not recorded'; const d = new Date(value); return Number.isNaN(d.getTime()) ? 'Unknown' : d.toLocaleString(); }
function outcome(value) { return ({completed_claim: 'Reported complete', partial: 'Reported partial', failed: 'Reported failure', unfinished: 'Reported unfinished', uncertain: 'Reported uncertain'})[value] || 'No outcome recorded'; }
function designLabel(doc) { return ({governing: 'Governing', previously_governing: 'Previously governing', draft: 'Draft'})[doc.designation_status] || 'Saved'; }
function key(scope) { return scope.kind + ':' + scope.id; }
function scopeLabel(scope, captured = null) { const m = captured || state.scopeMetadata.find(m => key(m.scope) === key(scope)); return m && m.recorded && m.display_name !== scope.id ? m.display_name + ' (' + scope.id + ')' : scope.id; }
function scopeTools() { $('scope-details').hidden = state.scopeFilter === 'all' || !state.scopes.length; }
function routeValues() { return Object.fromEntries(new URLSearchParams(location.hash.slice(1))); }
function navigate(values) { const hash = new URLSearchParams(values).toString(); if (location.hash.slice(1) === hash) route(); else location.hash = hash; }
function projectRoute(extra = {}) { const r = routeValues(); return {scope: key(state.scope), project: state.project.project_id, ...(r.closeout ? {closeout: r.closeout} : {}), ...extra}; }
function stamp() { $('snapshot').textContent = 'History read ' + new Date().toLocaleTimeString(); }
function clearPrivate(message) {
  state.listVersion++; state.detailVersion++; state.scopes = []; state.scopeMetadata = []; state.projects = []; state.items = []; state.project = null; state.closeout = null; state.detailScopeMetadata = null; state.detail = null; state.selected = null; state.scope = null; state.snapshots = {}; state.cursors = {}; state.detailSnapshot = null; scopeTools();
  clearTimeout(searchTimer); $('operator').textContent = 'Access unavailable'; $('repository').replaceChildren(); $('repository').disabled = true; $('search').value = ''; $('search').disabled = true; $('refresh').disabled = false;
  $('work-list').replaceChildren(node('p', 'empty', 'History is currently unavailable.')); $('detail').replaceChildren(node('p', 'empty', 'Refresh after access or history service is restored.')); $('count').textContent = '—'; $('more').hidden = true; $('breadcrumb').replaceChildren(); $('notice').textContent = message; $('notice').hidden = false;
}
async function api(path, params) {
  const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 20000);
  try { const url = new URL(path, location.origin); for (const [k, v] of Object.entries(params || {})) if (v !== undefined && v !== null) url.searchParams.set(k, String(v)); const response = await fetch(url, {cache: 'no-store', credentials: 'same-origin', signal: controller.signal, headers: {'Accept': 'application/json'}}); if (!response.ok) throw new Error('unavailable'); return await response.json(); } finally { clearTimeout(timer); }
}
function workspace(view, params = {}, scope = state.scope, snapshot = null) {
  return api('/api/workspace/' + view, {scope_kind: scope.kind, scope_id: scope.id, ...params, ...(snapshot ? {snapshot: JSON.stringify(snapshot)} : {})});
}
async function verify(markdown, expected) { const raw = new TextEncoder().encode(markdown); const result = await crypto.subtle.digest('SHA-256', raw); const digest = [...new Uint8Array(result)].map(v => v.toString(16).padStart(2, '0')).join(''); if (digest !== expected) throw new Error('digest'); }
function download(markdown, filename) { const url = URL.createObjectURL(new Blob([markdown], {type: 'text/markdown;charset=utf-8'})); const a = node('a'); a.href = url; a.download = filename; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
function field(panel, label, value) { panel.append(node('h3', 'section-label', label), node('p', 'prose', value || 'Not recorded')); }
function emptyDetail() { state.detailVersion++; state.project = null; state.closeout = null; state.detailScopeMetadata = null; state.detail = null; state.selected = null; $('breadcrumb').replaceChildren(); $('detail').replaceChildren(node('p', 'empty', 'Select a project or work item to inspect its recorded history.')); }
function setListView(view) { state.view = view; $('view').value = view; emptyDetail(); loadList(); }
async function loadList(append = false) {
  const version = ++state.listVersion;
  if (!append) { state.items = []; state.cursors = {}; state.snapshots = {}; $('work-list').replaceChildren(node('p', 'empty', 'Reading recorded history…')); }
  const scopes = state.scopes.filter(s => state.scopeFilter === 'all' || key(s) === state.scopeFilter);
  let total = 0; let hasMore = false;
  try {
    for (const scope of scopes) {
      const k = key(scope); const previous = state.cursors[k];
      if (append && previous && !previous.has_more) { total += previous.total; continue; }
      const result = await workspace(state.view === 'projects' ? 'projects' : 'works', {q: $('search').value, offset: append && previous ? previous.next_offset : 0, limit: 20, ...(state.view === 'projects' ? {state: $('project-state').value || undefined, archived: $('archived').checked} : {unassigned: state.view === 'unassigned'})}, scope, append ? state.snapshots[k] : null);
      if (version !== state.listVersion) return;
      state.snapshots[k] = result.snapshot; state.cursors[k] = result; total += result.total; hasMore ||= result.has_more;
      state.items.push(...result.items.map(item => ({...item, scope})));
    }
    if (version !== state.listVersion) return;
    state.items.sort((a, b) => (b.last_project_update || b.last_recorded_at).localeCompare(a.last_project_update || a.last_recorded_at));
    $('work-list').replaceChildren();
    for (const item of state.items) {
      const isProject = state.view === 'projects';
      const card = button('', () => navigate({scope: key(item.scope), ...(isProject ? {project: item.project_id} : {work: item.work_item_id})}), 'work-card');
      card.append(node('h3', '', isProject ? item.name : item.title), node('div', 'event-time', scopeLabel(item.scope)));
      if (isProject) {
        const doc = item.governing_architecture; const latest = item.latest_architecture;
        card.append(node('p', 'card-overview', item.overview), badge(item.state), node('div', 'event-time', item.work_count + ' work items · Governing: ' + (doc ? 'v' + doc.version : 'Not designated') + (latest && (!doc || latest.version > doc.version) ? ' · ' + designLabel(latest) + ' v' + latest.version : '')),
          node('div', 'event-time', 'Project updated ' + when(item.last_project_update)), node('div', 'event-time', 'Work activity ' + when(item.last_work_activity)));
      } else {
        card.append(badge(outcome(item.latest_outcome)), node('div', 'event-time', 'Scope revision ' + item.revision + (item.latest_outcome && item.outcome_revision_sha256 !== item.work_revision_sha256 ? ' · Outcome concerns an earlier scope' : '')),
          node('div', 'event-time', item.assignment && item.assignment.project_id ? 'Assigned to project · Design ' + (item.assignment.architecture_version ? 'v' + item.assignment.architecture_version : 'Not designated') : 'Unassigned work'), node('div', 'event-time', when(item.last_recorded_at)));
      }
      $('work-list').append(card);
    }
    if (!state.items.length) $('work-list').append(node('p', 'empty', 'No recorded ' + (state.view === 'projects' ? 'projects' : 'work') + ' match this view. Explicit recording and assignment determine coverage.'));
    $('list-title').textContent = state.view === 'projects' ? 'Projects' : state.view === 'unassigned' ? 'Unassigned work' : 'All work'; $('count').textContent = total; $('more').hidden = !hasMore; $('notice').hidden = true; stamp();
  } catch (_) { if (version === state.listVersion) clearPrivate('History could not be read. Request a fresh authorized view.'); }
}
function tabs(target, names, active, fn) {
  const list = node('div', 'tabs'); list.setAttribute('role', 'tablist'); list.setAttribute('aria-label', 'Record views');
  const panel = node('div', 'tab-panel'); panel.setAttribute('role', 'tabpanel'); panel.id = 'record-panel';
  for (const title of names) { const name = title.toLowerCase(); const b = button(title, () => fn(name), 'tab' + (active === name ? ' active' : '')); b.id = 'tab-' + name; b.setAttribute('role', 'tab'); b.setAttribute('aria-selected', String(active === name)); b.setAttribute('aria-controls', 'record-panel'); list.append(b); }
  panel.setAttribute('aria-labelledby', 'tab-' + active); target.append(list, panel); return panel;
}
async function route() {
  if (!state.scopes.length) return;
  const r = routeValues(); if (!r.scope) { emptyDetail(); return; }
  const scope = state.scopes.find(s => key(s) === r.scope); if (!scope) { clearPrivate('This scope is unavailable.'); return; }
  state.scope = scope; const version = ++state.detailVersion; $('detail').replaceChildren(node('p', 'empty', 'Reading recorded history…'));
  try {
    state.project = null; state.closeout = null; state.detailScopeMetadata = null; state.detailSnapshot = null;
    if (r.scope_details === '1') {
      const value = await workspace('scope', {version: r.version || undefined});
      if (version !== state.detailVersion) return;
      state.detailSnapshot = value.snapshot; state.detailScopeMetadata = value.scope_metadata; await renderScope(value, version); stamp(); return;
    }
    if (r.project) {
      const value = await workspace('project', {project_id: r.project, ...(r.closeout ? {closeout_sequence: r.closeout} : {})});
      if (version !== state.detailVersion) return;
      state.project = value.project; state.closeout = value.closeout || null; state.detailSnapshot = value.snapshot; state.detailScopeMetadata = value.scope_metadata;
    }
    if (r.work) {
      const detail = await workspace('work', {work_id: r.work}, scope, state.detailSnapshot);
      if (version !== state.detailVersion) return;
      state.detail = detail; state.detailScopeMetadata = detail.scope_metadata; state.selected = r.work; state.detailSnapshot = detail.snapshot; await renderWork(r.tab || 'overview');
    } else if (r.project) await renderProject(r.tab || 'overview', version);
    else emptyDetail();
    stamp();
  } catch (_) { if (version === state.detailVersion) clearPrivate('This record could not be read or verified. Request a fresh authorized view.'); }
}
function breadcrumb(work) {
  const target = $('breadcrumb'); target.replaceChildren(button('All projects', () => { location.hash = ''; setListView('projects'); }, 'quiet'), node('span', '', '/ ' + scopeLabel(state.scope, state.detailScopeMetadata)));
  if (state.project) target.append(button(state.project.name, () => navigate(projectRoute()), 'quiet'));
  if (work) target.append(node('span', '', '/ ' + work.title));
}
function attribution(panel, record) {
  const source = record.source || {};
  field(panel, 'Source attribution', [source.kind, source.namespace, source.id].filter(Boolean).join(' · ') || 'Not recorded');
  field(panel, 'Submitting principal', record.peer_uid != null ? 'UID ' + record.peer_uid : record.writer_uid != null ? 'UID ' + record.writer_uid : 'Not recorded');
  field(panel, 'Recording / source occurrence time', when(record.recorded_at) + ' / ' + when(record.occurred_at));
}
async function renderScope(value, version) {
  const m = value.metadata; breadcrumb(); const panel = $('detail');
  panel.replaceChildren(node('div', 'work-eyebrow', state.scope.kind === 'repository' ? 'Repository' : 'Non-Git category'), node('h2', '', m.display_name), node('code', '', state.scope.id));
  const unmapped = node('section'); unmapped.append(node('h3', 'section-label', 'Unmapped captured evidence')); panel.append(unmapped);
  await paged(unmapped, 'reporting', {unassigned: true, operation: 'artifact.record'}, version, reportingRecord);
  if (version !== state.detailVersion) return;
  if (!m.recorded) { panel.append(node('p', 'empty', 'Scope metadata not yet recorded.')); return; }
  field(panel, 'Description', m.description); field(panel, 'Scope revision', m.revision); field(panel, 'Change summary', m.change_summary); attribution(panel, m);
  if (m.repository_url) {
    let url; try { url = new URL(m.repository_url); } catch (_) { url = null; }
    if (url && url.protocol === 'https:' && !url.username && !url.password && !url.search && !url.hash) { const a = node('a', 'evidence-link', 'Repository source'); a.href = url.href; a.target = '_blank'; a.rel = 'noopener noreferrer'; panel.append(a); }
  }
  panel.append(node('h3', 'section-label', 'Scope revision history'));
  await paged(panel, 'scope', {}, version, item => { const card = node('article', 'record-card'); card.append(node('h3', '', 'Revision ' + item.revision + ' · ' + item.display_name), node('p', 'prose', item.change_summary), node('p', 'event-time', when(item.recorded_at)), button('View scope revision ' + item.revision, () => navigate({scope: key(state.scope), scope_details: 1, version: item.revision}), 'quiet')); return card; });
}
async function renderProject(tab, version) {
  const p = state.project; if (!projectTabs.some(t => t.toLowerCase() === tab)) tab = 'overview'; const r = routeValues();
  breadcrumb(); const target = $('detail'); target.replaceChildren(node('div', 'work-eyebrow', state.scope.id + ' / Project'), node('h2', '', p.name), badge(p.state), ...(p.archived ? [badge('Archived')] : []), node('p', 'purpose', p.overview));
  if (r.closeout) target.append(node('p', 'snapshot-note', 'Historical view · At closeout on ' + when(state.closeout && state.closeout.recorded_at) + ' · #' + r.closeout), button('Return to current project', () => navigate({scope: key(state.scope), project: p.project_id}), 'quiet'));
  else target.append(node('p', 'event-time', 'Current view · ' + p.work_count + ' assigned work items'));
  const panel = tabs(target, projectTabs, tab, name => navigate(projectRoute({tab: name})));
  if (tab === 'overview') {
    field(panel, 'Intended outcome', p.intended_outcome); field(panel, 'In scope', p.in_scope); field(panel, 'Out of scope', p.out_of_scope); field(panel, 'Owner', p.owner || 'Not recorded');
    const doc = p.architecture.find(d => d.version === p.governing_version); const latest = p.architecture[p.architecture.length - 1];
    field(panel, 'Architecture document', latest ? latest.title + ' · ' + latest.document_id : 'Not yet recorded');
    panel.append(button('Architecture: ' + (doc ? 'Governing v' + doc.version : 'Not designated') + (latest ? ' · Latest saved v' + latest.version + ' (' + designLabel(latest) + ')'  : ''), () => navigate(projectRoute({tab: 'architecture'})), 'doc-card'));
    field(panel, 'Git baseline', p.scope.kind === 'non_git' ? 'Not applicable — non-Git project' : 'Starting: ' + (p.starting_baseline || 'Not recorded') + ' · Current: ' + (p.current_baseline || 'Not recorded'));
    field(panel, 'Project reference', p.project_id); field(panel, 'Project metadata', 'Revision ' + p.revision + ' · Updated ' + when(p.last_project_update));
    reportingSummary(panel, p.reporting);
    attribution(panel, {source: p.last_source, peer_uid: p.last_peer_uid, writer_uid: p.last_writer_uid, recorded_at: p.last_project_update, occurred_at: p.last_occurred_at});
    panel.append(node('h3', 'section-label', 'Reported outcomes · current scope'));
    for (const [name, count] of Object.entries(p.reported_outcome_counts || {})) field(panel, name === 'not_recorded' ? 'No outcome recorded' : outcome(name), String(count));
    field(panel, 'Outcomes for earlier scope revisions', String(p.earlier_revision_outcome_count || 0));
    for (const closeout of p.closeouts) { field(panel, 'Recorded ' + closeout.state + ' · ' + when(closeout.recorded_at) + ' · #' + closeout.sequence, closeout.summary); panel.append(button('Inspect closeout #' + closeout.sequence, () => navigate({scope: key(state.scope), project: p.project_id, closeout: closeout.sequence}), 'quiet')); }
  } else if (tab === 'work') await paged(panel, 'works', {project_id: p.project_id}, version, item => workCard(item));
  else if (tab === 'architecture') await architecture(panel, p, r, version);
  else if (tab === 'baselines') {
    if (p.scope.kind === 'non_git') field(panel, 'Git baselines', 'Not applicable — non-Git project');
    else if (!p.baselines.length) field(panel, 'Git baselines', 'Not recorded');
    for (const b of p.baselines) { const card = node('article', 'record-card'); card.append(node('h3', '', 'v' + b.version + ' · ' + b.label), node('code', '', b.commit)); field(card, 'Repository / captured ref', b.repository_id + ' / ' + (b.ref || 'Not recorded')); field(card, 'Selection', [p.starting_baseline === b.version ? 'Starting' : '', p.current_baseline === b.version ? 'Current' : '', p.closeouts.some(c => c.baseline && c.baseline.version === b.version) ? 'At closeout' : ''].filter(Boolean).join(' · ') || 'Saved'); field(card, 'Change reason', b.reason); field(card, 'Provenance', b.source.kind + ' · Recorded ' + when(b.recorded_at)); field(card, 'Reported source information', (b.source_reference || 'Not recorded') + ' · Reported verification time: ' + when(b.verified_at)); card.append(node('p', 'event-time', 'A reported commit or verification timestamp is not an independently observed release.')); panel.append(card); }
    await reportingHistory(panel, {project_id: p.project_id, operation: 'attempt.record'}, version);
  } else {
    await paged(panel, 'history', {project_id: p.project_id}, version, event => { const n = node('article', 'record-card'); n.append(node('h3', '', event.operation), badge(event.source.kind), node('p', 'event-time', 'Recorded ' + when(event.recorded_at) + ' · Occurred ' + when(event.occurred_at)), node('pre', 'document-source', JSON.stringify(event.body, null, 2))); return n; });
    if (version === state.detailVersion) await reportingHistory(panel, {project_id: p.project_id}, version);
  }
  if (version === state.detailVersion) target.append(node('p', 'limit-note', 'Project state and design designation are explicit records. Work outcomes, merge, deployment and verification remain separate facts.'));
}
function workCard(item) { const b = button('', () => navigate(projectRoute({work: item.work_item_id})), 'doc-card'); b.append(node('strong', '', item.title), badge(outcome(item.latest_outcome)), node('p', 'event-time', 'Scope revision ' + item.revision + ' · Design ' + (item.assignment && item.assignment.architecture_version ? 'v' + item.assignment.architecture_version : 'Not designated')), node('p', 'event-time', 'Last recorded activity ' + when(item.last_recorded_at))); if (item.latest_outcome) b.append(node('p', 'event-time', 'Outcome for ' + (item.outcome_revision ? 'scope revision ' + item.outcome_revision : 'scope digest ' + item.outcome_revision_sha256) + (item.outcome_revision_sha256 !== item.work_revision_sha256 ? ' · Earlier scope revision' : ' · Current scope revision'))); const report = item.reporting; if (report && report.available) { for (const mapping of report.mappings || []) if (mapping.body.kind === 'execution') b.append(node('p', 'event-time', mapping.body.plan_id + ' · ' + mapping.body.linear.identifier)); if (report.latest_attempt) b.append(node('p', 'event-time', agentLabel(report.latest_attempt.body.actor) + ' · ' + report.latest_attempt.body.phase)); if (report.latest_checkpoint) b.append(node('p', 'prose', report.latest_checkpoint.observation)); } return b; }
async function paged(panel, view, params, version, render) {
  let offset = 0;
  const more = button('Show more', () => load(), 'more');
  async function load() { try { const result = await workspace(view, {...params, offset, limit: 20}, state.scope, state.detailSnapshot); if (version !== state.detailVersion) return; more.remove(); for (const item of result.items) panel.append(render(item)); if (!result.total) panel.append(node('p', 'empty', 'No records in this view.')); offset = result.next_offset; if (result.has_more) panel.append(more); } catch (_) { if (version === state.detailVersion) clearPrivate('History is unavailable. Request a fresh authorized view.'); } }
  await load();
}
async function architecture(panel, p, r, version) {
  if (!p.architecture.length) { field(panel, 'Architecture document', 'Not yet recorded'); return; }
  const selected = Number(r.version || p.governing_version || p.architecture[p.architecture.length - 1].version);
  const picker = node('select'); picker.setAttribute('aria-label', 'Architecture version');
  for (const d of p.architecture) { const option = node('option', '', 'v' + d.version + (' · ' + designLabel(d)) + ' — ' + d.change_summary); option.value = d.version; picker.append(option); }
  picker.value = selected; picker.addEventListener('change', () => navigate(projectRoute({tab: 'architecture', version: picker.value}))); panel.append(picker);
  const value = await workspace('architecture', {project_id: p.project_id, version: selected}, state.scope, state.detailSnapshot); if (version !== state.detailVersion) return;
  const d = value.document; await verify(d.markdown, d.markdown_sha256); if (version !== state.detailVersion) return;
  field(panel, d.title + ' · v' + d.version, d.change_summary); panel.append(node('code', '', d.document_id + ' · ' + d.markdown_sha256)); attribution(panel, d); field(panel, 'Source reference', d.source_reference);
  const designations = node('section'); designations.append(node('h3', 'section-label', 'Governing designation history'));
  if (!(p.designations || []).length) designations.append(node('p', 'empty', 'Not designated.'));
  for (const event of p.designations || []) { const card = node('article', 'record-card'); card.append(node('h4', '', 'Designated v' + event.version), node('p', 'prose', event.reason), node('code', '', event.markdown_sha256)); attribution(card, event); designations.append(card); }
  panel.append(designations);
  for (const closeout of p.closeouts) if (closeout.architecture && closeout.architecture.version === d.version) field(panel, 'Architecture pinned at closeout', when(closeout.recorded_at) + ' · #' + closeout.sequence);
  field(panel, 'Baseline at document creation', d.baseline_applicability === 'not_applicable' ? 'Not applicable — non-Git project' : d.baseline ? 'v' + d.baseline.version + ' · ' + d.baseline.commit : 'Not recorded');
  panel.append(button('Download exact Markdown', () => download(d.markdown, d.document_id + '-v' + d.version + '.md'), 'quiet'), node('pre', 'document-source', d.markdown));
  const compare = node('section', 'compare-controls'); compare.append(node('h3', 'section-label', 'Compare saved versions'));
  const left = node('select'); left.setAttribute('aria-label', 'Compare from version'); const right = node('select'); right.setAttribute('aria-label', 'Compare to version');
  for (const doc of p.architecture) for (const pick of [left, right]) { const option = node('option', '', 'v' + doc.version); option.value = doc.version; pick.append(option); }
  const history = p.designations || []; const previous = [...history].reverse().find(e => e.version !== p.governing_version);
  left.value = previous ? previous.version : p.architecture[0].version; right.value = p.governing_version || selected;
  const diff = node('pre', 'document-source');
  compare.append(left, right, button('Compare', async () => { try { const result = await workspace('compare', {project_id: p.project_id, left: left.value, right: right.value}, state.scope, state.detailSnapshot); if (version !== state.detailVersion) return; diff.textContent = result.diff || 'No text changes.'; } catch (_) { if (version === state.detailVersion) clearPrivate('Comparison unavailable.'); } }), diff); panel.append(compare);
  const related = node('section'); related.append(node('h3', 'section-label', 'Work using this design version')); panel.append(related);
  await paged(related, 'works', {project_id: p.project_id, architecture_version: selected}, version, item => workCard(item));
  if (version === state.detailVersion) await reportingHistory(panel, {project_id: p.project_id, operation: 'decision.observe', architecture_version: selected}, version);
}
async function renderWork(tab) {
  const d = state.detail; const target = $('detail'); if (!['overview', 'timeline', 'documents', 'evidence'].includes(tab)) tab = 'overview'; breadcrumb(d.work);
  target.replaceChildren(button(state.project ? '← Back to project' : '← Back to list', () => state.project ? navigate(projectRoute()) : navigate({}), 'back'), node('div', 'work-eyebrow', d.repository_id + ' / revision ' + d.work.revision), node('h2', '', d.work.title), node('p', 'purpose', d.work.objective));
  const panel = tabs(target, ['Overview', 'Timeline', 'Documents', 'Evidence'], tab, name => navigate({...routeValues(), tab: name}));
  if (tab === 'overview') { field(panel, 'Why this work exists', d.work.rationale); field(panel, 'Work reference', d.work.work_item_id); field(panel, 'Project', d.assignment && d.assignment.project_id || 'Unassigned work'); field(panel, 'Architecture reference', d.assignment && d.assignment.architecture_version ? 'v' + d.assignment.architecture_version : 'Not designated'); field(panel, 'Recorded acceptance criteria', 'Criteria describe requested outcomes; this list does not assert they passed.'); const list = node('ul', 'criteria'); for (const criterion of d.work.acceptance_criteria) list.append(node('li', '', criterion.id + ' · ' + criterion.description)); panel.append(list); field(panel, 'Scope', d.scope.kind === 'non_git' ? 'Non-Git category: ' + d.scope.id : d.work.allowed_paths.join('\n')); field(panel, 'Baseline', d.scope.kind === 'non_git' ? 'Not applicable — non-Git work' : d.work.baseline ? d.work.baseline.ref + ' · ' + d.work.baseline.commit : 'Not recorded'); }
  if (tab === 'timeline') for (const e of [...d.timeline].reverse()) { const item = node('article', 'event'); item.append(node('h3', '', labels[e.operation] || e.operation), badge(e.provenance), node('p', 'prose', e.summary)); for (const decision of e.decisions) item.append(node('p', 'prose', decision)); if (e.next_action) field(item, 'Next action', e.next_action); if (e.operation === 'session.attach') field(item, 'Reported native session ID', e.session_id || 'Not recorded'); if (e.outcome) item.append(badge(outcome(e.outcome)), node('code', '', 'Scope digest: ' + e.work_revision_sha256)); item.append(node('p', 'event-time', 'Recorded ' + when(e.recorded_at) + ' · Occurred ' + when(e.occurred_at))); panel.append(item); }
  if (tab === 'documents') { if (!d.documents.length) panel.append(node('p', 'empty', 'No retained documents.')); for (const doc of d.documents) { const b = button('', () => openWorkDocument(doc), 'doc-card'); b.append(node('strong', '', doc.title), node('small', '', doc.type + ' · version ' + doc.version)); panel.append(b); } }
  if (tab === 'evidence') { if (!d.evidence.length) panel.append(node('p', 'empty', 'No supported external evidence links.')); for (const e of d.evidence) { let url; try { url = new URL(e.url); } catch (_) { continue; } if (url.protocol !== 'https:' || url.hostname !== 'github.com' || url.username || url.password) continue; const a = node('a', 'evidence-link', e.label); a.href = url.href; a.target = '_blank'; a.rel = 'noopener noreferrer'; panel.append(a); } }
  if (tab === 'overview') reportingSummary(panel, d.reporting);
  if (tab === 'timeline') await reportingHistory(panel, {work_id: d.work.work_item_id}, state.detailVersion);
  if (tab === 'evidence') await reportingHistory(panel, {work_id: d.work.work_item_id, operation: 'artifact.record'}, state.detailVersion);
  target.append(node('p', 'limit-note', 'Records preserve reported and imported evidence. Release status is not inferred. Work outside explicit recording may be absent.'));
}
async function openWorkDocument(doc) {
  const version = ++state.detailVersion;
  try { const value = await workspace('document', {work_id: state.selected, document_id: doc.document_id, version: doc.version}, state.scope, state.detailSnapshot); await verify(value.markdown, doc.markdown_sha256); if (version !== state.detailVersion) return; $('detail').replaceChildren(button('← Back to documents', () => { state.detailVersion++; renderWork('documents'); }, 'back'), node('h2', '', doc.title), node('p', 'document-meta', 'Exact Markdown verified · version ' + doc.version), button('Download Markdown', () => download(value.markdown, doc.document_id + '-v' + doc.version + '.md'), 'quiet'), node('pre', 'document-source', value.markdown)); } catch (_) { if (version === state.detailVersion) clearPrivate('The exact document could not be verified.'); }
}
async function boot() {
  const version = ++state.listVersion;
  try {
    const info = await api('/api/workspace/scopes'); if (version !== state.listVersion) return;
    state.scopes = info.scopes; state.scopeMetadata = info.scope_metadata || []; if (!state.scopes.length) throw new Error('scopes'); $('operator').textContent = info.operator_email;
    $('repository').replaceChildren(); const all = node('option', '', 'All scopes'); all.value = 'all'; $('repository').append(all);
    const repos = node('optgroup'); repos.label = 'Repositories'; const other = node('optgroup'); other.label = 'Other repositories'; const categories = node('optgroup'); categories.label = 'Non-Git projects';
    for (const scope of state.scopes) { const option = node('option', '', scopeLabel(scope)); option.value = key(scope); (scope.kind === 'non_git' ? categories : ['jarvis', 'robot_ws'].includes(scope.id) ? repos : other).append(option); }
    for (const group of [repos, other, categories]) if (group.children.length) $('repository').append(group);
    if (state.scopeFilter !== 'all' && !state.scopes.some(s => key(s) === state.scopeFilter)) state.scopeFilter = 'all';
    $('repository').value = state.scopeFilter; scopeTools();
    for (const id of ['repository', 'search', 'refresh']) $(id).disabled = false; $('notice').hidden = true;
    await loadList(); await route();
  } catch (_) { if (version === state.listVersion) clearPrivate('Sign in through Cloudflare Access to read project history.'); }
}
$('repository').addEventListener('change', () => { state.scopeFilter = $('repository').value; scopeTools(); emptyDetail(); location.hash = ''; loadList(); });
$('scope-details').addEventListener('click', () => navigate({scope: state.scopeFilter, scope_details: 1}));
$('view').addEventListener('change', () => { state.view = $('view').value; $('project-filters').hidden = state.view !== 'projects'; emptyDetail(); location.hash = ''; loadList(); });
$('search').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => loadList(), 250); });
for (const id of ['project-state', 'archived']) $(id).addEventListener('change', () => loadList());
$('refresh').addEventListener('click', async () => { if (!state.scopes.length) { await boot(); return; } await loadList(); await route(); });
$('more').addEventListener('click', () => loadList(true));
$('nav-projects').addEventListener('click', () => { location.hash = ''; setListView('projects'); $('project-filters').hidden = false; });
$('nav-work').addEventListener('click', () => { location.hash = ''; setListView('works'); $('project-filters').hidden = true; });
window.addEventListener('hashchange', () => route());
window.addEventListener('pagehide', () => clearPrivate('Request a fresh authorized view to continue.'));
window.addEventListener('pageshow', event => { if (event.persisted) boot(); });
document.querySelector('.account a').addEventListener('click', () => clearPrivate('Signing out…'));
boot();
