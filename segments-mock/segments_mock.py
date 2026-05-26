from __future__ import annotations

import json
import os
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


STATE_FILE = Path(os.getenv("SEGMENTS_STATE_FILE", "/data/segments.json"))
PORT = int(os.getenv("PORT", "8091"))
LOCK = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_state() -> list[dict]:
    if not STATE_FILE.exists():
        return []
    try:
        with STATE_FILE.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def save_state(segments: list[dict]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = STATE_FILE.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(segments, fh, ensure_ascii=False, separators=(",", ":"))
    tmp_path.replace(STATE_FILE)


def normalize_path(raw_path: str) -> str:
    path = urlparse(raw_path).path
    marker = "/api/v1/segments"
    idx = path.find(marker)
    if idx >= 0:
        return path[idx:]
    return path


def read_json_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def pagination_payload(items: list[dict], query: dict[str, list[str]]) -> dict:
    page = max(1, int(query.get("page", ["1"])[0] or "1"))
    page_size = int(
        query.get(
            "page_size",
            query.get("per_page", query.get("pageSize", query.get("limit", ["20"]))),
        )[0]
        or "20"
    )
    total = len(items)
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    start = (page - 1) * page_size
    end = start + page_size
    page_items = items[start:end] if page_size > 0 else items
    return {
        "segments": page_items,
        "page": page,
        "limit": page_size,
        "total": total,
        "meta": {
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
                "has_next_page": page < total_pages,
                "has_previous_page": page > 1,
            }
        },
    }


def default_segment(payload: dict | None = None) -> dict:
    payload = payload or {}
    now = now_iso()
    contacts_count = int(payload.get("contactsCount") or payload.get("computedCount") or 0)
    return {
        "name": payload.get("name") or "Novo Segmento",
        "description": payload.get("description") or "",
        "status": payload.get("status") or payload.get("active") or "draft",
        "contactsCount": contacts_count,
        "computedCount": int(payload.get("computedCount") or contacts_count),
        "lastComputedAt": payload.get("lastComputedAt") or None,
        "filters": payload.get("filters") or payload.get("conditions") or [],
        "createdAt": now,
        "updatedAt": now,
        "created_at": now,
        "updated_at": now,
        "contacts_count": contacts_count,
        "computed_count": int(payload.get("computedCount") or contacts_count),
        "last_computed_at": payload.get("lastComputedAt") or None,
    }


def persist_create(payload: dict) -> dict:
    segment = {
        "id": str(uuid.uuid4()),
        **default_segment(payload),
    }
    with LOCK:
        segments = load_state()
        segments.insert(0, segment)
        save_state(segments)
    return segment


def persist_update(segment_id: str, payload: dict) -> dict | None:
    with LOCK:
        segments = load_state()
        for index, current in enumerate(segments):
            if current.get("id") != segment_id:
                continue
            updated = deepcopy(current)
            updated.update(default_segment(payload))
            updated["id"] = segment_id
            updated["updatedAt"] = now_iso()
            segments[index] = updated
            save_state(segments)
            return updated
    return None


def find_segment(segment_id: str) -> dict | None:
    for segment in load_state():
        if segment.get("id") == segment_id:
            return segment
    return None


def delete_segment(segment_id: str) -> bool:
    with LOCK:
        segments = load_state()
        new_segments = [segment for segment in segments if segment.get("id") != segment_id]
        if len(new_segments) == len(segments):
            return False
        save_state(new_segments)
        return True


def recompute_segments() -> list[dict]:
    now = now_iso()
    with LOCK:
        segments = load_state()
        recomputed: list[dict] = []
        for current in segments:
            updated = deepcopy(current)
            updated["lastComputedAt"] = now
            updated["updatedAt"] = now
            updated["created_at"] = updated.get("created_at") or updated.get("createdAt") or now
            updated["updated_at"] = now
            updated["computedCount"] = int(updated.get("computedCount") or updated.get("contactsCount") or 0)
            updated["contactsCount"] = int(updated.get("contactsCount") or updated["computedCount"] or 0)
            updated["computed_count"] = updated["computedCount"]
            updated["contacts_count"] = updated["contactsCount"]
            updated["last_computed_at"] = now
            recomputed.append(updated)
        save_state(recomputed)
        return recomputed


