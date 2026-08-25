from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from rag_platform.config import Settings
from rag_platform.retrieval.service import RetrievalService


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int | None = Field(None, ge=1)


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="RAG Developer Search", version="0.1.0")
    retrieval: RetrievalService | None = None

    def get_retrieval() -> RetrievalService:
        nonlocal retrieval
        try:
            retrieval = retrieval or RetrievalService(settings)
            return retrieval
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
    def home() -> str:
        return _HTML

    @app.post("/api/search")
    def search(request: QueryRequest) -> dict[str, object]:
        try:
            results, latency = get_retrieval().search(request.query, top_k=request.top_k)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {
            "query": request.query,
            "latency_ms": latency,
            "results": [result.model_dump() for result in results],
        }

    return app


_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RAG Developer Search</title>
  <style>
    body {
      font: 16px system-ui;
      max-width: 900px;
      margin: 3rem auto;
      padding: 0 1rem;
      background: #f6f7f9;
      color: #17202a;
    }
    form { display: flex; gap: .5rem; }
    input { flex: 1; padding: .8rem; }
    button { padding: .8rem 1rem; }
    .result {
      background: white;
      margin: 1rem 0;
      padding: 1rem;
      border-radius: 8px;
      box-shadow: 0 1px 4px #ccd;
    }
    small { color: #59636e; }
    pre { white-space: pre-wrap; }
  </style>
</head>
<body>
  <h1>Developer Search</h1>
  <form id="form">
    <input id="query" value="What is zero trust?" aria-label="Query">
    <button>Search</button>
  </form>
  <p id="meta"></p>
  <main id="results"></main>
  <script>
    const escapeHtml = (value) => String(value).replace(
      /[&<>"']/g,
      (character) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "\"": "&quot;",
        "'": "&#039;"
      })[character]
    );
    form.onsubmit = async (event) => {
      event.preventDefault();
      results.textContent = "Searching…";
      const response = await fetch("/api/search", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ query: query.value })
      });
      const data = await response.json();
      if (!response.ok) {
        results.textContent = data.detail;
        return;
      }
      meta.textContent = `${data.results.length} results in ${data.latency_ms.toFixed(1)} ms`;
      results.innerHTML = data.results.map((item, index) => `
        <article class="result">
          <b>${index + 1}. ${escapeHtml(item.filename)}</b><br>
          <small>Page ${escapeHtml(item.page)} · Score ${item.score.toFixed(4)} ·
            ${escapeHtml(item.chunk_id)}</small>
          <pre>${escapeHtml(item.text)}</pre>
        </article>
      `).join("");
    };
  </script>
</body>
</html>
"""
