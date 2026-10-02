import { NextRequest, NextResponse } from "next/server";
import { appUrl } from "../../../lib/app-url";

export async function GET() {
  // Link prefetches and browser GET/HEAD requests must never mutate a session.
  return new NextResponse(null, { status: 405, headers: { Allow: "POST", "Cache-Control": "no-store" } });
}

export async function POST(request: NextRequest) {
  const publicUrl = appUrl();
  if (request.headers.get("origin") !== publicUrl.origin) {
    return new NextResponse(null, { status: 403, headers: { "Cache-Control": "no-store" } });
  }
  const logoutUrl = new URL(process.env.COGNITO_LOGOUT_URL!);
  logoutUrl.search = new URLSearchParams({
    client_id: process.env.COGNITO_CLIENT_ID!,
    logout_uri: new URL("/login", publicUrl).toString(),
  }).toString();
  // Convert the form POST to a GET for Cognito's logout endpoint.
  const response = NextResponse.redirect(logoutUrl, 303);
  response.headers.set("Cache-Control", "no-store");
  response.cookies.delete("id_token");
  response.cookies.delete("active_tenant_id");
  return response;
}
