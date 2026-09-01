import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}));
  const tenantId = typeof body.tenant_id === "string" ? body.tenant_id : "";
  if (!/^ten_[a-zA-Z0-9]+$/.test(tenantId)) return NextResponse.json({ code: "INVALID_TENANT" }, { status: 400 });
  const response = NextResponse.json({ tenant_id: tenantId });
  response.cookies.set("active_tenant_id", tenantId, { httpOnly: true, sameSite: "lax", secure: process.env.NODE_ENV === "production", path: "/" });
  return response;
}
