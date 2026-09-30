import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const appUrl = process.env.NEXT_PUBLIC_APP_URL;
  if (!appUrl) throw new Error("NEXT_PUBLIC_APP_URL is required");
  const publicUrl = new URL(appUrl);
  if (!["http:", "https:"].includes(publicUrl.protocol)) {
    throw new Error("NEXT_PUBLIC_APP_URL must be an HTTP(S) URL");
  }
  const code = request.nextUrl.searchParams.get("code");
  const state = request.nextUrl.searchParams.get("state");
  const expectedState = request.cookies.get("oauth_state")?.value;
  const verifier = request.cookies.get("oauth_verifier")?.value;
  if (!code || !state || !expectedState || !verifier || state !== expectedState) {
    return NextResponse.redirect(new URL("/login?error=invalid_callback", publicUrl));
  }
  const redirectUri = new URL("/auth/callback", publicUrl).toString();
  const body = new URLSearchParams({ grant_type:"authorization_code", client_id:process.env.COGNITO_CLIENT_ID!, code, redirect_uri:redirectUri, code_verifier:verifier });
  const headers: HeadersInit = { "content-type":"application/x-www-form-urlencoded" };
  if (process.env.COGNITO_CLIENT_SECRET) headers.authorization = `Basic ${Buffer.from(`${process.env.COGNITO_CLIENT_ID}:${process.env.COGNITO_CLIENT_SECRET}`).toString("base64")}`;
  const tokenResponse = await fetch(process.env.COGNITO_TOKEN_URL!, { method:"POST", headers, body, cache:"no-store" });
  if (!tokenResponse.ok) return NextResponse.redirect(new URL("/login?error=token_exchange", publicUrl));
  const tokens = await tokenResponse.json();
  const response = NextResponse.redirect(new URL("/", publicUrl));
  response.cookies.set("id_token", tokens.id_token, { httpOnly:true, secure:process.env.NODE_ENV==="production", sameSite:"lax", path:"/", maxAge:tokens.expires_in });
  response.cookies.delete("oauth_state");
  response.cookies.delete("oauth_verifier");
  return response;
}
