# Phase 7 Exit-Criteria Runbook

This runbook records the reproducible staging procedure for validating Phase 7
authentication, RBAC, and tenant isolation. Use a separate Cognito User Pool and
test database; do not place passwords, JWTs, Terraform state, or production values
in Git.

## What this procedure proves

- Cognito ID tokens are verified by the API.
- The token subject and tenant claim must match an active PostgreSQL membership.
- Admin and Viewer capabilities differ at protected routes.
- Tenant A and Tenant B cannot see one another's user or audit data through the
  currently implemented Phase 7 routes.

It does not complete the JWKS-rotation, invalid-token, Qdrant-filter, or
answer-trace criteria. Those remaining checks are listed at the end.

## 1. Start the Phase 7 services

Use the Phase 7 branch and apply the schema:

```bash
git switch phase-7
make migrate
```

Start the API in a dedicated terminal. The environment values must be exported
into the process that runs `make api`; the current API launcher does not load a
root `.env` file automatically.

```bash
cd ~/rag-knowledge-platform
source .venv/bin/activate

export RAG__AUTH__ENABLED=true
export RAG__AUTH__ISSUER="https://cognito-idp.<region>.amazonaws.com/<user-pool-id>"
export RAG__AUTH__AUDIENCE="<app-client-id>"
export RAG__AUTH__JWKS_CACHE_SECONDS=30

make api
```

In a separate terminal, verify service and database readiness:

```bash
curl http://127.0.0.1:8080/live
curl http://127.0.0.1:8080/ready
```

Both endpoints must return `200` with `{"status":"ok"}` and
`{"status":"ready"}` respectively.

## 2. Provision the Cognito test environment

The Terraform configuration is in [`terraform/cognito`](../../../terraform/cognito).
Create a local variable file with a globally unique Cognito domain prefix and the
callback URLs:

```hcl
aws_region = "ap-south-1"
name       = "replace-with-unique-phase7-dev"

callback_urls = [
  "http://localhost:3000/auth/callback",
]

logout_urls = [
  "http://localhost:3000",
]
```

Apply and retrieve the public configuration values:

```bash
cd terraform/cognito
terraform init
terraform plan
terraform apply

terraform output -raw issuer
terraform output -raw app_client_id
terraform output -raw hosted_ui_base_url
```

The callback URL must use `https` for a public deployment. Cognito permits
`http://localhost` only for local testing. A public EC2 IP address over HTTP is
not a valid Cognito callback URL.

## 3. Run the frontend through an SSH tunnel

For local callback testing while the application runs on EC2, run the Next.js
frontend on the EC2 instance in a second dedicated terminal:

```bash
cd ~/rag-knowledge-platform/apps/web

export RAG_API_URL=http://127.0.0.1:8080
export NEXT_PUBLIC_APP_URL=http://localhost:3000
export NEXT_PUBLIC_COGNITO_AUTHORIZE_URL="<hosted-ui-base-url>/oauth2/authorize"
export COGNITO_TOKEN_URL="<hosted-ui-base-url>/oauth2/token"
export NEXT_PUBLIC_COGNITO_LOGOUT_URL="<hosted-ui-base-url>/logout"
export NEXT_PUBLIC_COGNITO_CLIENT_ID="<app-client-id>"

npm run dev -- --hostname 127.0.0.1 --port 3000
```

On the local workstation, keep a third terminal open for the tunnel:

```bash
ssh -N -o ExitOnForwardFailure=yes \
  -L 3000:127.0.0.1:3000 \
  -i ~/.ssh/<ec2-key> ubuntu@<ec2-public-ip>
```

Open `http://localhost:3000/login` in the browser. The browser must access the
frontend through the tunnel; do not use the EC2 public IP for the localhost
callback flow.

## 4. Bootstrap Tenant A and its Admin

Create a Cognito user with a real email, `custom:tenant_id=ten_demo_a`, and an
`ADMIN` group assignment. Suppress the invitation and explicitly set a permanent
password so no password-reset challenge is required:

```bash
aws cognito-idp admin-create-user \
  --region <region> \
  --user-pool-id <user-pool-id> \
  --username '<admin-email>' \
  --user-attributes \
    Name=email,Value='<admin-email>' \
    Name=email_verified,Value=true \
    Name=custom:tenant_id,Value=ten_demo_a \
  --message-action SUPPRESS

aws cognito-idp admin-set-user-password \
  --region <region> \
  --user-pool-id <user-pool-id> \
  --username '<admin-email>' \
  --password '<secure-test-password>' \
  --permanent

aws cognito-idp admin-add-user-to-group \
  --region <region> \
  --user-pool-id <user-pool-id> \
  --username '<admin-email>' \
  --group-name ADMIN
```

