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
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen


STATE_FILE = Path(os.getenv("SEGMENTS_STATE_FILE", "/data/segments.json"))
PORT = int(os.getenv("PORT", "8091"))
API_BASE_URL = os.getenv("API_BASE_URL", "https://api.evo.librecode.coop/api/v1").rstrip("/")
LOCK = threading.Lock()
CONTACTS_PAGE_SIZE = int(os.getenv("SEGMENTS_CONTACTS_PAGE_SIZE", "200"))


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


def request_json(path: str, auth_header: str | None = None, params: dict[str, object] | None = None) -> dict | list:
    query = f"?{urlencode(params)}" if params else ""
    url = f"{API_BASE_URL}/{path.lstrip('/')}{query}"
    request = Request(url, headers={"Accept": "application/json"})
    if auth_header:
        request.add_header("Authorization", auth_header)
    with urlopen(request, timeout=15) as response:
        raw = response.read()
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return {}


def extract_items(payload: dict | list) -> list[dict]:
    if isinstance(payload, list):
        return payload if all(isinstance(item, dict) for item in payload) else []
    if not isinstance(payload, dict):
        return []
    for key in ("data", "contacts", "results", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def extract_contact_id(item: dict) -> str | None:
    for key in ("id", "contact_id", "contactId", "uuid"):
        value = item.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def fetch_all_contact_ids(auth_header: str | None) -> list[str]:
    if not auth_header:
        return []

    ids: list[str] = []
    seen: set[str] = set()

    try:
        payload = request_json("/contacts/all", auth_header=auth_header)
        for item in extract_items(payload):
            contact_id = extract_contact_id(item)
            if contact_id and contact_id not in seen:
                seen.add(contact_id)
                ids.append(contact_id)
        if ids:
            return ids
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        pass

    page = 1
    while True:
        try:
            payload = request_json(
                "/contacts",
                auth_header=auth_header,
                params={"page": page, "limit": CONTACTS_PAGE_SIZE},
            )
        except (HTTPError, URLError, TimeoutError, OSError, ValueError):
            break

        items = extract_items(payload)
        for item in items:
            contact_id = extract_contact_id(item)
            if contact_id and contact_id not in seen:
                seen.add(contact_id)
                ids.append(contact_id)

        pagination = {}
        if isinstance(payload, dict):
            pagination = (payload.get("meta") or {}).get("pagination") or {}
        total_pages = pagination.get("total_pages")
        if total_pages is not None:
            try:
                total_pages = int(total_pages)
            except (TypeError, ValueError):
                total_pages = None
        if total_pages is not None:
            if page >= total_pages:
                break
        elif len(items) < CONTACTS_PAGE_SIZE:
            break
        page += 1

    return ids


def is_everyone_segment(payload: dict) -> bool:
    definition = payload.get("definition")
    if not isinstance(definition, dict):
        return False
    entry_node = definition.get("entryNode")
    return isinstance(entry_node, dict) and entry_node.get("type") == "Everyone"


def apply_segment_computation(segment: dict, auth_header: str | None) -> dict:
    updated = deepcopy(segment)
    updated["updatedAt"] = now_iso()
    updated["updated_at"] = updated["updatedAt"]
    if is_everyone_segment(updated):
        contact_ids = fetch_all_contact_ids(auth_header)
        updated["contactIds"] = contact_ids
        updated["contactsCount"] = len(contact_ids)
        updated["computedCount"] = len(contact_ids)
        updated["contacts_count"] = len(contact_ids)
        updated["computed_count"] = len(contact_ids)
        updated["status"] = "running"
        updated["lastComputedAt"] = updated["updatedAt"]
        updated["last_computed_at"] = updated["updatedAt"]
    else:
        updated.setdefault("contactIds", [])
        updated.setdefault("contactsCount", int(updated.get("contactsCount") or 0))
        updated.setdefault("computedCount", int(updated.get("computedCount") or updated.get("contactsCount") or 0))
        updated.setdefault("contacts_count", int(updated.get("contactsCount") or 0))
        updated.setdefault("computed_count", int(updated.get("computedCount") or updated.get("contactsCount") or 0))
    return updated


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
        "definition": payload.get("definition") or {"entryNode": {"id": "entry", "type": "And"}},
        "contactsCount": contacts_count,
        "computedCount": int(payload.get("computedCount") or contacts_count),
        "lastComputedAt": payload.get("lastComputedAt") or None,
        "contactIds": payload.get("contactIds") or [],
        "filters": payload.get("filters") or payload.get("conditions") or [],
        "createdAt": now,
        "updatedAt": now,
        "created_at": now,
        "updated_at": now,
        "contacts_count": contacts_count,
        "computed_count": int(payload.get("computedCount") or contacts_count),
        "last_computed_at": payload.get("lastComputedAt") or None,
    }


def persist_create(payload: dict, auth_header: str | None = None) -> dict:
    segment = {
        "id": str(uuid.uuid4()),
        **default_segment(payload),
    }
    segment = apply_segment_computation(segment, auth_header)
    with LOCK:
        segments = load_state()
        segments.insert(0, segment)
        save_state(segments)
    return segment


def persist_update(segment_id: str, payload: dict, auth_header: str | None = None) -> dict | None:
    with LOCK:
        segments = load_state()
        for index, current in enumerate(segments):
            if current.get("id") != segment_id:
                continue
            updated = deepcopy(current)
            updated.update(default_segment(payload))
            updated["id"] = segment_id
            updated = apply_segment_computation(updated, auth_header)
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


def recompute_segments(auth_header: str | None) -> list[dict]:
    now = now_iso()
    with LOCK:
        segments = load_state()
        recomputed: list[dict] = []
        for current in segments:
            updated = apply_segment_computation(current, auth_header)
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
                if is_everyone_segment(segment) and not segment.get("contactIds"):
                    segment = apply_segment_computation(segment, self.headers.get("Authorization"))
                    with LOCK:
                        segments = load_state()
                        for index, current in enumerate(segments):
                            if current.get("id") == segment_id:
                                segments[index] = segment
                                save_state(segments)
                                break
                self._send(
                    HTTPStatus.OK,
                    {
                        "contactIds": segment.get("contactIds") or [],
                        "segmentId": segment_id,
                        "total": len(segment.get("contactIds") or []),
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
            recomputed = recompute_segments(self.headers.get("Authorization"))
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
            self._send(HTTPStatus.CREATED, persist_create(body, self.headers.get("Authorization")))
            return

        if path.startswith("/api/v1/segments/") and path.endswith("/recompute"):
            segment_id = path.split("/")[-2]
            segment = find_segment(segment_id)
            if segment is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": "Segment not found"})
                return
            updated = apply_segment_computation(segment, self.headers.get("Authorization"))
            updated["lastComputedAt"] = now_iso()
            updated["updatedAt"] = updated["lastComputedAt"]
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
            segment = persist_update(segment_id, body, self.headers.get("Authorization"))
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
