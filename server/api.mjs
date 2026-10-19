import { lstatSync, readdirSync, watch } from 'node:fs';
import { isAbsolute, join, relative, resolve, sep } from 'node:path';

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

function watchProject(project, send) {
  const watchers = new Map();
  const paths = new Set();
  let timer;
  let stopped = false;
  let unknown = false;
  let refresh = false;
  const closeWatchers = () => {
    for (const watcher of watchers.values()) { watcher.removeAllListeners(); watcher.close(); }
    watchers.clear();
  };
  const stop = () => { stopped = true; clearTimeout(timer); closeWatchers(); paths.clear(); };
  const unavailable = () => {
    if (stopped) return;
    stop();
    send({ type: 'watch-unavailable' });
  };
  const changed = (directory, event, filename) => {
    if (stopped) return;
    if (!filename) unknown = true;
    else {
      const target = resolve(directory, String(filename));
      const path = relative(project.path, target);
      if (!path || path === '..' || path.startsWith(`..${sep}`) || isAbsolute(path)) unknown = true;
      else {
        paths.add(path.split(sep).join('/'));
        if (paths.size > 100) { unknown = true; paths.clear(); }
        if (watchers.has(target)) unknown = true;
        if (event === 'rename') {
          try { if (lstatSync(target).isDirectory()) unknown = true; }
          catch { /* Deleted files are still reported by their relative path. */ }
        }
      }
    }
    refresh ||= event === 'rename';
    if (timer) return;
    timer = setTimeout(() => {
      timer = undefined;
      send(unknown || !paths.size ? { type: 'files-changed' } : { type: 'files-changed', paths: [...paths] });
      paths.clear();
      unknown = false;
      if (refresh) {
        refresh = false;
        closeWatchers();
        try { start(); } catch { unavailable(); }
      }
    }, 400);
    timer.unref();
  };
  const visit = directory => {
    const info = lstatSync(directory);
    if (!info.isDirectory() || info.isSymbolicLink() || watchers.size >= 256) throw new Error('Watch directory unavailable');
    const watcher = watch(directory, { persistent: false }, (event, filename) => changed(directory, event, filename));
    watchers.set(directory, watcher);
    watcher.on('error', unavailable);
    watcher.on('close', unavailable);
    // Watch directories individually so nested symlinks never lead outside the project.
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      if (entry.isDirectory() && !entry.isSymbolicLink() && !entry.name.startsWith('.')) visit(join(directory, entry.name));
    }
  };
  const start = () => {
    visit(project.workspace);
    const agents = join(project.path, '.agents');
    if (lstatSync(agents, { throwIfNoEntry: false })?.isSymbolicLink()) throw new Error('Watch directory unavailable');
    const skills = join(agents, 'skills');
    if (!lstatSync(skills, { throwIfNoEntry: false })) { send({ type: 'watch-unavailable' }); return; }
    visit(skills);
  };
  try { start(); } catch { unavailable(); }
  return stop;
}

export function createApi(core) {
  const streams = new Set();
  let closed = false;
  const api = async (request, response, url) => {
    if (!url.pathname.startsWith('/api/')) return false;
    try {
      if (closed) { json(response, 503, { error: '项目查看器正在关闭。' }); return true; }
      const method = request.method;
      if (method === 'GET' && url.pathname === '/api/health') {
        json(response, 200, { ready: !core.failed }); return true;
      }
      if (url.pathname === '/api/projects') {
        if (method === 'GET') json(response, 200, await core.call('project.list'));
        else json(response, 405, { error: '不支持的操作。' });
        return true;
      }
      if (method === 'POST' && url.pathname === '/api/projects/open') {
        json(response, 200, await core.call('project.open', await body(request))); return true;
      }
      if (method === 'GET' && url.pathname === '/api/project-folders') {
        json(response, 200, await core.call('project.browse', { path: url.searchParams.get('path') })); return true;
      }
      const match = url.pathname.match(/^\/api\/projects\/([a-f0-9]{32})(?:\/(files|file|download|preview|chat|events))?$/);
      if (!match) { json(response, 404, { error: '接口不存在。' }); return true; }
      const [, projectId, action] = match;
      const params = { projectId };
      if (method === 'GET' && !action) json(response, 200, await core.call('project.read', params));
      else if (method === 'GET' && action === 'files') json(response, 200, await core.call('file.list', { ...params,
        directory: url.searchParams.get('directory'), query: url.searchParams.get('query'),
        offset: url.searchParams.get('offset'), limit: url.searchParams.get('limit') }));
      else if (method === 'GET' && action === 'file') json(response, 200, await core.call('file.read', { ...params,
        path: url.searchParams.get('path'), selection: materialSelection(url) }));
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
      else if (method === 'GET' && action === 'events') {
        const project = await core.call('project.read', params);
        if (closed || response.destroyed || response.writableEnded) { response.end(); return true; }
        response.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store', Connection: 'keep-alive', 'X-Accel-Buffering': 'no' });
        response.write(': connected\n\n');
        const write = content => {
          if (!response.destroyed && !response.writableEnded) {
            if (response.writableLength > 1_000_000) { response.end(); return; }
            response.write(content);
          }
        };
        let stopWatch = () => {};
        const heartbeat = setInterval(() => write(': connected\n\n'), 15000);
        heartbeat.unref();
        const cleanup = () => {
          clearInterval(heartbeat);
          stopWatch();
          streams.delete(cleanup);
          response.off('close', cleanup);
          response.off('error', cleanup);
          if (!response.destroyed && !response.writableEnded) response.end();
        };
        streams.add(cleanup);
        response.once('close', cleanup);
        response.once('error', cleanup);
        stopWatch = watchProject(project, message => write(`data: ${JSON.stringify(message)}\n\n`));
      } else json(response, 405, { error: '不支持的操作。' });
    } catch (error) {
      if (!response.headersSent) json(response, error.status || 500, { error: error.message || '操作失败，请重试。' });
      else response.end();
    }
    return true;
  };
  api.close = () => { closed = true; for (const cleanup of streams) cleanup(); };
  return api;
}
