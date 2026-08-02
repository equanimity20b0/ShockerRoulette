import os
import http
import logging
import urllib.parse

logger = logging.getLogger("GameServer")

def make_response(status, headers, body, legacy=True):
    if legacy:
        return status, headers, body
    status_code = int(status)
    reason_phrase = getattr(status, "phrase", "OK")
    try:
        from websockets.http11 import Response
        from websockets.datastructures import Headers
        return Response(status_code, reason_phrase, Headers(headers), body)
    except ImportError:
        return status, headers, body

class HttpHandler:
    # In-memory resource cache: { absolute_path -> (mtime, mime_type, bytes_content) }
    _cache = {}

    @staticmethod
    def serve_static(request_path, legacy=True):
        # 1. Map virtual directory paths to physical files
        if request_path == "/" or not request_path:
            request_path = "/index.html"
        elif request_path == "/player":
            request_path = "/player.html"

        web_dir = os.path.join(os.path.dirname(__file__), "web")
        rel_path = request_path.lstrip('/')
        safe_path = os.path.normpath(os.path.join(web_dir, rel_path))
        
        # 2. Enforce directory boundary check to prevent traversal attacks
        if safe_path.startswith(web_dir) and os.path.isfile(safe_path):
            try:
                # Get file modification timestamp for cache validation
                mtime = os.path.getmtime(safe_path)
                cached = HttpHandler._cache.get(safe_path)

                if cached and cached[0] == mtime:
                    mime_type, content = cached[1], cached[2]
                else:
                    # Detect MIME type based on extension
                    if safe_path.endswith(".html"):
                        mime_type = "text/html; charset=utf-8"
                    elif safe_path.endswith(".js"):
                        mime_type = "application/javascript"
                    elif safe_path.endswith(".css"):
                        mime_type = "text/css"
                    else:
                        mime_type = "application/octet-stream"

                    with open(safe_path, "rb") as f:
                        content = f.read()

                    # Save to cache
                    HttpHandler._cache[safe_path] = (mtime, mime_type, content)
                    logger.info(f"Loaded static file into memory cache: {request_path}")

                response_headers = [
                    ('Content-Type', mime_type),
                    ('Content-Length', str(len(content))),
                    ('Connection', 'close'),
                    ('Access-Control-Allow-Origin', '*')
                ]
                return make_response(http.HTTPStatus.OK, response_headers, content, legacy=legacy)
            except Exception as e:
                logger.error(f"Error serving static file {request_path}: {e}")
                return make_response(http.HTTPStatus.INTERNAL_SERVER_ERROR, [], b"Internal Server Error", legacy=legacy)

        return make_response(http.HTTPStatus.NOT_FOUND, [], b"Not Found", legacy=legacy)

    @staticmethod
    async def process_request(server, *args, **kwargs):
        # Supports websockets <= 12.0: process_request(path, headers)
        # Supports websockets >= 13.0: process_request(connection, request)
        if len(args) < 2:
            return None
            
        arg1, arg2 = args[0], args[1]
        if isinstance(arg1, str):
            path = arg1
            headers = arg2
        else:
            path = arg2.path
            headers = arg2.headers

        # 1. Detect if it's a WebSocket upgrade request
        upgrade_header = ""
        if hasattr(headers, "get"):
            upgrade_header = headers.get("Upgrade") or headers.get("upgrade") or ""
        if not upgrade_header and hasattr(headers, "items"):
            for k, v in headers.items():
                if k.lower() == "upgrade":
                    upgrade_header = v
                    break
        
        upgrade_header = str(upgrade_header).lower()
        if "websocket" in upgrade_header:
            return None # Allow standard WebSocket upgrade handshake
            
        # 2. Extract path
        url_parsed = urllib.parse.urlparse(path)
        request_path = url_parsed.path

        is_legacy = isinstance(arg1, str)
        return HttpHandler.serve_static(request_path, legacy=is_legacy)
