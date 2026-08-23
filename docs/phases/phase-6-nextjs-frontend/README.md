# Phase 6 — Next.js Production Frontend

## Objective and boundary

`apps/web` is a Next.js TypeScript App Router application. Browsers communicate only with Next.js.
A same-origin route handler proxies authenticated requests to FastAPI, so Qdrant, PostgreSQL,
Ollama, and S3 credentials/endpoints are never exposed as browser database clients.

## Implemented screens

- Cognito login handoff, authorization-code callback, forgot-password handoff, SSO, and logout.
- Dashboard cards for documents, indexed/failed counts, queries, uploads, Drive and system status.
- Chat with grounded answers, expandable citations, page/chunk metadata, copy and feedback controls.
- Documents table with name, source, status, updated time and detail navigation.
- Direct-to-S3 PDF upload using browser SHA-256, presigned POST, and completion acknowledgement.
- Document detail metadata, checksum/version, pages/chunks, embedding version, permissions, activity,
  reindex/delete controls, and visual pipeline progress.
- Ingestion-stage screen.
- Platform-style admin surface for users, tenants, roles, documents, jobs, Drive, models, prompts,
  collections, health, deployment, audit, and alerts.

## Authentication flow

The login page redirects to Cognito Hosted UI. The callback exchanges the authorization code on
the Next.js server and stores the ID token in an HTTP-only, same-site cookie. Server components and
the backend proxy attach that token as a bearer credential. Client JavaScript cannot read it.

Configure `apps/web/.env.local` from `.env.example`. Use HTTPS and secure cookies in production,
configure exact Cognito callback/logout URLs, and add CSRF/state/nonce validation before public use.

## Direct upload flow

The browser hashes the PDF, requests authorization from FastAPI, submits the presigned form directly
to S3, then acknowledges completion. AWS credentials never reach the browser. Server-side encryption
fields are included in the signed policy.

## Run and build

```bash
make frontend-install
cp apps/web/.env.example apps/web/.env.local
make frontend-dev
cd apps/web && npm run build
```

The production build uses standalone output and strict TypeScript. The current interface is a
functional application foundation; wire reindex/delete buttons, streaming transport, retry,
feedback persistence, and full admin CRUD as their backend endpoints mature.

## Exit checklist

- [ ] Production build completes with strict TypeScript.
- [ ] Cognito callback sets only HTTP-only secure production cookies.
- [ ] Browser network traffic never connects directly to databases, Qdrant, or Ollama.
- [ ] Viewer/editor/admin navigation and controls reflect backend authorization.
- [ ] Upload, chat, documents, detail, pipeline, dashboard, and admin screens are exercised.
- [ ] Citation source/page/chunk expansion matches FastAPI response metadata.
- [ ] Responsive and keyboard/accessibility review is complete.
