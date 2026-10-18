export function json(response, status, value) {
  response.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
  response.end(JSON.stringify(value));
}

function materialSelection(url) {
  const selection = {};
  for (const key of ['startPage', 'endPage', 'startParagraph', 'endParagraph']) {
    if (url.searchParams.has(key)) selection[key] = Number(url.searchParams.get(key));
  }
  return Object.keys(selection).length ? selection : undefined;
}

async function body(request, maximumBytes = 800000) {
  if (!request.headers['content-type']?.startsWith('application/json') || request.headers['x-co-math-request'] !== '1') {
    throw Object.assign(new Error('请求格式不正确，请从研究工作台操作。'), { status: 403 });
  }
  let bytes = 0;
  const chunks = [];
  for await (const chunk of request) {
    bytes += chunk.length;
    if (bytes > maximumBytes) throw Object.assign(new Error('请求过大。'), { status: 413 });
    chunks.push(chunk);
  }
  try {
    const value = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error();
    return value;
  } catch { throw Object.assign(new Error('请求内容不是有效的 JSON。'), { status: 400 }); }
}

export function createApi(core, model, runs) {
  return async (request, response, url) => {
    if (!url.pathname.startsWith('/api/')) return false;
    try {
      const method = request.method;
      if (method === 'GET' && url.pathname === '/api/health') {
        json(response, 200, { ready: !core.failed, model: model.status().configured }); return true;
      }
      if (url.pathname === '/api/settings') {
        if (method === 'GET') json(response, 200, model.status());
        else if (method === 'PUT') {
          if (runs.active.size) throw Object.assign(new Error('请等待或停止正在进行的回答，再修改模型设置。'), { status: 409 });
          json(response, 200, await model.save(await body(request)));
        } else json(response, 405, { error: '不支持的操作。' });
        return true;
      }
      if (method === 'POST' && url.pathname === '/api/settings/select') {
        json(response, 200, await model.select(await body(request))); return true;
      }
      if (method === 'POST' && url.pathname === '/api/settings/models') {
        json(response, 200, await model.listModels(await body(request))); return true;
      }
      if (method === 'POST' && url.pathname === '/api/skills/library') {
        const input = await body(request);
        json(response, 200, await core.call('skill.connect', { directory: input.directory })); return true;
      }
      const profileMatch = url.pathname.match(/^\/api\/settings\/profiles\/([a-zA-Z0-9_-]{1,64})$/);
      if (method === 'DELETE' && profileMatch) {
        await body(request);
        if (runs.active.size) throw Object.assign(new Error('请等待正在进行的回答结束，再删除配置。'), { status: 409 });
        json(response, 200, await model.remove(profileMatch[1])); return true;
      }
      if (url.pathname === '/api/projects') {
        if (method === 'GET') json(response, 200, await core.call('project.list'));
        else if (method === 'POST') json(response, 201, await core.call('project.create', await body(request)));
        else json(response, 405, { error: '不支持的操作。' });
        return true;
      }
      if (method === 'POST' && url.pathname === '/api/projects/open') {
        json(response, 200, await core.call('project.open', await body(request))); return true;
      }
      if (method === 'GET' && url.pathname === '/api/project-folders') {
        json(response, 200, await core.call('project.browse', { path: url.searchParams.get('path') })); return true;
      }
      const match = url.pathname.match(/^\/api\/projects\/([a-f0-9]{32})(?:\/(files|file|materials|download|preview|notes|chat|runs|events|cancel|skills|skill))?$/);
      if (!match) { json(response, 404, { error: '接口不存在。' }); return true; }
      const [, projectId, action] = match;
      const params = { projectId };
      if (method === 'GET' && !action) json(response, 200, await core.call('project.read', params));
      else if (method === 'GET' && action === 'skills') json(response, 200, await core.call('skill.list', params));
      else if (method === 'GET' && action === 'skill') json(response, 200, await core.call('skill.read', { ...params, source: url.searchParams.get('source'), path: url.searchParams.get('path') }));
      else if (method === 'GET' && action === 'files') json(response, 200, await core.call('file.list', { ...params,
        directory: url.searchParams.get('directory'), query: url.searchParams.get('query'),
        offset: url.searchParams.get('offset'), limit: url.searchParams.get('limit') }));
      else if (method === 'GET' && action === 'file') json(response, 200, await core.call('file.read', { ...params,
        path: url.searchParams.get('path'), selection: materialSelection(url) }));
      else if (method === 'POST' && action === 'materials') {
        const input = await body(request, 15_000_000);
        json(response, 201, await core.call('material.import', { ...params, name: input.name, data: input.data }));
      }
      else if (method === 'GET' && ['download', 'preview'].includes(action)) {
        const file = await core.call('file.download', { ...params, path: url.searchParams.get('path') });
        if (action === 'preview' && !file.name.toLowerCase().endsWith('.pdf')) throw Object.assign(new Error('此格式请下载原文件查看。'), { status: 400 });
        const bytes = Buffer.from(file.data, 'base64');
        const filename = encodeURIComponent(file.name).replace(/[!'()*]/g, character => '%' + character.charCodeAt(0).toString(16));
        response.writeHead(200, { 'Content-Type': action === 'preview' ? 'application/pdf' : 'application/octet-stream', 'Content-Length': bytes.length,
          'Content-Disposition': `${action === 'preview' ? 'inline' : 'attachment'}; filename="material"; filename*=UTF-8''${filename}`,
          'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'; sandbox", 'Cache-Control': 'no-store' });
        response.end(bytes);
      }
      else if (method === 'GET' && action === 'chat') json(response, 200, await core.call('chat.read', params));
      else if (method === 'POST' && action === 'notes') json(response, 201, await core.call('note.create', { ...await body(request), ...params }));
      else if (method === 'POST' && action === 'runs') json(response, 202, await runs.start(projectId, await body(request)));
      else if (method === 'POST' && action === 'cancel') { await body(request); json(response, 200, runs.cancel(projectId)); }
      else if (method === 'GET' && action === 'events') {
        await core.call('project.read', params);
        response.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store', Connection: 'keep-alive', 'X-Accel-Buffering': 'no' });
        response.write(': connected\n\n');
        const send = message => {
          if (!response.destroyed && !response.writableEnded) {
            if (response.writableLength > 1_000_000) { response.end(); return; }
            response.write(`data: ${JSON.stringify(message)}\n\n`);
          }
        };
        const unsubscribe = runs.subscribe(projectId, send);
        const active = runs.active.get(projectId)?.message;
        if (active) send(active);
        const heartbeat = setInterval(() => response.write(': connected\n\n'), 15000);
        response.on('close', () => { clearInterval(heartbeat); unsubscribe(); });
      } else json(response, 405, { error: '不支持的操作。' });
    } catch (error) {
      if (!response.headersSent) json(response, error.status || 500, { error: error.message || '操作失败，请重试。' });
      else response.end();
    }
    return true;
  };
}
