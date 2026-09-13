# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the fake TTS backend and worker."""

from __future__ import annotations

import wave
from pathlib import Path

from praelector_tts.backends.fake import FakeBackend
from praelector_tts.worker import TtsWorker


def test_fake_backend_duration_and_wav(tmp_path: Path) -> None:
    backend = FakeBackend(sample_rate=24000)
    output_wav = tmp_path / "test_chunk.wav"

    text = "To jest testowy tekst dla syntezatora mowy."  # 43 chars
    duration_s, sr = backend.synthesize(text=text, output_path=str(output_wav))

    assert output_wav.exists()
    assert sr == 24000
    expected_duration = round(len(text.strip()) / 14.0, 3)
    assert round(duration_s, 3) == expected_duration

    # Verify WAV header
    with wave.open(str(output_wav), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 24000
        frames = wav.getnframes()
        actual_duration = frames / 24000.0
        assert abs(actual_duration - duration_s) < 0.05


def test_worker_dispatch_synthesize(tmp_path: Path) -> None:
    worker = TtsWorker()
    output_wav = tmp_path / "worker_chunk.wav"

    req = {
        "id": "req_001",
        "action": "synthesize",
        "backend_id": "fake",
        "text": "Krótka wypowiedź.",
        "output_path": str(output_wav),
        "params": {},
    }

    resp = worker.handle_request(req)
    assert resp.ok is True
    assert resp.id == "req_001"
    assert output_wav.exists()


def test_worker_probe() -> None:
    worker = TtsWorker()
    resp = worker.handle_request({"id": "req_probe", "action": "probe"})
    assert resp.ok is True
    data = resp.model_dump()
    assert "fake" in data["backends"]
