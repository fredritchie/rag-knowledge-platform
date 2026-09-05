import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get("code");
  const state = request.nextUrl.searchParams.get("state");
  const expectedState = request.cookies.get("oauth_state")?.value;
  const verifier = request.cookies.get("oauth_verifier")?.value;
  if (!code || !state || !expectedState || !verifier || state !== expectedState) {
    return NextResponse.redirect(new URL("/login?error=invalid_callback", request.url));
  }
  const redirectUri = `${process.env.NEXT_PUBLIC_APP_URL}/auth/callback`;
  const body = new URLSearchParams({ grant_type:"authorization_code", client_id:process.env.COGNITO_CLIENT_ID!, code, redirect_uri:redirectUri, code_verifier:verifier });
  const headers: HeadersInit = { "content-type":"application/x-www-form-urlencoded" };
  if (process.env.COGNITO_CLIENT_SECRET) headers.authorization = `Basic ${Buffer.from(`${process.env.COGNITO_CLIENT_ID}:${process.env.COGNITO_CLIENT_SECRET}`).toString("base64")}`;
  const tokenResponse = await fetch(process.env.COGNITO_TOKEN_URL!, { method:"POST", headers, body, cache:"no-store" });
  if (!tokenResponse.ok) return NextResponse.redirect(new URL("/login?error=token_exchange", request.url));
  const tokens = await tokenResponse.json();
  const response = NextResponse.redirect(new URL("/", request.url));
  response.cookies.set("id_token", tokens.id_token, { httpOnly:true, secure:process.env.NODE_ENV==="production", sameSite:"lax", path:"/", maxAge:tokens.expires_in });
  response.cookies.delete("oauth_state");
  response.cookies.delete("oauth_verifier");
  return response;
}
