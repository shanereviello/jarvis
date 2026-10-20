(async function draftPrFrontend({cli, github, attach}) {
  // Operator-side adapter: cli dispatches the protected installed Python bridge.
  // github invokes this chat's existing connector; no tokens enter the worker.
  if (![cli, github, attach].every(fn => typeof fn === 'function')) throw new Error('operator_adapters_required');
  const unwrap = result => {
    if (result?.isError) throw new Error('connector_error');
    const value = result?.structuredContent;
    if (typeof value?.content === 'string') return JSON.parse(value.content);
    if (value && typeof value === 'object') return value;
    throw new Error('connector_shape');
  };
  const intent = await cli('prepare');
  const branch = unwrap(await github('fetch', intent.branch_read));
  const prs = unwrap(await github('fetch', intent.prs_read));
  if (!Array.isArray(prs)) throw new Error('PR_collection_shape');
  const armed = await cli('arm', {
    branch: {name: branch.name, commit: {sha: branch.commit?.sha}},
    prs: prs.length ? [{}] : []
  });
  // Only the exact server-validated request is passed to the authenticated client.
  let snapshot;
  try {
    snapshot = unwrap(await github('create_pull_request', armed.create));
  } catch (_) {
    return await cli('unknown'); // Never retry creation after an ambiguous response.
  }
  // Attach every created PR, including one whose head raced with our preflight.
  const url = snapshot.html_url || snapshot.url;
  let attachmentError = false;
  if (typeof url === 'string' && /^https:\/\/github\.com\/[A-Za-z0-9_-]+\/[A-Za-z0-9_.-]+\/pull\/[1-9][0-9]*$/.test(url)) {
    try { await attach(url); } catch (_) { attachmentError = true; }
  }
  const selected = snapshot.head && typeof snapshot.head === 'object' ? {
    head: {ref: snapshot.head.ref, sha: snapshot.head.sha, repo: {full_name: snapshot.head.repo?.full_name}},
    base: {ref: snapshot.base?.ref}, html_url: snapshot.html_url,
    number: snapshot.number, draft: snapshot.draft, merged: snapshot.merged, state: snapshot.state
  } : {
    head: snapshot.head, head_sha: snapshot.head_sha, head_repo_full_name: snapshot.head_repo_full_name,
    base: snapshot.base, url: snapshot.url, number: snapshot.number,
    draft: snapshot.draft, merged: snapshot.merged, state: snapshot.state
  };
  // Host/receipt failures leave the armed fence. Never create again as recovery.
  const result = await cli('complete', selected);
  return {...result, attachment_pending: attachmentError};
})
