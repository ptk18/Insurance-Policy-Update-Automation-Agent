import { cookies } from "next/headers";

// Server-only: never expose the workspace bearer token to browser JavaScript.
export const SESSION = "policy_workspace";
export const backendUrl =
  process.env.POLICY_API_URL ||
  (process.env.POLICY_API_HOST
    ? `http://${process.env.POLICY_API_HOST}:8000`
    : "http://127.0.0.1:8000");
export const jsonError = (detail: string, status: number) =>
  Response.json(
    { detail },
    { status, headers: { "Cache-Control": "no-store" } },
  );

export function sameOrigin(request: Request) {
  const origin = request.headers.get("origin");
  if (!origin) return false;
  try {
    // Next may normalize request.url to its internal bind host. The browser's
    // Host header retains the public host/port; browser scripts cannot forge it.
    const url = new URL(origin);
    return (
      ["http:", "https:"].includes(url.protocol) &&
      url.host === request.headers.get("host")
    );
  } catch {
    return false;
  }
}

export async function backendFetch(path: string, init: RequestInit = {}) {
  const token = (await cookies()).get(SESSION)?.value;
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(`${backendUrl}${path}`, {
    ...init,
    headers,
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(25000),
  });
}
