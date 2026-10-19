import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { extname, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { CoreBridge } from './core-bridge.mjs';
import { createApi, json } from './api.mjs';

const core = new CoreBridge();
const root = fileURLToPath(new URL('../', import.meta.url));
const dist = resolve(root, 'dist');
const port = Number(process.env.PORT || 4175);
let vite;
let server;
let api;
let closing = false;
let ready = false;
async function close() {
  if (closing) return;
  closing = true;
  ready = false;
  const force = setTimeout(() => process.exit(1), 7000);
  force.unref();
  api?.close();
  server?.close();
  core.close();
  await vite?.close();
  server?.closeAllConnections();
  clearTimeout(force);
}
try {
  if (process.argv.includes('--dev')) {
    const { createServer: createVite } = await import('vite');
    vite = await createVite({ configFile: resolve(root, 'vite.config.ts'), server: { middlewareMode: true, hmr: false }, appType: 'spa' });
  } else await stat(resolve(dist, 'index.html'));
  api = createApi(core);
  const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.woff': 'font/woff', '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.svg': 'image/svg+xml' };
  server = createServer(async (request, response) => {
    response.setHeader('X-Content-Type-Options', 'nosniff');
    response.setHeader('Referrer-Policy', 'no-referrer');
    response.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'");
    try {
      const actualPort = server.address().port;
      const allowedHosts = [`127.0.0.1:${actualPort}`, `localhost:${actualPort}`];
      const host = request.headers.host;
      if (!allowedHosts.includes(host) || request.headers['sec-fetch-site'] === 'cross-site' || (request.headers.origin && request.headers.origin !== `http://${host}`)) {
        json(response, 403, { error: '请通过本机研究工作台地址访问。' }); return;
      }
      if (!ready) { json(response, 503, { error: '研究工作台正在启动或关闭，请稍后刷新。' }); return; }
      const url = new URL(request.url, `http://${host}`);
      if (await api(request, response, url)) return;
      if (vite) { vite.middlewares(request, response); return; }
      if (!['GET', 'HEAD'].includes(request.method)) { response.writeHead(405); response.end(); return; }
      let path = resolve(dist, '.' + decodeURIComponent(url.pathname));
      if (path !== dist && !path.startsWith(dist + sep)) { response.writeHead(404); response.end(); return; }
      if (!extname(path)) path = resolve(dist, 'index.html');
      const data = await readFile(path);
      response.writeHead(200, { 'Content-Type': types[extname(path)] || 'application/octet-stream', 'Cache-Control': 'no-cache' });
      response.end(request.method === 'HEAD' ? undefined : data);
    } catch (error) {
      if (!response.headersSent) json(response, error.code === 'ENOENT' ? 404 : 500, { error: '页面或文件无法读取，请检查构建和项目目录。' });
      else response.end();
    }
  });
  server.once('close', () => api.close());
  await new Promise((done, reject) => { server.once('error', reject); server.listen(port, '127.0.0.1', done); });
  await core.call('startup');
  ready = true;
  console.log(`Co-Math: http://127.0.0.1:${server.address().port}`);
  process.on('SIGINT', () => { void close(); });
  process.on('SIGTERM', () => { void close(); });
} catch (error) {
  console.error(error.code === 'ENOENT' ? '请先运行 npm run build，并检查 Python 环境。' : error.message);
  await close();
  process.exitCode = 1;
}
