import json

from fastapi import HTTPException, Request


async def bounded_json(request: Request, limit: int) -> dict:
    """No multipart spooling or temporary files; reject large bodies early."""
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
        raise HTTPException(415, "Content-Type must be application/json")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > limit:
            raise HTTPException(413, "Request body too large")
    try:
        payload = json.loads(data)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(400, "Invalid JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(422, "Expected a JSON object")
    return payload