class SegmentsHandler(BaseHTTPRequestHandler):
    server_version = "segments-mock/1.0"

    def log_message(self, fmt: str, *args) -> None:  # pragma: no cover
        return

    def _send(self, status: int, body: dict | list | str | bytes, content_type: str = "application/json") -> None:
        if isinstance(body, (dict, list)):
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            content_type = "application/json"
        elif isinstance(body, str):
            payload = body.encode("utf-8")
        else:
            payload = body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        path = normalize_path(self.path)
        query = parse_qs(urlparse(self.path).query)

        if path in {"/health", "/ready"}:
            self._send(HTTPStatus.OK, {"status": "healthy"})
            return

        if path == "/api/v1/segments":
            self._send(HTTPStatus.OK, pagination_payload(load_state(), query))
            return

        if path.startswith("/api/v1/segments/") and path.endswith("/contact-ids"):
            segment_id = path.split("/")[-2]
            segment = find_segment(segment_id)
            if segment is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": "Segment not found"})
            else:
                self._send(
                    HTTPStatus.OK,
                    {
                        "contactIds": [],
                        "segmentId": segment_id,
                        "total": 0,
                    },
                )
            return

        if path.startswith("/api/v1/segments/"):
            segment_id = path.rsplit("/", 1)[-1]
            segment = find_segment(segment_id)
            if segment is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": "Segment not found"})
            else:
                self._send(HTTPStatus.OK, segment)
            return

        self._send(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST(self) -> None:
        path = normalize_path(self.path)
        body = read_json_body(self)

        if path == "/api/v1/segments/recompute-all":
            recomputed = recompute_segments()
            self._send(
                HTTPStatus.OK,
                {
                    "results": [{"id": segment.get("id"), "success": True} for segment in recomputed],
                    "totalProcessingTimeMs": 1,
                    "segments": recomputed,
                    "total": len(recomputed),
                },
            )
            return

        if path == "/api/v1/segments":
            self._send(HTTPStatus.CREATED, persist_create(body))
            return

        if path.startswith("/api/v1/segments/") and path.endswith("/recompute"):
            segment_id = path.split("/")[-2]
            segment = find_segment(segment_id)
            if segment is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": "Segment not found"})
                return
            updated = deepcopy(segment)
            updated["lastComputedAt"] = now_iso()
            updated["updatedAt"] = now_iso()
            updated["last_computed_at"] = updated["lastComputedAt"]
            with LOCK:
                segments = load_state()
                for index, current in enumerate(segments):
                    if current.get("id") == segment_id:
                        segments[index] = updated
                        save_state(segments)
                        break
            self._send(
                HTTPStatus.OK,
                {
                    "success": True,
                    "segment": updated,
                    "results": [{"id": segment_id, "success": True}],
                    "totalProcessingTimeMs": 1,
                },
            )
            return

        self._send(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_PATCH(self) -> None:
        path = normalize_path(self.path)
        body = read_json_body(self)

        if path.startswith("/api/v1/segments/"):
            segment_id = path.rsplit("/", 1)[-1]
            segment = persist_update(segment_id, body)
            if segment is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": "Segment not found"})
            else:
                self._send(HTTPStatus.OK, segment)
            return

        self._send(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_PUT(self) -> None:
        self.do_PATCH()

    def do_DELETE(self) -> None:
        path = normalize_path(self.path)
        if path.startswith("/api/v1/segments/"):
            segment_id = path.rsplit("/", 1)[-1]
            if delete_segment(segment_id):
                self._send(HTTPStatus.NO_CONTENT, b"", content_type="text/plain")
            else:
                self._send(HTTPStatus.NOT_FOUND, {"error": "Segment not found"})
            return

        self._send(HTTPStatus.NOT_FOUND, {"error": "Not found"})


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), SegmentsHandler)
    print(f"segments-mock listening on 0.0.0.0:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
