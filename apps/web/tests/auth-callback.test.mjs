import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { runInNewContext } from "node:vm";
import test from "node:test";
import ts from "typescript";
import { NextRequest } from "next/server.js";

// Execute the actual handler with isolated environment and token-exchange mocks.
function compile(path) {
  return ts.transpileModule(readFileSync(new URL(path, import.meta.url), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
}
const origin = "https://fred-rag-dev.duckdns.org";

function handler(fetch, appUrl = origin, route = "callback") {
  const exports = {};
  const process = { env: {
    APP_URL: appUrl, NODE_ENV: "production",
    NEXT_PUBLIC_APP_URL: "http://localhost:3000",
    COGNITO_CLIENT_ID: "test-client", COGNITO_TOKEN_URL: "https://identity.example/oauth2/token",
    COGNITO_AUTHORIZE_URL: "https://identity.example/oauth2/authorize",
    COGNITO_LOGOUT_URL: "https://identity.example/logout",
  } };
  const helper = {};
  runInNewContext(compile("../lib/app-url.ts"), { exports: helper, process, URL });
  const nativeRequire = createRequire(import.meta.url);
  runInNewContext(compile(`../app/auth/${route}/route.ts`), {
    exports, require: (name) => name === "../../../lib/app-url" ? helper : nativeRequire(name),
    URL, URLSearchParams, Buffer, fetch, process,
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
    /APP_URL is required/);
});

test("login uses runtime origin and retains PKCE and state cookies", async () => {
  const response = await handler(undefined, `${origin}/`, "login")();
  const location = new URL(response.headers.get("location"));
  assert.equal(location.searchParams.get("redirect_uri"), `${origin}/auth/callback`);
  assert.equal(location.searchParams.get("state"), response.cookies.get("oauth_state").value);
  assert.equal(location.searchParams.get("code_challenge_method"), "S256");
  assert.ok(response.cookies.get("oauth_verifier").value);
  assert.equal(response.cookies.get("oauth_state").httpOnly, true);
  assert.equal(response.cookies.get("oauth_state").secure, true);
});

test("logout uses runtime origin rather than the legacy build value", async () => {
  const response = await handler(undefined, `${origin}/`, "logout")();
  const location = new URL(response.headers.get("location"));
  assert.equal(location.searchParams.get("logout_uri"), `${origin}/login`);
  assert.equal(response.cookies.get("id_token").value, "");
});

test("all auth routes reject missing or unsafe origins", async () => {
  for (const route of ["login", "callback", "logout"]) {
    for (const value of ["", "javascript:alert(1)", "https://user:pass@example.com",
      `${origin}/path`, `${origin}?q=x`, `${origin}#fragment`]) {
      await assert.rejects(handler(undefined, value, route)(callback()), /APP_URL/);
    }
  }
});

test("missing callback cookies cannot bypass state validation", async () => {
  const request = new NextRequest(`${origin}/auth/callback?code=x&state=y`);
  const response = await handler(() => assert.fail("unexpected token request"))(request);
  assert.equal(response.headers.get("location"), `${origin}/login?error=invalid_callback`);
});
