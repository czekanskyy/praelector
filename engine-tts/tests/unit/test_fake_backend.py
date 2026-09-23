# SPDX-License-Identifier: Apache-2.0
"""Tests for the deterministic stand-in backend (PLAN.md §10.3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from praelector_tts.audio import read_wav
from praelector_tts.backends import create_backend, describe
from praelector_tts.backends.fake import CHARS_PER_AUDIO_SECOND, SAMPLE_RATE, FakeBackend
from praelector_tts.protocol import (
    LoadContext,
    SynthesisRequest,
    TtsError,
    TtsErrorCode,
)


@pytest.fixture
def backend() -> FakeBackend:
    loaded = FakeBackend()
    loaded.load(LoadContext(models_dir="/tmp/models"))
    return loaded


def _request(text: str, out_path: Path, **params: object) -> SynthesisRequest:
    return SynthesisRequest(text=text, out_path=str(out_path), params=dict(params))


def test_descriptor_declares_the_contract() -> None:
    descriptor = describe("fake")
    assert descriptor.id == "fake"
    assert descriptor.adapter_version == FakeBackend.adapter_version
    assert "pl" in descriptor.capabilities.languages
    assert descriptor.capabilities.max_input_chars == 400
    assert descriptor.capabilities.native_sample_rate == SAMPLE_RATE
    assert descriptor.capabilities.deterministic_with_seed is True
    assert descriptor.capabilities.watermark is False


def test_every_license_entry_has_an_spdx_id() -> None:
    """The gate NF-03 depends on: no descriptor may ship without license data."""
    descriptor = describe("fake")
    assert descriptor.licenses, "a backend without license data cannot be shipped"
    for entry in descriptor.licenses:
        assert entry.spdx
        assert entry.component


def test_params_schema_carries_ui_hints() -> None:
    """TTS-05: the Voices screen renders this with no backend-specific code."""
    schema = describe("fake").params_schema
    assert schema["type"] == "object"
    for name, prop in schema["properties"].items():
        assert "x-prl-ui" in prop, name
        assert "widget" in prop["x-prl-ui"]


def test_vram_profile_is_present_for_every_precision() -> None:
    profile = describe("fake").vram_profile
    assert profile["fp16"].peak_mib > 0
    assert profile["fp16"].measured is True


def test_duration_follows_the_characters_per_second_rule(
    backend: FakeBackend, tmp_path: Path
) -> None:
    text = "Nie zdążymy." * 10
    result = backend.synthesize(_request(text, tmp_path / "a.wav"))
    assert result.duration_s == pytest.approx(len(text) / CHARS_PER_AUDIO_SECOND, abs=1e-4)
    assert result.sample_rate == SAMPLE_RATE


def test_the_written_file_matches_the_reported_duration(
    backend: FakeBackend, tmp_path: Path
) -> None:
    result = backend.synthesize(_request("Ala ma kota.", tmp_path / "a.wav"))
    samples, rate = read_wav(Path(result.out_path))
    assert rate == result.sample_rate
    assert len(samples) / rate == pytest.approx(result.duration_s, abs=1e-3)


def test_output_lands_in_the_part_file(backend: FakeBackend, tmp_path: Path) -> None:
    result = backend.synthesize(_request("Ala ma kota.", tmp_path / "rk.wav"))
    assert result.out_path.endswith(".part")
    assert not (tmp_path / "rk.wav").exists()


def test_the_same_text_produces_identical_audio(backend: FakeBackend, tmp_path: Path) -> None:
    text = "Walker wzruszył ramionami."
    first = backend.synthesize(_request(text, tmp_path / "a.wav"))
    second = backend.synthesize(_request(text, tmp_path / "b.wav"))
    assert Path(first.out_path).read_bytes() == Path(second.out_path).read_bytes()


def test_different_text_produces_different_audio(backend: FakeBackend, tmp_path: Path) -> None:
    first = backend.synthesize(_request("Ala ma kota.", tmp_path / "a.wav"))
    second = backend.synthesize(_request("Ala ma psa.", tmp_path / "b.wav"))
    assert Path(first.out_path).read_bytes() != Path(second.out_path).read_bytes()


def test_speed_scales_duration(backend: FakeBackend, tmp_path: Path) -> None:
    text = "Deadline mamy o osiemnastej."
    normal = backend.synthesize(_request(text, tmp_path / "a.wav"))
    double = backend.synthesize(_request(text, tmp_path / "b.wav", speed=2.0))
    assert double.duration_s == pytest.approx(normal.duration_s / 2, abs=1e-3)


def test_out_of_range_params_are_clamped(backend: FakeBackend, tmp_path: Path) -> None:
    result = backend.synthesize(_request("Ala ma kota.", tmp_path / "a.wav", speed=99.0))
    assert result.duration_s == pytest.approx(
        len("Ala ma kota.") / CHARS_PER_AUDIO_SECOND / 2.0, abs=1e-3
    )


def test_a_garbage_param_falls_back_to_its_default(backend: FakeBackend, tmp_path: Path) -> None:
    result = backend.synthesize(_request("Ala ma kota.", tmp_path / "a.wav", speed="fast"))
    assert result.duration_s == pytest.approx(
        len("Ala ma kota.") / CHARS_PER_AUDIO_SECOND, abs=1e-3
    )


def test_an_unsupported_language_is_refused(backend: FakeBackend, tmp_path: Path) -> None:
    request = SynthesisRequest(text="Hello there.", language="de", out_path=str(tmp_path / "a.wav"))
    with pytest.raises(TtsError) as excinfo:
        backend.synthesize(request)
    assert excinfo.value.code is TtsErrorCode.LANGUAGE_UNSUPPORTED
    assert excinfo.value.detail["language"] == "de"
    assert not (tmp_path / "a.wav.part").exists()


def test_overlong_input_is_refused(backend: FakeBackend, tmp_path: Path) -> None:
    request = SynthesisRequest(text="x" * 401, out_path=str(tmp_path / "a.wav"))
    with pytest.raises(TtsError) as excinfo:
        backend.synthesize(request)
    assert excinfo.value.code is TtsErrorCode.INPUT_TOO_LONG
    assert excinfo.value.detail == {"chars": 401, "limit": 400}


def test_synthesizing_before_load_fails(tmp_path: Path) -> None:
    with pytest.raises(TtsError) as excinfo:
        FakeBackend().synthesize(_request("Ala ma kota.", tmp_path / "a.wav"))
    assert excinfo.value.code is TtsErrorCode.LOAD_FAILED


def test_load_reports_the_device_and_precision() -> None:
    report = FakeBackend().load(LoadContext(device="cuda:0", precision="fp16", models_dir="/m"))
    assert report.loaded is True
    assert report.device == "cuda:0"
    assert report.precision == "fp16"
    assert report.model_revision == FakeBackend.adapter_version


def test_unload_clears_the_loaded_flag(tmp_path: Path) -> None:
    backend = FakeBackend()
    backend.load(LoadContext(models_dir="/m"))
    backend.unload()
    with pytest.raises(TtsError) as excinfo:
        backend.synthesize(_request("Ala ma kota.", tmp_path / "a.wav"))
    assert excinfo.value.code is TtsErrorCode.LOAD_FAILED


def test_probe_vram_reports_the_table_value_without_torch(backend: FakeBackend) -> None:
    report = backend.probe_vram()
    assert report.peak_mib is not None
    assert report.peak_mib > 0


def test_the_registry_creates_the_fake_backend() -> None:
    assert isinstance(create_backend("fake"), FakeBackend)
