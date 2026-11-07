// Dedicated Codex route; do not replace or edit the existing Jarvis Worker.
// Bind CODEX_WEBHOOK_SECRET and CODEX_N8N_BRIDGE_SECRET as private Worker secrets.
// CODEX_N8N_URL is the fixed authenticated n8n production webhook, not caller input.
export default {
  async fetch(request, env) {
    const deny = status => new Response('Codex webhook refused', {status});
    const url = new URL(request.url);
    if (request.method !== 'POST' || url.pathname !== '/webhooks/codex' || url.search) return deny(404);
    const maximum = 131072;
    const declared = request.headers.get('content-length');
    if (declared && (!/^\d+$/.test(declared) || Number(declared) > maximum)) return deny(413);
    if (!env.CODEX_WEBHOOK_SECRET || !env.CODEX_N8N_BRIDGE_SECRET ||
        !env.CODEX_N8N_URL || env.CODEX_WEBHOOK_SECRET.length < 24 ||
        env.CODEX_N8N_BRIDGE_SECRET.length < 32) return deny(503);
    let target;
    try { target = new URL(env.CODEX_N8N_URL); } catch { return deny(503); }
    if (target.protocol !== 'https:' || target.username || target.password || target.search || target.hash) return deny(503);
    const reader = request.body?.getReader();
    if (!reader) return deny(400);
    const chunks = []; let size = 0;
    while (true) {
      const {done,value} = await reader.read(); if (done) break;
      size += value.byteLength;
      if (size > maximum) { await reader.cancel(); return deny(413); }
      chunks.push(value);
    }
    const raw = new Uint8Array(size); let cursor = 0;
    for (const chunk of chunks) { raw.set(chunk,cursor); cursor+=chunk.byteLength; }
    const signature = request.headers.get('linear-signature') || '';
    const delivery = request.headers.get('linear-delivery') || '';
    if (!/^[0-9a-f]{64}$/.test(signature) ||
        !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(delivery)) return deny(403);
    const key = await crypto.subtle.importKey('raw',new TextEncoder().encode(env.CODEX_WEBHOOK_SECRET),
      {name:'HMAC',hash:'SHA-256'},false,['verify']);
    const supplied = Uint8Array.from(signature.match(/../g),part=>parseInt(part,16));
    if (!await crypto.subtle.verify('HMAC',key,supplied,raw)) return deny(403);
    let body;
    try { body = JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(raw)); } catch { return deny(400); }
    if (typeof body.webhookTimestamp !== 'number' || !Number.isFinite(body.webhookTimestamp) ||
        Math.abs(Date.now()-body.webhookTimestamp)>60000 ||
        body.organizationId !== env.CODEX_ORGANIZATION_ID ||
        body.type !== 'AgentSessionEvent') return deny(403);
    const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',raw)))
      .map(b=>b.toString(16).padStart(2,'0')).join('');
    const headers = new Headers({
      'Content-Type':'application/json',
      'Linear-Delivery':delivery,
      'X-RRAS-Codex-Verified':'v1',
      'X-RRAS-Codex-Body-SHA256':digest,
      'X-RRAS-Codex-Bridge':env.CODEX_N8N_BRIDGE_SECRET
    });
    try {
      const response = await fetch(target.toString(),{method:'POST',headers,body:raw,
        redirect:'error',signal:AbortSignal.timeout(3500)});
      // Preserve non-2xx/uncertain intake for Linear's retry; never acknowledge a
      // merely forwarded request or leak an internal response body.
      return new Response(response.ok ? 'Accepted' : 'Codex intake unavailable',
        {status:response.ok ? 200 : 503});
    } catch { return deny(503); }
  }
};
