import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

async function proxy(request: NextRequest, context: { params: Promise<{ path:string[] }> }) {
  const token = (await cookies()).get("id_token")?.value;
  const tenantId = (await cookies()).get("active_tenant_id")?.value;
  if (!token) return NextResponse.json({code:"AUTH_REQUIRED"},{status:401});
  const { path } = await context.params;
  const headers: Record<string, string> = {authorization:`Bearer ${token}`,"content-type":request.headers.get("content-type") ?? "application/json"};
  if (tenantId) headers["x-tenant-id"] = tenantId;
  const response = await fetch(`${process.env.RAG_API_URL}/${path.join("/")}${request.nextUrl.search}`, { method:request.method, headers, body:["GET","HEAD"].includes(request.method)?undefined:await request.text(), cache:"no-store" });
  return new NextResponse(response.body,{status:response.status,headers:{"content-type":response.headers.get("content-type") ?? "application/json"}});
}
export const GET=proxy; export const POST=proxy; export const PUT=proxy; export const PATCH=proxy; export const DELETE=proxy;
