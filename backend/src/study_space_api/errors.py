from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


@dataclass(slots=True)
class APIError(Exception):
    status_code: int
    code: str
    message: str
    details: dict = field(default_factory=dict)


def request_id_for(request: Request | None = None) -> str:
    if request is not None:
        value = getattr(request.state, "request_id", None)
        if value:
            return value
    return f"req-{uuid.uuid4().hex}"


def error_payload(request_id: str, code: str, message: str, details: dict | None = None) -> dict:
    return {
        "schema_version": "1.0",
        "error": {"code": code, "message": message, "details": details or {}, "request_id": request_id},
    }


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        supplied = request.headers.get("x-request-id", "")
        request.state.request_id = supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else request_id_for()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response


class BodyLimitMiddleware:
    def __init__(self, app: object, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: dict, receive: object, send: object) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        content_length = dict(scope.get("headers", [])).get(b"content-length")
        if content_length is not None and int(content_length) > self.max_bytes:
            await self._reject(send)
            return
        received = 0

        async def limited_receive() -> dict:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise APIError(413, "PAYLOAD_TOO_LARGE", "Request body exceeds configured limit")
            return message

        try:
            await self.app(scope, limited_receive, send)
        except APIError as exc:
            if exc.code != "PAYLOAD_TOO_LARGE":
                raise
            await self._reject(send)

    async def _reject(self, send: object) -> None:
        req_id = request_id_for()
        body = json.dumps(error_payload(req_id, "PAYLOAD_TOO_LARGE", "Request body exceeds configured limit")).encode()
        await send({"type": "http.response.start", "status": 413, "headers": [(b"content-type", b"application/json"), (b"x-request-id", req_id.encode())]})
        await send({"type": "http.response.body", "body": body})


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def handle_api_error(request: Request, exc: APIError) -> JSONResponse:
        return JSONResponse(
            content=error_payload(request_id_for(request), exc.code, exc.message, exc.details),
            status_code=exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = {
            "errors": [
                {"type": item.get("type"), "loc": list(item.get("loc", ())), "msg": item.get("msg")}
                for item in exc.errors()
            ]
        }
        return JSONResponse(
            content=error_payload(request_id_for(request), "VALIDATION_ERROR", "Request validation failed", details),
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            content=error_payload(request_id_for(request), "INTERNAL_ERROR", "An unexpected server error occurred"),
            status_code=500,
        )
