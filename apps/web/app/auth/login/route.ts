import { createHash, randomBytes } from "node:crypto";
import { NextResponse } from "next/server";

function requiredEnvironment(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
}

export async function GET() {
  const state = randomBytes(32).toString("base64url");
  const verifier = randomBytes(64).toString("base64url");
  const challenge = createHash("sha256").update(verifier).digest("base64url");
  const appUrl = requiredEnvironment("NEXT_PUBLIC_APP_URL");
  const authorizeUrl = new URL(requiredEnvironment("COGNITO_AUTHORIZE_URL"));
  authorizeUrl.search = new URLSearchParams({
    client_id: requiredEnvironment("COGNITO_CLIENT_ID"),
    response_type: "code",
    scope: "openid email profile",
    redirect_uri: `${appUrl}/auth/callback`,
    state,
    code_challenge: challenge,
    code_challenge_method: "S256",
  }).toString();

  const response = NextResponse.redirect(authorizeUrl);
  const cookieOptions = {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/auth/callback",
    maxAge: 600,
  };
  response.cookies.set("oauth_state", state, cookieOptions);
  response.cookies.set("oauth_verifier", verifier, cookieOptions);
  return response;
}
