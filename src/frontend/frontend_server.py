import html
import os

import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

# Load environment variables from .env file
load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Build paths
BUILD_DIR = os.path.join(os.path.dirname(__file__), "build")
INDEX_HTML = os.path.join(BUILD_DIR, "index.html")
BACKEND_BASE_URL = os.getenv("BACKEND_API_URL", "http://localhost:8000")

# Serve static files from build directory
app.mount(
    "/assets", StaticFiles(directory=os.path.join(BUILD_DIR, "assets")), name="assets"
)


@app.get("/")
async def serve_index():
    return FileResponse(INDEX_HTML)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/config")
async def get_config():
    auth_enabled = html.escape(os.getenv("AUTH_ENABLED", "false"))

    config = {
        "API_URL": "/api",
        "ENABLE_AUTH": auth_enabled,
    }
    return config


FORWARDED_HEADERS = {
    "x-ms-client-principal",
    "x-ms-client-principal-id",
    "x-ms-client-principal-name",
    "x-ms-client-principal-groups",
    "x-ms-client-principal-role",
    "x-ms-client-principal-roles",
}


@app.post("/api/chat")
async def proxy_chat(request: Request) -> Response:
    try:
        payload = await request.json()
    except Exception as exc:  # pragma: no cover - defensive guard
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    # Forward EasyAuth headers if present
    forward_headers = {k: v for k, v in request.headers.items() if k.lower() in FORWARDED_HEADERS}

    target_url = f"{BACKEND_BASE_URL.rstrip('/')}/api/chat"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            backend_response = await client.post(target_url, json=payload, headers=forward_headers)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Backend unavailable: {exc}") from exc

    return Response(
        content=backend_response.content,
        status_code=backend_response.status_code,
        media_type=backend_response.headers.get("content-type", "application/json"),
    )


@app.post("/api/user_browser_language")
async def proxy_user_browser_language(request: Request) -> Response:
    try:
        payload = await request.json()
    except Exception as exc:  # pragma: no cover - defensive guard
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    forward_headers = {k: v for k, v in request.headers.items() if k.lower() in FORWARDED_HEADERS}

    target_url = f"{BACKEND_BASE_URL.rstrip('/')}/api/user_browser_language"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            backend_response = await client.post(target_url, json=payload, headers=forward_headers)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Backend unavailable: {exc}") from exc

    return Response(
        content=backend_response.content,
        status_code=backend_response.status_code,
        media_type=backend_response.headers.get("content-type", "application/json"),
    )


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_backend_api(path: str, request: Request) -> Response:
    if request.method == "OPTIONS":
        # Handle pre-flight locally so App Service never forwards unsupported verbs
        return Response(status_code=204)

    target_url = f"{BACKEND_BASE_URL.rstrip('/')}/api/{path}"
    forward_headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in {"host", "connection", "keep-alive", "transfer-encoding", "content-length"}
    }
    params = dict(request.query_params)
    body = await request.body()

    try:
        async with httpx.AsyncClient(timeout=None) as client:
            req = client.build_request(
                request.method,
                target_url,
                headers=forward_headers,
                params=params,
                content=body if body else None,
            )
            backend_response = await client.send(req)
    except httpx.RequestError as exc:  # pragma: no cover - network guard
        raise HTTPException(status_code=502, detail=f"Backend unavailable: {exc}") from exc

    try:
        content = await backend_response.aread()
    finally:
        await backend_response.aclose()

    cleaned_headers = {
        k: v
        for k, v in backend_response.headers.items()
        if k.lower() not in {"content-length", "connection", "keep-alive", "transfer-encoding"}
    }

    return Response(
        content=content,
        status_code=backend_response.status_code,
        headers=cleaned_headers,
        media_type=backend_response.headers.get("content-type"),
    )
@app.get("/{full_path:path}")
async def serve_app(full_path: str):
    # Remediation: normalize and check containment before serving
    file_path = os.path.normpath(os.path.join(BUILD_DIR, full_path))
    # Block traversal and dotfiles
    if not file_path.startswith(BUILD_DIR) or ".." in full_path or "/." in full_path or "\\." in full_path:
        return FileResponse(INDEX_HTML)
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    return FileResponse(INDEX_HTML)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", default="local", help="Environment: local, dev, or prod")
    args = parser.parse_args()

    # Use port 8000 to match React app's default expectation
    uvicorn.run(app, host="127.0.0.1", port=8000)
