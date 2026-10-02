import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { runInNewContext } from "node:vm";
import test from "node:test";
import ts from "typescript";
import { NextRequest } from "next/server.js";

// Execute the actual handler with isolated environment and token-exchange mocks.
const source = readFileSync(new URL("../app/auth/callback/route.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const origin = "https://fred-rag-dev.duckdns.org";

function handler(fetch, appUrl = origin) {
  const exports = {};
  runInNewContext(compiled, {
    exports, require: createRequire(import.meta.url), URL, URLSearchParams, Buffer, fetch,
    process: { env: {
      NEXT_PUBLIC_APP_URL: appUrl, NODE_ENV: "production",
      COGNITO_CLIENT_ID: "test-client", COGNITO_TOKEN_URL: "https://identity.example/oauth2/token",
    } },
  });
  return exports.GET;
}

function callback(query = "?code=test-code&state=test-state") {
  return new NextRequest(`http://0.0.0.0:3000/auth/callback${query}`, {
    headers: { cookie: "oauth_state=test-state; oauth_verifier=test-verifier" },
  });
}

test("invalid callback redirects to public login without exchanging tokens", async () => {
  const response = await handler(() => assert.fail("unexpected token request"))(callback(""));
  assert.equal(response.headers.get("location"), `${origin}/login?error=invalid_callback`);
});

test("state mismatch remains rejected", async () => {
  const response = await handler(() => assert.fail("unexpected token request"))(
    callback("?code=test-code&state=wrong"),
  );
  assert.equal(response.headers.get("location"), `${origin}/login?error=invalid_callback`);
});

test("token exchange failure redirects to public login", async () => {
  const response = await handler(async () => new Response("", { status: 400 }))(callback());
  assert.equal(response.headers.get("location"), `${origin}/login?error=token_exchange`);
});

test("successful callback uses public origin for token exchange and redirect", async () => {
  const response = await handler(async (_url, options) => {
    assert.equal(options.body.get("redirect_uri"), `${origin}/auth/callback`);
    assert.equal(options.body.get("code_verifier"), "test-verifier");
    return Response.json({ id_token: "test-token", expires_in: 3600 });
  }, `${origin}/`)(callback());
  assert.equal(response.headers.get("location"), `${origin}/`);
  assert.equal(response.cookies.get("id_token").value, "test-token");
  assert.equal(response.cookies.get("id_token").httpOnly, true);
  assert.equal(response.cookies.get("id_token").secure, true);
});

test("missing public URL fails closed instead of using the internal host", async () => {
  await assert.rejects(handler(() => assert.fail("unexpected token request"), "")(callback()),
    /NEXT_PUBLIC_APP_URL is required/);
});
