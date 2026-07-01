import uuid
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from agents.supervisor import build_supervisor

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # demo only: lock this down in production
    allow_methods=["*"],
    allow_headers=["*"],
)

supervisor = None

class Query(BaseModel):
    question: str
    session_id: str | None = None

@app.on_event("startup")
async def startup():
    global supervisor
    supervisor = await build_supervisor()

@app.post("/ask")
async def ask(q: Query):
    # session_id groups a conversation so context is kept across follow-ups.
    session_id = q.session_id or str(uuid.uuid4())
    return await supervisor(q.question, session_id)

@app.get("/", response_class=HTMLResponse)
async def home():
    return CHAT_HTML


CHAT_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Multi-Agent MCP Demo</title>
  <style>
    :root {
      --indigo: #4f46e5;
      --indigo-dark: #4338ca;
      --bg: #f7f7fb;
      --user: #4f46e5;
      --bot: #ffffff;
      --border: #e6e6ef;
      --muted: #6b7280;
    }
    * { box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
      margin: 0; background: var(--bg); color: #1f2937;
      min-height: 100vh; display: flex; justify-content: center;
    }
    .app { width: 100%; max-width: 720px; display: flex; flex-direction: column;
           height: 100vh; padding: 0 16px; }
    header { padding: 20px 4px 12px; }
    header h1 { font-size: 20px; margin: 0 0 4px; display: flex; align-items: center; gap: 8px; }
    #newchat { margin-left: auto; font-size: 12px; font-weight: 600; padding: 5px 12px;
               border: 1px solid var(--border); background: #fff; border-radius: 999px;
               color: #374151; cursor: pointer; }
    #newchat:hover { border-color: var(--indigo); color: var(--indigo); }
    header p { margin: 0; color: var(--muted); font-size: 14px; }
    .badge-live { font-size: 11px; font-weight: 600; color: #059669; background: #d1fae5;
                  padding: 2px 8px; border-radius: 999px; }
    #log { flex: 1; overflow-y: auto; padding: 8px 4px 16px; display: flex;
           flex-direction: column; gap: 14px; }
    .turn { display: flex; flex-direction: column; gap: 6px; max-width: 88%; }
    .turn.user { align-self: flex-end; align-items: flex-end; }
    .turn.bot  { align-self: flex-start; align-items: flex-start; }
    .bubble { padding: 11px 14px; border-radius: 14px; line-height: 1.5; font-size: 15px;
              white-space: pre-wrap; word-wrap: break-word; }
    .user .bubble { background: var(--user); color: #fff; border-bottom-right-radius: 4px; }
    .bot .bubble  { background: var(--bot); border: 1px solid var(--border);
                    border-bottom-left-radius: 4px; }
    .route { font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: 999px;
             display: inline-flex; align-items: center; gap: 5px; }
    .route.weather { background: #dbeafe; color: #1d4ed8; }
    .route.country { background: #fef3c7; color: #b45309; }
    .route.worldcup { background: #dcfce7; color: #15803d; }
    details.trace { font-size: 13px; color: var(--muted); border: 1px dashed var(--border);
                    border-radius: 10px; padding: 6px 10px; background: #fafafe; width: 100%; }
    details.trace summary { cursor: pointer; user-select: none; font-weight: 500; }
    .step { margin: 6px 0 0; padding-left: 6px; border-left: 2px solid var(--border); }
    .step .tool { font-family: ui-monospace, "SF Mono", Menlo, monospace; color: #4338ca;
                  font-size: 12.5px; }
    .step .io { font-family: ui-monospace, Menlo, monospace; font-size: 12px; color: #374151;
                white-space: pre-wrap; word-break: break-word; margin-top: 2px; }
    .dots span { animation: blink 1.2s infinite both; }
    .dots span:nth-child(2) { animation-delay: .2s; }
    .dots span:nth-child(3) { animation-delay: .4s; }
    @keyframes blink { 0%,80%,100% { opacity: .2 } 40% { opacity: 1 } }
    .chips { display: flex; flex-wrap: wrap; gap: 8px; padding: 4px 4px 10px; }
    .chip { font-size: 13px; padding: 6px 12px; border: 1px solid var(--border);
            background: #fff; border-radius: 999px; cursor: pointer; color: #374151; }
    .chip:hover { border-color: var(--indigo); color: var(--indigo); }
    #row { display: flex; gap: 8px; padding: 10px 4px 18px; }
    #q { flex: 1; padding: 12px 14px; border: 1px solid var(--border); border-radius: 12px;
         font-size: 15px; outline: none; }
    #q:focus { border-color: var(--indigo); box-shadow: 0 0 0 3px rgba(79,70,229,.12); }
    #send { padding: 12px 20px; border: 0; border-radius: 12px; background: var(--indigo);
            color: #fff; font-weight: 600; cursor: pointer; }
    #send:hover { background: var(--indigo-dark); }
    #send:disabled { opacity: .5; cursor: default; }
    footer.by { padding: 4px 4px 18px; color: var(--muted); font-size: 13px;
                border-top: 1px solid var(--border); margin-top: 2px; }
    footer.by strong { color: #374151; }
    footer.by a { color: var(--indigo); text-decoration: none; }
    footer.by a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <div class="app">
    <header>
      <h1>🧭 Multi-Agent MCP Demo <span class="badge-live">live</span>
          <button id="newchat" onclick="newChat()">New chat</button></h1>
      <p>Ask about weather, countries, or the FIFA World Cup 2026. A supervisor routes each question to the right specialist agent, and you can expand each answer to see the tools it called. Ask follow-ups like "what currency do they use there?" and it keeps the context.</p>
    </header>

    <div id="log"></div>

    <div class="chips" id="chips">
      <div class="chip" onclick="ask(this.textContent)">What's the weather in Tokyo?</div>
      <div class="chip" onclick="ask(this.textContent)">What currency does Brazil use?</div>
      <div class="chip" onclick="ask(this.textContent)">Upcoming World Cup matches?</div>
      <div class="chip" onclick="ask(this.textContent)">Who will win the next World Cup match?</div>
    </div>

    <div id="row">
      <input id="q" placeholder="Ask about weather or a country…" autofocus>
      <button id="send" onclick="ask()">Send</button>
    </div>

    <footer class="by">
      Built by <strong>Jamalla Zawia</strong> ·
      <a href="mailto:jamala.zawia@gmail.com">jamala.zawia@gmail.com</a>
    </footer>
  </div>

  <script>
    const log = document.getElementById('log');
    const input = document.getElementById('q');
    const btn = document.getElementById('send');
    const chips = document.getElementById('chips');

    // One conversation id per browser session; the server keeps context under it.
    let sessionId = crypto.randomUUID();
    function newChat() {
      sessionId = crypto.randomUUID();
      log.innerHTML = '';
      input.focus();
    }

    function esc(s) {
      return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }
    // tiny formatter: escape, then **bold**
    function fmt(s) {
      return esc(s).replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>');
    }

    function addUser(text) {
      const t = document.createElement('div');
      t.className = 'turn user';
      t.innerHTML = '<div class="bubble">' + esc(text) + '</div>';
      log.appendChild(t);
      log.scrollTop = log.scrollHeight;
    }

    function addBotLoading() {
      const t = document.createElement('div');
      t.className = 'turn bot';
      t.innerHTML = '<div class="bubble"><span class="dots"><span>●</span><span>●</span><span>●</span></span> ' +
                    '<span style="color:#6b7280">thinking… first request may take ~40s if the server was asleep</span></div>';
      log.appendChild(t);
      log.scrollTop = log.scrollHeight;
      return t;
    }

    function renderTrace(route, steps) {
      const cls = (route && route.destination) || 'country';
      const icons = { weather: '🌤️', country: '🌍', worldcup: '⚽' };
      const icon = icons[cls] || '🤖';
      let html = '<span class="route ' + cls + '">' + icon + ' routed to ' + esc(route.agent) + '</span>';
      if (steps && steps.length) {
        let inner = '';
        for (const s of steps) {
          if (s.kind === 'tool_call') {
            inner += '<div class="step"><span class="tool">🔧 ' + esc(s.tool) + '(' +
                     esc(JSON.stringify(s.args)) + ')</span></div>';
          } else {
            inner += '<div class="step"><span class="tool">📥 ' + esc(s.tool) + '</span>' +
                     '<div class="io">' + esc(s.output) + '</div></div>';
          }
        }
        html += '<details class="trace"><summary>Show reasoning (' + steps.length + ' step' +
                (steps.length === 1 ? '' : 's') + ')</summary>' + inner + '</details>';
      }
      return html;
    }

    async function ask(preset) {
      const question = (preset || input.value).trim();
      if (!question) return;
      addUser(question);
      input.value = '';
      btn.disabled = true;
      const loading = addBotLoading();
      try {
        const r = await fetch('/ask', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question, session_id: sessionId })
        });
        const data = await r.json();
        loading.innerHTML =
          (data.route ? renderTrace(data.route, data.steps) : '') +
          '<div class="bubble">' + fmt(data.answer || '(no answer)') + '</div>';
      } catch (e) {
        loading.innerHTML = '<div class="bubble">⚠️ Error: ' + esc(e.message) + '</div>';
      } finally {
        btn.disabled = false;
        input.focus();
        log.scrollTop = log.scrollHeight;
      }
    }

    input.addEventListener('keydown', e => { if (e.key === 'Enter') ask(); });
  </script>
</body>
</html>
"""
