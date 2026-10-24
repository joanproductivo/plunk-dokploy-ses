// Sirve el MCP oficial de Plunk (@plunk/mcp) por HTTP para ponerlo detrás de mcp-auth-proxy.
// Solo escucha en la red interna del compose: el login lo exige el proxy de delante.
//
// Los clientes de la era 2025 van por sesiones con estado: así el servidor puede preguntar
// al usuario (elicitation) antes de un envío masivo. Sin sesión, Plunk rechazaría esos envíos.
// Los clientes del protocolo 2026-07-28 van por el manejador por petición del SDK.
import {randomUUID} from 'node:crypto';
import {createServer} from 'node:http';
import {createMcpHandler} from '@modelcontextprotocol/server';
import {NodeStreamableHTTPServerTransport, toNodeHandler} from '@modelcontextprotocol/node';
import {buildServer} from '@plunk/mcp';
import {loadConfig} from '/app/node_modules/@plunk/mcp/dist/config.js';

const MAX_BODY = 4 * 1024 * 1024;
const SESSION_IDLE_MS = 2 * 60 * 60 * 1000;
const port = Number(process.env.PORT || 3000);
const log = (message) => console.error('[plunk-mcp-http] ' + message);

const config = loadConfig();
const modern = toNodeHandler(
  createMcpHandler(() => buildServer(config), {legacy: 'reject', onerror: (error) => log(error.message)}),
  {onerror: (error) => log(error.message)},
);

// Sesiones de clientes 2025: id -> {transport, lastSeen}
const sessions = new Map();

setInterval(() => {
  const now = Date.now();
  for (const [id, session] of sessions) {
    if (now - session.lastSeen > SESSION_IDLE_MS) {
      sessions.delete(id);
      session.transport.close().catch(() => {});
    }
  }
}, 10 * 60 * 1000).unref();

function isInitialize(body) {
  return Array.isArray(body) ? body.some(isInitialize) : Boolean(body && body.method === 'initialize');
}

function jsonError(res, status, code, message) {
  res.writeHead(status, {'content-type': 'application/json'});
  res.end(JSON.stringify({jsonrpc: '2.0', id: null, error: {code, message}}));
}

async function handleSession(req, res, body) {
  const sessionId = req.headers['mcp-session-id'];
  if (sessionId) {
    const session = sessions.get(sessionId);
    if (!session) {
      // El cliente vuelve a inicializar al recibir 404 (p. ej. tras reiniciar el contenedor)
      jsonError(res, 404, -32001, 'Session not found');
      return;
    }
    session.lastSeen = Date.now();
    await session.transport.handleRequest(req, res, body);
    return;
  }
  if (req.method !== 'POST' || !isInitialize(body)) {
    jsonError(res, 400, -32000, 'Missing session: send initialize first');
    return;
  }
  const transport = new NodeStreamableHTTPServerTransport({
    sessionIdGenerator: () => randomUUID(),
    onsessioninitialized: (id) => sessions.set(id, {transport, lastSeen: Date.now()}),
    onsessionclosed: (id) => sessions.delete(id),
  });
  transport.onclose = () => {
    if (transport.sessionId) sessions.delete(transport.sessionId);
  };
  await buildServer(config).connect(transport);
  await transport.handleRequest(req, res, body);
}

async function readJson(req) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > MAX_BODY) throw new RangeError('body too large');
    chunks.push(chunk);
  }
  const text = Buffer.concat(chunks).toString('utf8');
  return text ? JSON.parse(text) : undefined;
}

// Deja en el log qué cliente se conecta y qué sabe hacer (nunca los argumentos de las herramientas)
const seenClients = new Set();
function logClient(body) {
  for (const message of Array.isArray(body) ? body : [body]) {
    const params = (message && message.params) || {};
    if (message && message.method === 'initialize') {
      log('initialize: cliente=' + JSON.stringify(params.clientInfo) + ' protocolo=' + params.protocolVersion +
        ' capacidades=' + JSON.stringify(params.capabilities));
      continue;
    }
    const meta = params._meta || {};
    const clientKeys = Object.keys(meta).filter((key) => /client|protocol/i.test(key));
    const summary = JSON.stringify(Object.fromEntries(clientKeys.map((key) => [key, meta[key]])));
    if (clientKeys.length && !seenClients.has(summary)) {
      seenClients.add(summary);
      log('cliente (protocolo nuevo): ' + summary);
    }
  }
}

createServer(async (req, res) => {
  try {
    const path = (req.url || '').split('?')[0];
    if (path === '/health') {
      res.writeHead(200, {'content-type': 'text/plain'});
      res.end('ok');
      return;
    }
    if (path !== '/mcp') {
      res.writeHead(404);
      res.end();
      return;
    }
    let body;
    if (req.method === 'POST') {
      try {
        body = await readJson(req);
      } catch (error) {
        const tooLarge = error instanceof RangeError;
        jsonError(res, tooLarge ? 413 : 400, -32700, tooLarge ? 'Request too large' : 'Parse error');
        return;
      }
      logClient(body);
    }
    // Sesión 2025: lleva cabecera de sesión, abre una (initialize) o es GET/DELETE de una sesión
    if (req.headers['mcp-session-id'] || req.method !== 'POST' || isInitialize(body)) {
      await handleSession(req, res, body);
    } else {
      modern(req, res, body);
    }
  } catch (error) {
    log(error.message);
    if (!res.headersSent) jsonError(res, 500, -32603, 'Internal error');
  }
}).listen(port, () => {
  const target = config.projects ? ' proyectos=' + Object.keys(config.projects).sort().join(',') : '';
  log('escuchando en :' + port + ' api=' + config.apiUrl + (config.readOnly ? ' (solo lectura)' : '') + target);
});
