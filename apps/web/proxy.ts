import { NextRequest, NextResponse } from "next/server";

/** Redirect browser navigation to login; API calls retain their JSON 401 contract. */
export function proxy(request: NextRequest) {
  if (request.cookies.get("id_token")?.value) return NextResponse.next();
  const login = new URL("/login", request.url);
  const next = `${request.nextUrl.pathname}${request.nextUrl.search}`;
  if (next !== "/") login.searchParams.set("next", next);
  return NextResponse.redirect(login);
}

export const config = {
  matcher: ["/((?!login|auth|api|_next|favicon.ico).*)"],
};
