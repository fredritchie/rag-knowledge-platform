import "server-only";
import { cookies } from "next/headers";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const token = (await cookies()).get("id_token")?.value;
  if (!token) throw new Error("AUTH_REQUIRED");
  const response = await fetch(`${process.env.RAG_API_URL ?? "http://localhost:8080"}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${token}`,
      ...init?.headers,
    },
    cache: "no-store",
  });
  if (!response.ok) {
    const error = await response.text();
    throw new Error(`API_${response.status}: ${error}`);
  }
  return response.json() as Promise<T>;
}
