import { cookies } from "next/headers";
import { backendFetch, jsonError, sameOrigin, SESSION } from "@/lib/backend";

const id = "[a-zA-Z0-9-]+";
const routes: Record<string, RegExp[]> = {
  GET: [
    /^health$/,
    /^fixtures$/,
    new RegExp(`^fixtures/documents/${id}$`),
    /^cases$/,
    new RegExp(`^cases/${id}$`),
    new RegExp(`^cases/${id}/attachments/${id}(/content)?$`),
  ],
  POST: [
    /^cases$/,
    new RegExp(
      `^cases/${id}/(process|resume|retry|attachments|replies|approve|reject|execute)$`,
    ),
  ],
  PUT: [new RegExp(`^cases/${id}/proposal$`)],
};

async function proxy(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  const path = (await context.params).path.join("/");
  if (!routes[request.method]?.some((pattern) => pattern.test(path)))
    return jsonError("Not found.", 404);
  if (request.method !== "GET" && !sameOrigin(request))
    return jsonError("Request origin is not allowed.", 403);
  if (path !== "health" && !(await cookies()).get(SESSION)?.value)
    return jsonError("Open a guest workspace to continue.", 401);
  try {
    const headers = new Headers();
    const contentType = request.headers.get("content-type");
    if (contentType) headers.set("Content-Type", contentType);
    const body =
      request.method === "GET" ? undefined : await request.arrayBuffer();
    if (body && body.byteLength > 6 * 1024 * 1024)
      return jsonError("The attachment is too large (5 MB maximum).", 413);
    const upstream = await backendFetch(`/${path}`, {
      method: request.method,
      headers,
      body,
    });
    const responseHeaders = new Headers({
      "Cache-Control": "private, no-store",
    });
    for (const name of ["content-type", "content-disposition"]) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    return new Response(upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return jsonError(
      "The review service could not be reached. Refresh to check whether your last action was saved.",
      502,
    );
  }
}

export { proxy as GET, proxy as POST, proxy as PUT };
