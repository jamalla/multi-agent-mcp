from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from agents.supervisor import build_supervisor

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # demo only — lock this down in production
    allow_methods=["*"],
    allow_headers=["*"],
)

supervisor = None

class Query(BaseModel):
    question: str

@app.on_event("startup")
async def startup():
    global supervisor
    supervisor = await build_supervisor()

@app.post("/ask")
async def ask(q: Query):
    answer = await supervisor(q.question)
    return {"answer": answer}

@app.get("/", response_class=HTMLResponse)
async def home():
    return CHAT_HTML


CHAT_HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Multi-Agent MCP Demo</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 640px; margin: 40px auto; padding: 0 16px; }
    h1 { font-size: 20px; }
    #log { border: 1px solid #ccc; border-radius: 8px; padding: 12px; height: 380px; overflow-y: auto; margin-bottom: 12px; }
    .msg { margin: 8px 0; padding: 8px 12px; border-radius: 8px; white-space: pre-wrap; }
    .user { background: #e8f0ff; text-align: right; }
    .bot  { background: #f2f2f2; }
    #row { display: flex; gap: 8px; }
    input { flex: 1; padding: 10px; border: 1px solid #ccc; border-radius: 8px; }
    button { padding: 10px 16px; border: 0; border-radius: 8px; background: #4f46e5; color: #fff; cursor: pointer; }
    button:disabled { opacity: 0.5; }
  </style>
</head>
<body>
  <h1>Multi-Agent MCP Demo</h1>
  <p>Ask about weather or countries — the supervisor routes to the right agent.</p>
  <div id="log"></div>
  <div id="row">
    <input id="q" placeholder="e.g. What's the weather in Tokyo?" autofocus>
    <button id="send" onclick="ask()">Send</button>
  </div>
  <script>
    const log = document.getElementById('log');
    const input = document.getElementById('q');
    const btn = document.getElementById('send');

    function add(text, cls) {
      const d = document.createElement('div');
      d.className = 'msg ' + cls;
      d.textContent = text;
      log.appendChild(d);
      log.scrollTop = log.scrollHeight;
    }

    async function ask() {
      const question = input.value.trim();
      if (!question) return;
      add(question, 'user');
      input.value = '';
      btn.disabled = true;
      add('Thinking… (first request may take ~40s if the server was asleep)', 'bot');
      try {
        const r = await fetch('/ask', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question })
        });
        const data = await r.json();
        log.lastChild.textContent = data.answer;
      } catch (e) {
        log.lastChild.textContent = 'Error: ' + e.message;
      } finally {
        btn.disabled = false;
        input.focus();
      }
    }

    input.addEventListener('keydown', e => { if (e.key === 'Enter') ask(); });
  </script>
</body>
</html>
"""
