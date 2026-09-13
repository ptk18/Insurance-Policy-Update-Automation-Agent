"""Bound request bodies before multipart parsing/spooling, including chunked uploads."""

from starlette.responses import JSONResponse


class RequestLimitMiddleware:
    def __init__(self, app, maximum=6 * 1024 * 1024):
        self.app = app
        self.maximum = maximum

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH"}:
            return await self.app(scope, receive, send)
        chunks = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body = message.get("body", b"")
            size += len(body)
            if size > self.maximum:
                return await JSONResponse(
                    {"detail": "Request body exceeds the demo limit"}, status_code=413
                )(scope, receive, send)
            chunks.append(body)
            if not message.get("more_body", False):
                break
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": b"".join(chunks), "more_body": False}

        await self.app(scope, bounded_receive, send)
