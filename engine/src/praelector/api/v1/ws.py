# SPDX-License-Identifier: Apache-2.0
"""The WebSocket hub: one connection per app, server → client events.

Traffic is almost entirely one-way. The client may send exactly two control
messages (OPENAPI_SKETCH.md §11):

* ``{"op": "subscribe", "topics": [...]}`` — narrow the stream; an empty list
  means "everything".
* ``{"op": "ping"}`` — answered with ``{"op": "pong", "seq": <last_seq>}``.

Control frames are distinguished from event envelopes by carrying ``op`` instead
of ``type``. On connect the server sends ``{"op": "hello", "v", "seq"}`` so the
client knows the sequence number to resume from, and ``{"op": "overflow", ...}``
if it fell behind and events were dropped — the client then calls
``GET /v1/jobs/{id}/events?since=<seq>`` to gap-fill (PLAN.md §8.1).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError

from praelector import SCHEMA_VERSION
from praelector.events import Subscription
from praelector.security import WS_SUBPROTOCOL, authorize_websocket
from praelector.state import AppState, get_state

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ws"])

#: 4001-4999 are application-defined close codes; 4401 reads as "unauthorized".
WS_CLOSE_UNAUTHORIZED = 4401


class ClientOp(BaseModel):
    op: Literal["subscribe", "ping"]
    topics: list[str] | None = None


async def _send(websocket: WebSocket, payload: dict[str, Any]) -> None:
    await websocket.send_text(json.dumps(payload, ensure_ascii=False, default=str))


async def _pump_events(websocket: WebSocket, state: AppState, sub: Subscription) -> None:
    while True:
        event = await sub.queue.get()
        if sub.dropped:
            await _send(
                websocket,
                {"op": "overflow", "dropped": sub.dropped, "seq": state.events.last_seq},
            )
            sub.dropped = 0
        await _send(websocket, event.to_wire())


async def _read_ops(websocket: WebSocket, state: AppState, sub: Subscription) -> None:
    while True:
        raw = await websocket.receive_text()
        try:
            op = ClientOp.model_validate_json(raw)
        except ValidationError:
            # A malformed control frame is a client bug, not a reason to drop the
            # stream; the next event will show whether the client is broken.
            logger.debug("ignored malformed ws control frame")
            continue
        if op.op == "ping":
            await _send(websocket, {"op": "pong", "seq": state.events.last_seq})
        else:
            state.events.set_topics(sub, op.topics or [])


@router.websocket("/ws")
async def event_stream(websocket: WebSocket, state: AppState = Depends(get_state)) -> None:
    rejection = authorize_websocket(websocket, state.policy)
    if rejection is not None:
        logger.warning("ws handshake rejected", extra={"error_code": str(rejection.code)})
        await websocket.close(code=WS_CLOSE_UNAUTHORIZED, reason=str(rejection.code))
        return

    await websocket.accept(subprotocol=WS_SUBPROTOCOL)
    sub = state.events.subscribe()
    pump = asyncio.create_task(_pump_events(websocket, state, sub))
    reader = asyncio.create_task(_read_ops(websocket, state, sub))
    try:
        # A client that vanishes between accept() and the first frame is normal.
        with contextlib.suppress(WebSocketDisconnect, RuntimeError):
            await _send(
                websocket, {"op": "hello", "v": SCHEMA_VERSION, "seq": state.events.last_seq}
            )
        await asyncio.wait({pump, reader}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in (pump, reader):
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
            await asyncio.gather(pump, reader)
        state.events.unsubscribe(sub)
        logger.debug("ws connection closed", extra={"last_seq": state.events.last_seq})
