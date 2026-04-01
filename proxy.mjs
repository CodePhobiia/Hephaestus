import { streamSimpleAnthropic } from '/home/ubuntu/.npm-global/lib/node_modules/openclaw/node_modules/@mariozechner/pi-ai/dist/providers/anthropic.js';
import { readFileSync } from 'fs';
import { createServer } from 'http';

const store = JSON.parse(readFileSync(`${process.env.HOME}/.openclaw/agents/main/agent/auth-profiles.json`, 'utf8'));
const token = store.profiles['anthropic:default'].token;
console.log('[proxy] Loaded token:', token.substring(0, 25) + '...');

const server = createServer(async (req, res) => {
  if (req.method !== 'POST') { res.writeHead(405); res.end(); return; }
  let body = '';
  req.on('data', c => body += c);
  req.on('end', async () => {
    try {
      const params = JSON.parse(body);
      
      // Model config matching OpenClaw's format
      const model = {
        id: params.model,
        provider: 'anthropic',
        api: 'anthropic-messages',
        baseUrl: 'https://api.anthropic.com',
        maxTokens: 32000,
        input: ['text', 'image'],
        reasoning: false,
      };
      
      // Context: map messages to the pi-ai format
      const piMessages = params.messages.map(m => {
        if (m.role === 'user') return { role: 'user', content: typeof m.content === 'string' ? m.content : m.content };
        if (m.role === 'assistant') return { role: 'assistant', content: [{ type: 'text', text: typeof m.content === 'string' ? m.content : m.content.map(c => c.text).join('') }] };
        return m;
      });
      
      const context = {
        systemPrompt: params.system || '',
        messages: piMessages,
      };
      
      const opts = {
        apiKey: token,
        maxTokens: params.max_tokens || 4096,
        temperature: params.temperature,
      };
      
      console.log(`[proxy] ${params.model} | ${params.messages.length} msgs | max_tokens=${opts.maxTokens}`);
      
      const stream = streamSimpleAnthropic(model, context, opts);
      let result = null;
      for await (const event of stream) {
        if (event.type === 'done') { result = event.message; break; }
        if (event.type === 'error') {
          const err = event.error || event;
          throw new Error(err.errorMessage || err.reason || JSON.stringify(err));
        }
      }
      if (!result) throw new Error('No response');
      
      const text = result.content.filter(c => c.type === 'text').map(c => c.text).join('');
      const usage = result.usage || {};
      
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({
        content: [{ type: 'text', text }],
        model: result.model || params.model,
        usage: { input_tokens: usage.input || 0, output_tokens: usage.output || 0 },
        stop_reason: result.stopReason || 'stop',
      }));
      console.log(`[proxy] OK | ${text.length} chars | in=${usage.input} out=${usage.output}`);
    } catch (e) {
      console.error('[proxy] ERR:', e.message?.substring(0, 300));
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: e.message }));
    }
  });
});

server.listen(18999, '127.0.0.1', () => console.log('[proxy] Ready on http://127.0.0.1:18999'));
