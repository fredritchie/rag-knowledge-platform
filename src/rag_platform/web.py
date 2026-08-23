# ruff: noqa: E501
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from rag_platform.config import Settings
from rag_platform.generation.service import GenerationService
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

    @app.get("/", response_class=HTMLResponse)
    def home() -> str:
        return _HTML

    @app.post("/api/search")
    def search(request: QueryRequest) -> dict[str, object]:
        results, latency = get_retrieval().search(request.query, top_k=request.top_k)
        return {
            "query": request.query,
            "latency_ms": latency,
            "results": [r.model_dump() for r in results],
        }

    @app.post("/api/ask")
    def ask(request: QueryRequest) -> dict[str, object]:
        service = GenerationService(settings, retrieval=get_retrieval())
        return service.answer(request.query).model_dump()

    return app


_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>RAG Developer Search</title>
<style>body{font:16px system-ui;max-width:900px;margin:3rem auto;padding:0 1rem;background:#f6f7f9;color:#17202a}form{display:flex;gap:.5rem}input{flex:1;padding:.8rem}button{padding:.8rem 1rem}.result{background:white;margin:1rem 0;padding:1rem;border-radius:8px;box-shadow:0 1px 4px #ccd}small{color:#59636e}pre{white-space:pre-wrap}</style></head>
<body><h1>Developer Search</h1><form id="form"><input id="query" value="What is zero trust?" aria-label="Query"><button>Search</button></form><p id="meta"></p><main id="results"></main>
<script>form.onsubmit=async(e)=>{e.preventDefault();results.innerHTML='Searching…';let r=await fetch('/api/search',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({query:query.value})});let d=await r.json();if(!r.ok){results.textContent=d.detail;return}meta.textContent=`${d.results.length} results in ${d.latency_ms.toFixed(1)} ms`;results.innerHTML=d.results.map((x,i)=>`<article class="result"><b>${i+1}. ${x.filename}</b><br><small>Page ${x.page} · Score ${x.score.toFixed(4)} · ${x.chunk_id}</small><pre>${x.text}</pre></article>`).join('')}</script></body></html>"""
