# SPDX-License-Identifier: Apache-2.0
"""End-to-end tests of the HTTP surface: auth, CORS, envelopes, WS, shutdown."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from praelector import SCHEMA_VERSION, __version__
from praelector.api.v1.ws import WS_CLOSE_UNAUTHORIZED
from praelector.domain.enums import EventType
from praelector.security import WS_SUBPROTOCOL
from praelector.state import AppState

EVIL_ORIGIN = "http://evil.example"


def test_health_needs_a_token(client: TestClient) -> None:
    response = client.get("/v1/health")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth.missing_token"


def test_health_reports_an_idle_engine(client: TestClient, auth: dict[str, str]) -> None:
    body = client.get("/v1/health", headers=auth).json()
    assert body["status"] == "ok"
    assert body["project_open"] is False
    assert body["active_job_id"] is None
    assert body["uptime_s"] >= 0


def test_health_reflects_open_state(
    client: TestClient, auth: dict[str, str], app_state: AppState
) -> None:
    # A real open project, not a poked field: `current_project_id` delegates to
    # the store, so the health route cannot report a project the lock disagrees
    # with.
    project_id = app_state.projects.create(name="Health check").id
    app_state.projects.open(project_id)
    app_state.active_job_id = "job_test"
    try:
        body = client.get("/v1/health", headers=auth).json()
        assert body["project_open"] is True
        assert body["active_job_id"] == "job_test"
    finally:
        app_state.active_job_id = None
        app_state.projects.close_current()


def test_version_reports_the_contract(client: TestClient, auth: dict[str, str]) -> None:
    body = client.get("/v1/version", headers=auth).json()
    assert body["app"] == __version__
    assert body["engine"] == __version__
    assert body["schema"] == SCHEMA_VERSION
    assert body["platform"]["python"]
    assert set(body["platform"]) == {"os", "arch", "python", "frozen"}


def test_a_wrong_token_is_rejected(client: TestClient) -> None:
    response = client.get("/v1/version", headers={"Authorization": "Bearer nope"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth.invalid_token"


def test_a_foreign_origin_is_rejected_even_with_a_valid_token(
    client: TestClient, auth: dict[str, str]
) -> None:
    response = client.get("/v1/health", headers={**auth, "Origin": EVIL_ORIGIN})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "auth.origin_rejected"


def test_an_allow_listed_origin_is_accepted(client: TestClient, auth: dict[str, str]) -> None:
    for origin in ("tauri://localhost", "http://tauri.localhost", "http://localhost:1420"):
        response = client.get("/v1/health", headers={**auth, "Origin": origin})
        assert response.status_code == 200, origin


def test_cors_preflight_needs_no_token(client: TestClient) -> None:
    response = client.options(
        "/v1/health",
        headers={
            "Origin": "http://tauri.localhost",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://tauri.localhost"
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_a_foreign_origin_cannot_preflight(client: TestClient) -> None:
    response = client.options(
        "/v1/health",
        headers={"Origin": EVIL_ORIGIN, "Access-Control-Request-Method": "GET"},
    )
    assert response.headers.get("access-control-allow-origin") != EVIL_ORIGIN


def test_every_response_carries_a_trace_id(client: TestClient, auth: dict[str, str]) -> None:
    ok = client.get("/v1/health", headers=auth)
    denied = client.get("/v1/health")
    assert ok.headers["X-Trace-Id"]
    assert denied.headers["X-Trace-Id"]
    assert ok.headers["X-Trace-Id"] != denied.headers["X-Trace-Id"]


def test_an_incoming_trace_id_is_honoured(client: TestClient, auth: dict[str, str]) -> None:
    response = client.get("/v1/health", headers={**auth, "X-Trace-Id": "trace-from-shell"})
    assert response.headers["X-Trace-Id"] == "trace-from-shell"


def test_unknown_routes_use_the_envelope(client: TestClient, auth: dict[str, str]) -> None:
    response = client.get("/v1/nope", headers=auth)
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "internal.not_found"
    assert body["error"]["detail"]["path"] == "/v1/nope"
    assert body["error"]["trace_id"]


def test_the_openapi_document_is_behind_auth(client: TestClient, auth: dict[str, str]) -> None:
    assert client.get("/v1/openapi.json").status_code == 401
    document = client.get("/v1/openapi.json", headers=auth).json()
    assert "/v1/health" in document["paths"]


def test_interactive_docs_are_disabled(client: TestClient, auth: dict[str, str]) -> None:
    assert client.get("/docs", headers=auth).status_code == 404
    assert client.get("/v1/docs", headers=auth).status_code == 404


def test_shutdown_runs_hooks(client: TestClient, auth: dict[str, str], app_state: AppState) -> None:
    called: list[str] = []

    async def hook() -> None:
        called.append("hook")

    app_state.shutdown_hooks.append(hook)
    body = client.post("/v1/shutdown", headers=auth).json()
    assert body == {"accepted": True, "server_signalled": False}
    assert called == ["hook"]
    assert app_state.shutting_down is True
    assert client.get("/v1/health", headers=auth).json()["status"] == "shutting_down"


def test_ws_streams_published_events(client: TestClient, app_state: AppState, token: str) -> None:
    with client.websocket_connect(f"/v1/ws?token={token}", subprotocols=[WS_SUBPROTOCOL]) as ws:
        hello = ws.receive_json()
        assert hello["op"] == "hello"
        assert hello["v"] == SCHEMA_VERSION
        assert hello["seq"] == 0

        app_state.events.publish(EventType.GPU_SAMPLE, {"device_index": 0, "vram_used_mib": 1024})
        event = ws.receive_json()
        assert event["type"] == "gpu.sample"
        assert event["seq"] == 1
        assert event["payload"]["vram_used_mib"] == 1024


def test_ws_answers_ping_with_the_current_seq(
    client: TestClient, app_state: AppState, token: str
) -> None:
    with client.websocket_connect(f"/v1/ws?token={token}", subprotocols=[WS_SUBPROTOCOL]) as ws:
        ws.receive_json()
        app_state.events.publish(EventType.JOB_STATE, {"state": "running"}, job_id="job_a")
        ws.receive_json()
        ws.send_text(json.dumps({"op": "ping"}))
        assert ws.receive_json() == {"op": "pong", "seq": 1}


def test_ws_honours_a_topic_subscription(
    client: TestClient, app_state: AppState, token: str
) -> None:
    with client.websocket_connect(f"/v1/ws?token={token}", subprotocols=[WS_SUBPROTOCOL]) as ws:
        ws.receive_json()
        ws.send_text(json.dumps({"op": "subscribe", "topics": ["job.state"]}))
        # Subscribe is applied on the reader task. A pong is sent by that same
        # task after the topic list, so it is proof the filter is in place
        # before the publishes below.
        ws.send_text(json.dumps({"op": "ping"}))
        assert ws.receive_json()["op"] == "pong"
        app_state.events.publish(EventType.GPU_SAMPLE, {"device_index": 0})
        app_state.events.publish(EventType.JOB_STATE, {"state": "paused"}, job_id="job_a")
        event = ws.receive_json()
        assert event["type"] == "job.state"


def test_ws_ignores_a_malformed_control_frame(
    client: TestClient, app_state: AppState, token: str
) -> None:
    with client.websocket_connect(f"/v1/ws?token={token}", subprotocols=[WS_SUBPROTOCOL]) as ws:
        ws.receive_json()
        ws.send_text("{not json")
        app_state.events.publish(EventType.GPU_SAMPLE, {"device_index": 0})
        assert ws.receive_json()["type"] == "gpu.sample"


@pytest.mark.parametrize("query", ["", "?token=wrong"])
def test_ws_rejects_an_unauthenticated_handshake(client: TestClient, query: str) -> None:
    with (
        pytest.raises(WebSocketDisconnect) as excinfo,
        client.websocket_connect(f"/v1/ws{query}", subprotocols=[WS_SUBPROTOCOL]) as ws,
    ):
        ws.receive_json()
    assert excinfo.value.code == WS_CLOSE_UNAUTHORIZED


def test_ws_rejects_a_foreign_origin(client: TestClient, token: str) -> None:
    with (
        pytest.raises(WebSocketDisconnect) as excinfo,
        client.websocket_connect(
            f"/v1/ws?token={token}",
            subprotocols=[WS_SUBPROTOCOL],
            headers={"Origin": EVIL_ORIGIN},
        ) as ws,
    ):
        ws.receive_json()
    assert excinfo.value.code == WS_CLOSE_UNAUTHORIZED


def test_the_token_never_appears_in_a_serialised_response(
    client: TestClient, auth: dict[str, str], token: str
) -> None:
    for path in ("/v1/health", "/v1/version", "/v1/nope"):
        response = client.get(path, headers=auth)
        assert token not in response.text
