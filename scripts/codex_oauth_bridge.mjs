#!/usr/bin/env node
/**
 * Native Codex OAuth bridge for Hephaestus.
 *
 * Uses the same underlying pi-ai Codex provider path OpenClaw uses:
 * - OAuth credentials from ~/.codex/auth.json
 * API: openai-codex-responses
 * Base URL: https://chatgpt.com/backend-api
 * Transport: native pi-ai provider (not `codex exec`)
 *
 * Input: JSON on stdin
 * Output: JSON on stdout
 */

import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const OPENCLAW_NODE_MODULES = process.env.OPENCLAW_NODE_MODULES
  || '/home/ubuntu/.npm-global/lib/node_modules/openclaw/node_modules';

async function importAbs(rel) {
  const p = path.join(OPENCLAW_NODE_MODULES, rel);
  return import(pathToFileURL(p).href);
}

const pi = await importAbs('@mariozechner/pi-ai/dist/index.js');
const oauth = await importAbs('@mariozechner/pi-ai/dist/utils/oauth/index.js');

const AUTH_PATH = path.join(process.env.HOME || '', '.codex', 'auth.json');

function decodeJwtPayload(token) {
  const parts = String(token || '').split('.');
  if (parts.length !== 3) throw new Error('Invalid JWT token format');
  return JSON.parse(Buffer.from(parts[1], 'base64url').toString('utf8'));
}

function extractAccountId(accessToken) {
  const payload = decodeJwtPayload(accessToken);
  const auth = payload['https://api.openai.com/auth'];
  const accountId = auth?.chatgpt_account_id;
  if (!accountId) throw new Error('No chatgpt_account_id in access token');
  return accountId;
}

async function loadAndRefreshAuth() {
  if (!fs.existsSync(AUTH_PATH)) {
    throw new Error(`Codex auth not found at ${AUTH_PATH}`);
  }
  const auth = JSON.parse(fs.readFileSync(AUTH_PATH, 'utf8'));
  if (auth.auth_mode !== 'chatgpt') {
    throw new Error('Codex auth mode is not chatgpt');
  }
  const tokens = auth.tokens || {};
  let access = tokens.access_token;
  let refresh = tokens.refresh_token;
  if (!access || !refresh) {
    throw new Error('Missing access_token or refresh_token in ~/.codex/auth.json');
  }

  const payload = decodeJwtPayload(access);
  const expMs = Number(payload.exp || 0) * 1000;
  if (Date.now() > expMs - 60_000) {
    const refreshed = await oauth.refreshOpenAICodexToken(refresh);
    access = refreshed.access;
    refresh = refreshed.refresh;
    auth.tokens.access_token = access;
    auth.tokens.refresh_token = refresh;
    auth.tokens.account_id = refreshed.accountId;
    auth.last_refresh = new Date().toISOString();
    fs.writeFileSync(AUTH_PATH, JSON.stringify(auth, null, 2));
  }

  return {
    access,
    refresh,
    accountId: tokens.account_id || extractAccountId(access),
  };
}

function buildModel(modelId = 'gpt-5.4') {
  return {
    id: modelId,
    name: modelId,
    api: 'openai-codex-responses',
    provider: 'openai-codex',
    baseUrl: 'https://chatgpt.com/backend-api',
    reasoning: true,
    input: ['text', 'image'],
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    contextWindow: 1050000,
    maxTokens: 128000,
  };
}

function normalizeMessages(messages) {
  const out = [];
  for (const m of messages || []) {
    if (!m || typeof m !== 'object') continue;
    if (m.role === 'user' && typeof m.content === 'string') {
      out.push({ role: 'user', content: m.content, timestamp: Date.now() });
      continue;
    }
    if (m.role === 'assistant' && Array.isArray(m.content)) {
      const content = [];
      for (const block of m.content) {
        if (!block || typeof block !== 'object') continue;
        if (block.type === 'text') {
          content.push({ type: 'text', text: String(block.text || '') });
        } else if (block.type === 'tool_use') {
          content.push({
            type: 'toolCall',
            id: String(block.id || ''),
            name: String(block.name || ''),
            arguments: block.input || {},
          });
        }
      }
      out.push({ role: 'assistant', content, api: 'openai-codex-responses', provider: 'openai-codex', model: 'gpt-5.4', usage: { input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}}, stopReason: 'stop', timestamp: Date.now() });
      continue;
    }
    if (m.role === 'user' && Array.isArray(m.content)) {
      for (const block of m.content) {
        if (block?.type === 'tool_result') {
          out.push({
            role: 'toolResult',
            toolCallId: String(block.tool_use_id || ''),
            toolName: String(block.name || ''),
            content: [{ type: 'text', text: String(block.content || '') }],
            isError: Boolean(block.is_error),
            timestamp: Date.now(),
          });
        }
      }
    }
  }
  return out;
}

