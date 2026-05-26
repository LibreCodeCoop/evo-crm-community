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


STATE_FILE = Path(os.getenv("JOURNEYS_STATE_FILE", "/data/journeys.json"))
PORT = int(os.getenv("PORT", "8090"))
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

    if isinstance(data, list):
        return data
    return []


def save_state(journeys: list[dict]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = STATE_FILE.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(journeys, fh, ensure_ascii=False, separators=(",", ":"))
    tmp_path.replace(STATE_FILE)


def normalize_path(raw_path: str) -> str:
    path = urlparse(raw_path).path
    if path.startswith("/undefined/api"):
        return path[len("/undefined") :]
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
    if isinstance(decoded, dict):
        return decoded
    return {}


def pagination_payload(items: list[dict], query: dict[str, list[str]]) -> dict:
    page = max(1, int(query.get("page", ["1"])[0] or "1"))
    page_size = int(query.get("page_size", query.get("per_page", query.get("pageSize", ["20"])))[0] or "20")
    total = len(items)
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    start = (page - 1) * page_size
    end = start + page_size
    page_items = items[start:end] if page_size > 0 else items
    return {
        "data": page_items,
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


def journey_defaults(payload: dict | None = None) -> dict:
    payload = payload or {}
    return {
        "name": payload.get("name") or "Nova Jornada",
        "description": payload.get("description") or "",
        "isActive": bool(payload.get("isActive", True)),
        "flowData": payload.get("flowData"),
        "flowTriggers": payload.get("flowTriggers") or [],
    }


def persist_create(payload: dict) -> dict:
    journey = {
        "id": str(uuid.uuid4()),
        **journey_defaults(payload),
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    }
    with LOCK:
        journeys = load_state()
        journeys.insert(0, journey)
        save_state(journeys)
    return journey


def persist_update(journey_id: str, payload: dict) -> dict | None:
    with LOCK:
        journeys = load_state()
        for index, current in enumerate(journeys):
            if current.get("id") != journey_id:
                continue
            updated = deepcopy(current)
            updated.update(journey_defaults(payload))
            updated["id"] = journey_id
            updated["updatedAt"] = now_iso()
            journeys[index] = updated
            save_state(journeys)
            return updated
    return None


def find_journey(journey_id: str) -> dict | None:
    journeys = load_state()
    for journey in journeys:
        if journey.get("id") == journey_id:
            return journey
    return None


def delete_journey(journey_id: str) -> bool:
    with LOCK:
        journeys = load_state()
        new_journeys = [journey for journey in journeys if journey.get("id") != journey_id]
        if len(new_journeys) == len(journeys):
            return False
        save_state(new_journeys)
        return True


def duplicate_journey(journey_id: str) -> dict | None:
    with LOCK:
        journeys = load_state()
        for current in journeys:
            if current.get("id") != journey_id:
                continue
            duplicated = deepcopy(current)
            duplicated["id"] = str(uuid.uuid4())
            duplicated["name"] = f"{current.get('name', 'Nova Jornada')} (Copy)"
            duplicated["createdAt"] = now_iso()
            duplicated["updatedAt"] = now_iso()
            journeys.insert(0, duplicated)
            save_state(journeys)
            return duplicated
    return None


def toggle_journey(journey_id: str) -> dict | None:
    with LOCK:
        journeys = load_state()
        for index, current in enumerate(journeys):
            if current.get("id") != journey_id:
                continue
            updated = deepcopy(current)
            updated["isActive"] = not bool(updated.get("isActive", True))
            updated["updatedAt"] = now_iso()
            journeys[index] = updated
            save_state(journeys)
            return updated
    return None


class JourneysHandler(BaseHTTPRequestHandler):
    server_version = "journeys-mock/1.0"

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

        if path == "/api/v1/journeys":
            journeys = load_state()
            self._send(HTTPStatus.OK, pagination_payload(journeys, query))
            return

        if path.startswith("/api/v1/journeys/trigger-type/"):
            trigger_type = path.rsplit("/", 1)[-1]
            journeys = [
                journey
                for journey in load_state()
                if trigger_type in {
                    str(trigger.get("type") or trigger.get("trigger_type") or trigger.get("name"))
                    for trigger in (journey.get("flowTriggers") or [])
                }
            ]
            self._send(HTTPStatus.OK, {"data": journeys})
            return

        if path.startswith("/api/v1/journeys/"):
            journey_id = path.rsplit("/", 1)[-1]
            journey = find_journey(journey_id)
            if journey is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": "Journey not found"})
            else:
                self._send(HTTPStatus.OK, journey)
            return

        self._send(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST(self) -> None:
        path = normalize_path(self.path)
        body = read_json_body(self)

        if path == "/api/v1/journeys":
            journey = persist_create(body)
            self._send(HTTPStatus.CREATED, journey)
            return

        if path.startswith("/api/v1/journeys/") and path.endswith("/toggle-active"):
            journey_id = path.split("/")[4]
            journey = toggle_journey(journey_id)
            if journey is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": "Journey not found"})
            else:
                self._send(HTTPStatus.OK, journey)
            return

        if path.startswith("/api/v1/journeys/") and path.endswith("/duplicate"):
            journey_id = path.split("/")[4]
            journey = duplicate_journey(journey_id)
            if journey is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": "Journey not found"})
            else:
                self._send(HTTPStatus.CREATED, journey)
            return

        if path.startswith("/api/v1/journeys/") and path.endswith("/variables"):
            journey_id = path.split("/")[4]
            journey = find_journey(journey_id)
            if journey is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": "Journey not found"})
            else:
                with LOCK:
                    journeys = load_state()
                    for index, current in enumerate(journeys):
                        if current.get("id") == journey_id:
                            updated = deepcopy(current)
                            updated["variables"] = body if isinstance(body, (list, dict)) else []
                            updated["updatedAt"] = now_iso()
                            journeys[index] = updated
                            save_state(journeys)
                            self._send(HTTPStatus.OK, {"data": updated.get("variables", [])})
                            return
                self._send(HTTPStatus.NOT_FOUND, {"error": "Journey not found"})
            return

        self._send(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_PATCH(self) -> None:
        path = normalize_path(self.path)
        body = read_json_body(self)

        if path.startswith("/api/v1/journeys/"):
            journey_id = path.rsplit("/", 1)[-1]
            journey = persist_update(journey_id, body)
            if journey is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": "Journey not found"})
            else:
                self._send(HTTPStatus.OK, journey)
            return

        self._send(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_PUT(self) -> None:
        self.do_PATCH()

    def do_DELETE(self) -> None:
        path = normalize_path(self.path)
        if path.startswith("/api/v1/journeys/"):
            journey_id = path.rsplit("/", 1)[-1]
            if delete_journey(journey_id):
                self._send(HTTPStatus.NO_CONTENT, b"", content_type="text/plain")
            else:
                self._send(HTTPStatus.NOT_FOUND, {"error": "Journey not found"})
            return

        self._send(HTTPStatus.NOT_FOUND, {"error": "Not found"})


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), JourneysHandler)
    print(f"journeys-mock listening on 0.0.0.0:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
