# Apps

`web/` contains the Phase 6–10 Next.js TypeScript application. It uses the App Router and proxies
browser calls through same-origin route handlers so PostgreSQL, Qdrant, Ollama, and S3 remain
backend-only. The administration page includes event-queue/DLQ health and the Google Drive
connect, disconnect, force, pause, resume, last-sync, and error controls.

```bash
make frontend-install
cp apps/web/.env.example apps/web/.env.local
make frontend-dev
```
