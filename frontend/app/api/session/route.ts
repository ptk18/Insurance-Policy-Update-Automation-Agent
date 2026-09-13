import { cookies } from "next/headers";
import { backendFetch, jsonError, sameOrigin, SESSION } from "@/lib/backend";

export async function GET() {
  return Response.json(
    { connected: Boolean((await cookies()).get(SESSION)?.value) },
    { headers: { "Cache-Control": "no-store" } },
  );
}

export async function POST(request: Request) {
  if (!sameOrigin(request))
    return jsonError("Request origin is not allowed.", 403);
  const jar = await cookies();
  if (jar.get(SESSION)?.value) return Response.json({ connected: true });
  try {
    const response = await backendFetch("/workspaces", { method: "POST" });
    if (!response.ok)
      return jsonError("Could not open a guest workspace.", response.status);
    const data = await response.json();
    jar.set(SESSION, data.token, {
      httpOnly: true,
      sameSite: "strict",
      secure:
        process.env.COOKIE_SECURE === "true" ||
        new URL(request.url).protocol === "https:",
      path: "/",
      maxAge: 60 * 60 * 24 * 7,
    });
    return Response.json({ connected: true });
  } catch {
    return jsonError(
      "The review service is unavailable. Check that the API is running.",
      502,
    );
  }
}

export async function DELETE(request: Request) {
  if (!sameOrigin(request))
    return jsonError("Request origin is not allowed.", 403);
  (await cookies()).delete(SESSION);
  return Response.json({ connected: false });
}
