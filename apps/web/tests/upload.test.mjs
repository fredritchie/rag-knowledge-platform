import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import test from "node:test";
import ts from "typescript";

const compiled = ts.transpileModule(readFileSync(new URL("../lib/upload.ts", import.meta.url), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;

for (const scenario of ["success", "network", "s3", "confirmation", "authorization", "invalid-json"]) {
  test(`upload handles ${scenario} without an unhandled rejection`, async () => {
    const calls = [], messages = [], exports = {};
    const fetch = async (url) => {
      calls.push(url);
      if (calls.length === 1) {
        if (scenario === "invalid-json") return new Response("not json");
        return Response.json({ message: "Not authorized", upload_url: "https://storage.example",
          upload_fields: { key: "test" }, document_id: "doc", document_version_id: "ver" },
        { status: scenario === "authorization" ? 403 : 201 });
      }
      if (calls.length === 2 && scenario === "network") throw new TypeError("Failed to fetch");
      return new Response(null, { status: scenario === "s3" && calls.length === 2 ? 403
        : scenario === "confirmation" && calls.length === 3 ? 500 : 204 });
    };
    runInNewContext(compiled, { exports, fetch, crypto, FormData, Uint8Array, Error, TypeError });
    await exports.uploadDocument(new File(["pdf"], "test.pdf", { type: "application/pdf" }), m => messages.push(m));
    if (scenario === "success") assert.match(messages.at(-1), /Upload received/);
    else assert.doesNotMatch(messages.at(-1), /Upload received/);
    if (["network", "s3"].includes(scenario)) assert.equal(calls.length, 2);
    if (["authorization", "invalid-json"].includes(scenario)) assert.equal(calls.length, 1);
    if (scenario === "confirmation") assert.match(messages.at(-1), /confirmation failed/);
    if (scenario === "network") assert.match(messages.at(-1), /CORS/);
  });
}
