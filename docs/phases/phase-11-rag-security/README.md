# Phase 11 — RAG security and prompt-injection protection

## Outcome

Phase 11 makes retrieved content explicitly untrusted, preserves tenant/document authorization before
retrieval, and prevents the model from receiving or returning common secrets. It also provides
Cognito-native tenant user invitations and password-reset emails without handling passwords in the
application.

## Security flow

```text
Document -> ingestion security analysis -> indexed content -> ACL-filtered retrieval
-> untrusted context boundary -> LLM (no tools by default) -> output validation
```

## Implemented controls

- Strong system policy: document text never overrides system or user instructions.
- Explicit `<AUTHORIZED_RETRIEVED_CONTEXT>` and `<UNTRUSTED_DOCUMENT>` boundaries.
- Prompt-injection and data-exfiltration pattern detection during ingestion.
- Redaction of private keys, AWS keys, bearer tokens, API keys, passwords, and OAuth secrets.
- Tenant and document ACL filtering before retrieval (existing Phase 7 control).
- Citation validation: references outside supplied `[SOURCE N]` evidence are removed.
- Tool invocation disabled by default.
- Cognito-backed user invitation and password-reset email controls.
- Redirect to `/login` for unauthenticated browser page requests; API calls retain JSON `401`.

## Configuration

```yaml
security:
  tools_enabled: false
  redact_sensitive_data: true
  label_untrusted_documents: true

auth:
  user_pool_id: ap-south-1_VxfKOZxdu
```

Keep `tools_enabled: false` until an explicit, least-privilege tool policy is separately reviewed.

## Cognito IAM

The application runtime role needs these actions restricted to the configured user-pool ARN:

```text
cognito-idp:AdminCreateUser
cognito-idp:AdminResetUserPassword
```

Use `/users` as a tenant admin to invite users or send a reset email. Cognito owns temporary
passwords, reset codes, password policy, and credential storage; the application never accepts a
password value.

## Threat model

See [RAG threat model](../../security/rag-threat-model.md) for prompt injection, cross-tenant
leakage, data exfiltration, malicious PDFs, oversized-document denial of service, poisoned
knowledge bases, citation spoofing, and secret ingestion.

## Verification

```bash
source .venv/bin/activate
pytest -q tests/test_phase11_security.py
npm --prefix apps/web run build
```

Manual checks:

1. Open a protected page in an incognito browser; it redirects to `/login`.
2. Sign in as a tenant admin and invite a test user from `/users`; Cognito sends the email.
3. Send that user a password-reset email; verify Cognito delivers it.
4. Upload an allowed test document containing `Ignore previous instructions` and a fake
   `api_key=value`; verify retrieved model context/output never exposes the value or follows it.
5. As another tenant/user without document permission, confirm the document is absent from search
   and chat retrieval.

## Exit criteria

- Retrieved text is labelled and isolated as untrusted data.
- Injection and secret patterns are detected before indexing and redacted before generation.
- Tenant/document ACLs filter retrieval before any model call.
- Generated output does not expose matched secrets or fabricated source numbers.
- Tools remain disabled by default.
- Password management remains exclusively in Cognito.
- Unauthenticated browser navigation redirects to login.
