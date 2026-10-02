import { NextResponse } from "next/server";
import { appUrl } from "../../../lib/app-url";

export async function GET() {
  const logoutUrl = new URL(process.env.COGNITO_LOGOUT_URL!);
  logoutUrl.search = new URLSearchParams({
    client_id: process.env.COGNITO_CLIENT_ID!,
    logout_uri: new URL("/login", appUrl()).toString(),
  }).toString();
  const response = NextResponse.redirect(logoutUrl);
  response.cookies.delete("id_token");
  return response;
}