function normalizeTools(tools) {
  return (tools || []).map((t) => ({
    name: t.name,
    description: t.description,
    parameters: t.input_schema || t.parameters || { type: 'object', properties: {} },
  }));
}

function extractResult(response) {
  const content_blocks = [];
  const tool_calls = [];
  let text = '';
  for (const block of response.content || []) {
    if (block.type === 'text') {
      const b = { type: 'text', text: block.text || '' };
      content_blocks.push(b);
      text += b.text;
    } else if (block.type === 'thinking') {
      content_blocks.push({ type: 'thinking', thinking: block.thinking || '', thinkingSignature: block.thinkingSignature || '' });
    } else if (block.type === 'toolCall') {
      const tc = {
        id: String(block.id || ''),
        name: String(block.name || ''),
        input: block.arguments || {},
      };
      content_blocks.push({ type: 'tool_use', id: tc.id, name: tc.name, input: tc.input });
      tool_calls.push(tc);
    }
  }
  return {
    text,
    content_blocks,
    tool_calls,
    input_tokens: response.usage?.input || 0,
    output_tokens: response.usage?.output || 0,
    total_tokens: response.usage?.totalTokens || 0,
    cost_usd: response.usage?.cost?.total || 0,
    model: response.model || 'gpt-5.4',
    stop_reason: response.stopReason || 'stop',
    response_id: response.responseId || null,
    raw: response,
  };
}

async function main() {
  const input = fs.readFileSync(0, 'utf8');
  const req = JSON.parse(input || '{}');
  const auth = await loadAndRefreshAuth();
  const model = buildModel(req.model || 'gpt-5.4');

  const options = {
    apiKey: auth.access,
    reasoning: req.reasoning || 'medium',
    reasoningEffort: req.reasoning_effort,
    reasoningSummary: req.reasoning_summary,
    maxTokens: req.max_tokens || 4096,
    sessionId: req.session_id,
  };

  let context;
  const systemPrompt = req.system || 'You are a helpful assistant.';

  if (req.kind === 'prompt_stream') {
    const messages = [{ role: 'user', content: String(req.prompt || ''), timestamp: Date.now() }];
    if (req.prefill) {
      messages.push({
        role: 'assistant',
        content: [{ type: 'text', text: String(req.prefill) }],
        api: 'openai-codex-responses',
        provider: 'openai-codex',
        model: model.id,
        usage: { input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}},
        stopReason: 'stop',
        timestamp: Date.now(),
      });
    }
    context = { systemPrompt, messages };
    const stream = pi.streamSimple(model, context, options);
    let accumulated = '';
    for await (const event of stream) {
      if (event.type === 'text_delta') {
        accumulated += event.delta || '';
        process.stdout.write(JSON.stringify({ type: 'delta', delta: event.delta || '', accumulated }) + '\n');
      }
    }
    const response = await stream.result();
    process.stdout.write(JSON.stringify({ type: 'final', result: extractResult(response) }) + '\n');
    return;
  }

  if (req.kind === 'tools') {
    context = {
      systemPrompt,
      messages: normalizeMessages(req.messages || []),
      tools: normalizeTools(req.tools || []),
    };
    const response = await pi.complete(model, context, options);
    process.stdout.write(JSON.stringify({ ok: true, result: extractResult(response) }));
    return;
  }

  // simple prompt mode
  const messages = [{ role: 'user', content: String(req.prompt || ''), timestamp: Date.now() }];
  if (req.prefill) {
    messages.push({
      role: 'assistant',
      content: [{ type: 'text', text: String(req.prefill) }],
      api: 'openai-codex-responses',
      provider: 'openai-codex',
      model: model.id,
      usage: { input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}},
      stopReason: 'stop',
      timestamp: Date.now(),
    });
  }
  context = {
    systemPrompt,
    messages,
  };
  const response = await pi.completeSimple(model, context, options);
  process.stdout.write(JSON.stringify({ ok: true, result: extractResult(response) }));
}

main().catch((err) => {
  const msg = err instanceof Error ? err.message : String(err);
  const stack = err instanceof Error ? (err.stack || '') : '';
  process.stdout.write(JSON.stringify({ ok: false, error: msg, stack }));
  process.exit(1);
});