Retrieve the user's `sub`, then insert the application tenant, user, and active
membership. The application role comes from `tenant_memberships`, not solely from
the Cognito group.

```sql
INSERT INTO tenants (id, name, slug, status, settings)
VALUES ('ten_demo_a', 'Demo Tenant A', 'demo-tenant-a', 'ACTIVE', '{}'::jsonb);

INSERT INTO users (id, external_subject, email, display_name, status)
VALUES ('usr_demo_admin', '<cognito-sub>', '<admin-email>', 'Demo Admin', 'ACTIVE');

INSERT INTO tenant_memberships (id, tenant_id, user_id, role, groups, active)
VALUES (
  'mem_demo_admin',
  'ten_demo_a',
  'usr_demo_admin',
  'ADMIN',
  '["ADMIN"]'::jsonb,
  true
);
```

Sign in and verify the browser-backed API proxy:

```text
http://localhost:3000/api/backend/api/v1/auth/me
```

Expected fields include the application's `user_id`, the Cognito
`external_subject`, `tenant_id`, and `role: "ADMIN"`.

## 5. Verify Viewer RBAC

Create a second Cognito user with the same Tenant A custom attribute, then create
the matching application user and membership with role `VIEWER`. Use an incognito
browser window to prevent reuse of the Admin's HTTP-only `id_token` cookie.

After Viewer login:

```text
GET /api/backend/api/v1/auth/me       -> 200; role is VIEWER
GET /api/backend/api/v1/users         -> 403
GET /api/backend/api/v1/audit/events  -> 403
```

The first request must be opened through the Next.js proxy in the browser:

```text
http://localhost:3000/api/backend/api/v1/auth/me
```

A terminal `curl` call without an `Authorization` header correctly returns
`403 Missing bearer token`; it does not carry the browser's HTTP-only cookie.

## 6. Verify Tenant A versus Tenant B isolation

Create a second tenant and a second Cognito Admin user. The value of
`custom:tenant_id` and `tenant_memberships.tenant_id` must be identical. Verify
the values before signing in:

```bash
aws cognito-idp admin-get-user \
  --region <region> \
  --user-pool-id <user-pool-id> \
  --username '<tenant-b-admin-email>' \
  --query 'UserAttributes[?Name==`sub` || Name==`custom:tenant_id`].[Name,Value]' \
  --output table
```

If the browser returns `User is not an active member of this tenant`, compare the
token user's Cognito `sub` and `custom:tenant_id` against the database record:

```sql
SELECT
  u.email,
  u.external_subject,
  u.status AS user_status,
  tm.tenant_id,
  tm.role,
  tm.active
FROM users u
LEFT JOIN tenant_memberships tm ON tm.user_id = u.id
WHERE u.external_subject = '<cognito-sub>';
```

Use a fresh incognito session after changing Cognito user attributes; an existing
ID token retains the old claims.

As Tenant B Admin, verify:

```text
GET /api/backend/api/v1/auth/me       -> 200; Tenant B identity
GET /api/backend/api/v1/tenants/current -> Tenant B only
GET /api/backend/api/v1/users         -> Tenant B users only
GET /api/backend/api/v1/audit/events  -> Tenant B audit events only
```

Repeat the user-list check as Tenant A Admin. Tenant A must not receive the
Tenant B user, and Tenant B must not receive either Tenant A user.

## Evidence to retain

Record, without saving passwords or tokens:

- Terraform plan/apply output and the non-secret outputs used for configuration.
- `/live` and `/ready` `200` responses.
- Admin and Viewer `/auth/me` identity responses.
- Viewer `403` responses for `/users` and `/audit/events`.
- Tenant A and Tenant B user-list results showing no cross-tenant rows.
- The revision/commit deployed to the EC2 instance.

## Remaining Phase 7 exit work

- Exercise real Cognito JWKS rotation without API restart. The verifier should
  refresh and retry once when it receives an otherwise valid token with an
  unknown `kid`.
- Add automated tests for missing, expired, malformed, modified,
  wrong-audience, and wrong-issuer tokens.
- Add and test document, job, chat, and direct-ID routes for cross-tenant
  isolation.
- Capture Qdrant requests and assert both tenant and authorized-document filters.
- Write answer traces and assert unauthorized chunk IDs never appear in them.
