# SPDX-License-Identifier: Apache-2.0
"""Detection tests that need no GPU and spawn no process.

CI has no GPU — that is exactly why ``pytest -m "not gpu"`` exists — so every
test here drives the pure parsers with canned text and the probes through a fake
``run_probe_command``. The single test that touches real hardware lives in
``tests/integration/test_gpu_api.py`` and is marked ``gpu``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

import pytest
from pydantic import ValidationError

from praelector.domain.enums import GpuVendor
from praelector.gpu import detect
from praelector.gpu.detect import CommandResult, GpuDeviceInfo

NVIDIA_QUERY = (
    "nvidia-smi",
    "--query-gpu=index,name,memory.total,memory.free,driver_version",
    "--format=csv,noheader,nounits",
)

NVIDIA_ONE = "0, NVIDIA GeForce RTX 4070 Ti, 12287, 11234, 580.65.06\n"
NVIDIA_TWO = (
    "0, NVIDIA GeForce RTX 4070 Ti, 12287, 11234, 580.65.06\n"
    "1, NVIDIA GeForce RTX 3060, 12288, 12100, 580.65.06\n"
)
NVIDIA_HEADER = "index, name, memory.total [MiB], memory.free [MiB], driver_version\n" + NVIDIA_ONE

#: 16 GiB and 8 GiB cards, in the byte figures the kernel actually reports.
VRAM_16GIB = 17163091968
VRAM_8GIB = 8573157376
USED_256MIB = 268435456

#: ROCm 6.x ``amd-smi metric --mem --json``: percentages next to byte figures,
#: every number a string, VRAM nested under ``Vram``.
AMD_SMI_DICT = json.dumps(
    {
        "card0": {
            "DeviceID": "0x7480",
            "UniqueID": "0x5c88002f2fe16280",
            "Vram": {
                "% used": "1",
                "% free": "99",
                "total memory (B)": str(VRAM_16GIB),
                "used memory (B)": str(USED_256MIB),
                "free memory (B)": str(VRAM_16GIB - USED_256MIB),
            },
            "Vram Type": "VRAM_TYPE_HBM3",
        }
    }
)

#: A newer ``amd-smi``: a list of records with snake_case byte integers.
AMD_SMI_LIST = json.dumps(
    [
        {"card": "card0", "vram_total": VRAM_16GIB, "vram_used": USED_256MIB},
        {"card": "card1", "vram_total": VRAM_8GIB, "vram_used": 1048576},
    ]
)

#: ``rocm-smi --showmeminfo vram --json``: keyed by card, with a ``system``
#: block that is not a device, and no free figure at all.
ROCM_SMI = json.dumps(
    {
        "system": {"Driver version": "6.2.4", "PID": "1834"},
        "card0": {
            "VRAM Total Memory (B)": str(VRAM_16GIB),
            "VRAM Total Used Memory (B)": str(USED_256MIB),
        },
    }
)


class FakeClock:
    """A monotonic clock the test advances by hand — never ``time.sleep``."""

    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeProbe:
    """Callable stand-in for :func:`detect.run_probe_command`."""

    def __init__(self, results: Mapping[str, CommandResult]) -> None:
        self._results = dict(results)
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, argv: Sequence[str]) -> CommandResult:
        self.calls.append(tuple(argv))
        # An unlisted binary behaves like one that is not on PATH, which is the
        # state of every vendor stack on a CI runner.
        return self._results.get(argv[0], CommandResult(outcome=detect.OUTCOME_MISSING))

    def count(self, binary: str) -> int:
        return sum(1 for call in self.calls if call[0] == binary)


@pytest.fixture(autouse=True)
def _no_cache_leak() -> Iterator[None]:
    """The 5 s cache is process-wide; no test may inherit another's machine."""
    detect.invalidate_cache()
    yield
    detect.invalidate_cache()


@pytest.fixture
def fake_probe(monkeypatch: pytest.MonkeyPatch) -> object:
    """Install the fake subprocess wrapper; returns a factory."""

    def install(results: Mapping[str, CommandResult] | None = None) -> FakeProbe:
        fake = FakeProbe(results or {})
        monkeypatch.setattr(detect, "run_probe_command", fake)
        return fake

    return install


@pytest.fixture
def empty_sysfs(tmp_path: Path) -> Path:
    """A sysfs root with no DRM cards, so the AMD fallback finds nothing."""
    root = tmp_path / "sysfs"
    root.mkdir()
    return root


def write_sysfs_card(
    root: Path, card: str, *, total: int | None, used: int | None, driver: str | None = "amdgpu"
) -> Path:
    device = root / "class" / "drm" / card / "device"
    device.mkdir(parents=True)
    if total is not None:
        (device / "mem_info_vram_total").write_text(f"{total}\n", encoding="utf-8")
    if used is not None:
        (device / "mem_info_vram_used").write_text(f"{used}\n", encoding="utf-8")
    if driver is not None:
        (device / "uevent").write_text(f"DRIVER={driver}\nPCI_ID=1002:7480\n", encoding="utf-8")
    return device


def report_with(probe: FakeProbe, sysfs_root: Path) -> detect.GpuProbeReport:
    del probe  # the fake is already installed; it only records calls
    return detect.probe_report(use_cache=False, sysfs_root=sysfs_root)


def vendor_of(report: detect.GpuProbeReport, vendor: GpuVendor) -> detect.GpuVendorAvailability:
    return next(entry for entry in report.vendors if entry.vendor is vendor)


# --- nvidia-smi parsing -----------------------------------------------------


def test_a_single_nvidia_device_parses() -> None:
    (device,) = detect.parse_nvidia_smi(NVIDIA_ONE)
    assert device == GpuDeviceInfo(
        index=0,
        vendor=GpuVendor.NVIDIA,
        name="NVIDIA GeForce RTX 4070 Ti",
        driver="580.65.06",
        memory_total_mib=12287,
        memory_free_mib=11234,
        available=True,
        reason=None,
    )


def test_two_nvidia_devices_keep_their_ordinals() -> None:
    devices = detect.parse_nvidia_smi(NVIDIA_TWO)
    assert [device.index for device in devices] == [0, 1]
    assert [device.name for device in devices] == [
        "NVIDIA GeForce RTX 4070 Ti",
        "NVIDIA GeForce RTX 3060",
    ]


def test_windows_line_endings_parse() -> None:
    stdout = NVIDIA_TWO.replace("\n", "\r\n")
    devices = detect.parse_nvidia_smi(stdout)
    assert len(devices) == 2
    assert devices[0].driver == "580.65.06"
    assert devices[1].memory_free_mib == 12100


def test_a_device_name_containing_a_comma_survives() -> None:
    # Real output: the marketing name carries a comma, so the line cannot be
    # split positionally from the left.
    stdout = "0, NVIDIA GeForce RTX 4070 Ti, 12GB, 12287, 11234, 580.65.06\n"
    (device,) = detect.parse_nvidia_smi(stdout)
    assert device.name == "NVIDIA GeForce RTX 4070 Ti, 12GB"
    assert device.memory_total_mib == 12287
    assert device.memory_free_mib == 11234
    assert device.driver == "580.65.06"


def test_free_above_total_is_reported_verbatim() -> None:
    """A driver claiming more free than total VRAM is broken, not unheard of.

    The decision (documented on ``GpuDeviceInfo``) is to pass the figure through
    untouched: clamping here would hide a driver bug from the bug report GPU-06
    exists to support, and PLAN.md §7.2's budget math is what has to cope.
    """
    stdout = "0, NVIDIA GeForce RTX 4070 Ti, 12287, 13000, 580.65.06\n"
    (device,) = detect.parse_nvidia_smi(stdout)
    assert device.memory_total_mib == 12287
    assert device.memory_free_mib == 13000
    assert device.memory_free_mib > device.memory_total_mib
    assert device.available is True


def test_an_unsuppressed_header_is_not_a_device() -> None:
    devices = detect.parse_nvidia_smi(NVIDIA_HEADER)
    assert [device.index for device in devices] == [0]


@pytest.mark.parametrize(
    "stdout",
    [
        "0, NVIDIA GeForce RTX 4070 Ti\n",  # truncated: name only
        "0, NVIDIA GeForce RTX 4070 Ti, 12287\n",  # truncated: no free, no driver
        "0, NVIDIA GeForce RTX 4070 Ti, 12287, 11234\n",  # one field short
        ",\n",
        ",,,,,\n",
    ],
)
def test_a_truncated_line_is_dropped_rather_than_guessed(stdout: str) -> None:
    assert detect.parse_nvidia_smi(stdout) == []


@pytest.mark.parametrize("stdout", ["", "   ", "\n", "\r\n", "\n\n  \n\t\n"])
def test_empty_stdout_yields_no_devices(stdout: str) -> None:
    assert detect.parse_nvidia_smi(stdout) == []


@pytest.mark.parametrize(
    ("stdout", "expected_total", "expected_free"),
    [
        ("0, NVIDIA GeForce RTX 4070 Ti, [N/A], [N/A], 580.65.06\n", None, None),
        ("0, NVIDIA GeForce RTX 4070 Ti, [Not Supported], 11234, 580.65.06\n", None, 11234),
        ("0, NVIDIA GeForce RTX 4070 Ti, 12287, [Insufficient Permissions], [N/A]\n", 12287, None),
    ],
)
def test_smi_placeholders_never_become_numbers(
    stdout: str, expected_total: int | None, expected_free: int | None
) -> None:
    (device,) = detect.parse_nvidia_smi(stdout)
    assert device.memory_total_mib == expected_total
    assert device.memory_free_mib == expected_free
    # A card whose total VRAM cannot be read cannot be budgeted (PLAN.md §7.2),
    # but it is still a real device and must still be listed.
    assert device.available is (expected_total is not None)
    assert device.reason == (None if expected_total is not None else "memory_unreadable")


def test_a_placeholder_name_and_driver_do_not_invent_values() -> None:
    (device,) = detect.parse_nvidia_smi("0, [N/A], 12287, 11234, [Not Supported]\n")
    assert device.name == "unknown"
    assert device.driver is None
    assert device.memory_total_mib == 12287


@pytest.mark.parametrize(
    "stdout",
    [
        "\x00\x01binary garbage\xff",
        "not csv at all",
        # An explicit id: pytest exports the node id as PYTEST_CURRENT_TEST, and
        # Windows caps an environment variable at 32767 characters, so a 100k-char
        # parameter errors during setup instead of running.
        pytest.param("0, " + "x" * 100_000 + ", 12287, 11234, 580.65.06", id="huge-name-field"),
        "0, 1, 2, 3, 4, 5, 6, 7",  # far too many fields
        "-1, impostor, 12287, 11234, 580.65.06",  # -1 belongs to the CPU device
        "999999999999999999999, absurd, 1, 2, 3",
        "0, café ünïcode, 12287, 11234, 580.65.06",
        "0, card, NaN, inf, 580.65.06",
    ],
)
def test_hostile_nvidia_output_never_raises(stdout: str) -> None:
    devices = detect.parse_nvidia_smi(stdout)
    assert all(isinstance(device, GpuDeviceInfo) for device in devices)
    assert all(device.index >= 0 for device in devices)


# --- amd-smi / rocm-smi parsing --------------------------------------------


def test_amd_smi_dict_keyed_by_card() -> None:
    (device,) = detect.parse_amd_smi(AMD_SMI_DICT)
    assert device.vendor is GpuVendor.AMD
    assert device.index == 0
    assert device.name == "card0"
    assert device.memory_total_mib == 16368
    assert device.memory_free_mib == 16112
    assert device.available is True


def test_amd_smi_percentages_are_not_mistaken_for_megabytes() -> None:
    # ``"% free": "99"`` sits next to ``"free memory (B)"`` in the same object.
    (device,) = detect.parse_amd_smi(AMD_SMI_DICT)
    assert device.memory_free_mib != 99
    assert device.memory_free_mib == (VRAM_16GIB - USED_256MIB) // (1024 * 1024)


def test_amd_smi_list_of_records() -> None:
    devices = detect.parse_amd_smi(AMD_SMI_LIST)
    assert [device.index for device in devices] == [0, 1]
    assert [device.name for device in devices] == ["card0", "card1"]
    assert [device.memory_total_mib for device in devices] == [16368, 8176]
    # No free figure in this shape: it is derived from total - used.
    assert [device.memory_free_mib for device in devices] == [16368 - 256, 8176 - 1]


def test_rocm_smi_skips_its_system_block() -> None:
    devices = detect.parse_amd_smi(ROCM_SMI)
    assert len(devices) == 1
    # ``system`` comes first in the payload; ordinals are assigned after it is
    # filtered, so the real card is still index 0.
    assert devices[0].index == 0
    assert devices[0].name == "card0"
    assert devices[0].memory_total_mib == 16368
    assert devices[0].memory_free_mib == 16368 - 256


def test_a_bare_record_is_accepted() -> None:
    (device,) = detect.parse_amd_smi(json.dumps({"vram_total": VRAM_16GIB, "vram_used": 0}))
    assert device.memory_total_mib == 16368
    assert device.memory_free_mib == 16368
    assert device.name == "card0"


def test_a_record_keyed_by_pci_path_is_named_after_the_address() -> None:
    payload = json.dumps(
        {"/sys/devices/pci0000:00/0000:00:03.1/0000:03:00.0": {"vram_total": 1024}}
    )
    (device,) = detect.parse_amd_smi(payload)
    assert device.name == "0000:03:00.0"


def test_a_sku_wins_over_the_card_id_as_the_name() -> None:
    payload = json.dumps({"card1": {"SKU": "AMD Radeon RX 9060 XT", "vram_total": VRAM_16GIB}})
    (device,) = detect.parse_amd_smi(payload)
    assert device.name == "AMD Radeon RX 9060 XT"


def test_a_driver_version_is_picked_up_when_present() -> None:
    payload = json.dumps({"card0": {"Driver version": "6.2.4", "vram_total": VRAM_16GIB}})
    (device,) = detect.parse_amd_smi(payload)
    assert device.driver == "6.2.4"


def test_mib_suffixed_keys_are_not_rescaled() -> None:
    payload = json.dumps({"card0": {"vram_total_mib": 16368, "vram_used_mib": 256}})
    (device,) = detect.parse_amd_smi(payload)
    assert device.memory_total_mib == 16368
    assert device.memory_free_mib == 16112


def test_numeric_strings_are_accepted() -> None:
    payload = json.dumps({"card0": {"vram_total": str(VRAM_16GIB), "vram_used": "268435456"}})
    (device,) = detect.parse_amd_smi(payload)
    assert device.memory_total_mib == 16368
    assert device.memory_free_mib == 16112


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "   ",
        "{not json",
        '{"card0": ',
        "[",
        '"card0"',  # a bare string
        "12345",
        "null",
        "true",
        "[]",
        "{}",
        '{"system": {"Driver version": "6.2.4"}}',  # no device records at all
        '{"card0": {"SKU": "RX 9060 XT"}}',  # a card with no VRAM figures
        '{"card0": {"vram_total": null}}',
        '{"card0": {"% used": "1", "% free": "99"}}',  # percentages only
        "null\x00\xff",
    ],
)
def test_unusable_amd_payloads_yield_no_devices(payload: str) -> None:
    assert detect.parse_amd_smi(payload) == []


def test_a_free_figure_larger_than_total_is_reported_verbatim() -> None:
    payload = json.dumps({"card0": {"vram_total": 1048576, "vram_free": 99999999999}})
    (device,) = detect.parse_amd_smi(payload)
    assert device.memory_total_mib == 1
    assert device.memory_free_mib == 99999999999 // (1024 * 1024)


# --- the sysfs fallback -----------------------------------------------------


def test_sysfs_reports_total_and_derived_free(tmp_path: Path) -> None:
    write_sysfs_card(tmp_path, "card0", total=VRAM_16GIB, used=USED_256MIB)
    (device,) = detect.parse_sysfs_vram(tmp_path)
    assert device.vendor is GpuVendor.AMD
    assert device.index == 0
    assert device.name == "card0"
    assert device.driver == "amdgpu"
    assert device.memory_total_mib == 16368
    assert device.memory_free_mib == 16112
    assert device.available is True


def test_sysfs_cards_are_sorted_numerically(tmp_path: Path) -> None:
    for card in ("card10", "card2", "card0"):
        write_sysfs_card(tmp_path, card, total=VRAM_8GIB, used=0)
    devices = detect.parse_sysfs_vram(tmp_path)
    assert [device.index for device in devices] == [0, 2, 10]


def test_sysfs_ignores_connectors_and_foreign_cards(tmp_path: Path) -> None:
    write_sysfs_card(tmp_path, "card0", total=VRAM_16GIB, used=USED_256MIB)
    connector = tmp_path / "class" / "drm" / "card0-DP-1"
    connector.mkdir(parents=True)
    # An Intel iGPU shares the box: it has a card directory but no VRAM attributes.
    write_sysfs_card(tmp_path, "card1", total=None, used=None, driver="i915")
    devices = detect.parse_sysfs_vram(tmp_path)
    assert [device.name for device in devices] == ["card0"]


def test_sysfs_without_a_used_attribute_reports_no_free(tmp_path: Path) -> None:
    write_sysfs_card(tmp_path, "card0", total=VRAM_16GIB, used=None, driver=None)
    (device,) = detect.parse_sysfs_vram(tmp_path)
    assert device.memory_free_mib is None
    assert device.driver is None
    assert device.available is True


@pytest.mark.parametrize("total", ["[N/A]", "", "garbage", "-1"])
def test_sysfs_with_an_unreadable_total_is_skipped(tmp_path: Path, total: str) -> None:
    device_dir = write_sysfs_card(tmp_path, "card0", total=None, used=None)
    (device_dir / "mem_info_vram_total").write_text(total, encoding="utf-8")
    assert detect.parse_sysfs_vram(tmp_path) == []


def test_sysfs_without_a_drm_tree_yields_nothing(tmp_path: Path) -> None:
    assert detect.parse_sysfs_vram(tmp_path / "does-not-exist") == []
    empty = tmp_path / "empty"
    empty.mkdir()
    assert detect.parse_sysfs_vram(empty) == []


# --- probing, reason codes and ordering -------------------------------------


def test_the_probes_use_exactly_the_documented_commands(
    fake_probe: object, empty_sysfs: Path
) -> None:
    install = fake_probe  # type: ignore[operator]
    probe = install({})
    detect.probe_report(use_cache=False, sysfs_root=empty_sysfs)
    assert probe.calls[0] == NVIDIA_QUERY
    assert probe.calls[1][:4] == ("amd-smi", "metric", "--mem", "--json")
    assert probe.calls[2][:3] == ("rocm-smi", "--showmeminfo", "vram")


def test_a_machine_with_no_vendor_tools_still_reports_the_cpu_device(
    fake_probe: object, empty_sysfs: Path
) -> None:
    install = fake_probe  # type: ignore[operator]
    report = report_with(install({}), empty_sysfs)
    assert [device.vendor for device in report.devices] == [GpuVendor.CPU]
    cpu = report.devices[0]
    assert cpu.index == detect.CPU_DEVICE_INDEX == -1
    assert cpu.name == "cpu"
    assert cpu.memory_total_mib is None
    assert cpu.memory_free_mib is None
    assert cpu.driver is None
    assert cpu.available is True
    assert cpu.reason is None
    # GPU-07: the absence is explained, and PLAN.md §7.1's code is the AMD one.
    assert vendor_of(report, GpuVendor.NVIDIA).reason == "nvidia_smi_missing"
    assert vendor_of(report, GpuVendor.AMD).reason == "rocm_smi_missing"
    assert vendor_of(report, GpuVendor.AMD).available is False
    assert vendor_of(report, GpuVendor.CPU).available is True
    assert vendor_of(report, GpuVendor.CPU).reason is None


def test_detect_devices_matches_the_report(fake_probe: object, empty_sysfs: Path) -> None:
    install = fake_probe  # type: ignore[operator]
    install({"nvidia-smi": CommandResult(stdout=NVIDIA_TWO)})
    devices = detect.detect_devices(use_cache=False, sysfs_root=empty_sysfs)
    assert [device.vendor for device in devices] == [
        GpuVendor.NVIDIA,
        GpuVendor.NVIDIA,
        GpuVendor.CPU,
    ]
    assert isinstance(devices, list)


@pytest.mark.parametrize(
    ("result", "reason"),
    [
        (CommandResult(outcome=detect.OUTCOME_MISSING), "nvidia_smi_missing"),
        (CommandResult(outcome=detect.OUTCOME_TIMEOUT), "probe_timeout"),
        (CommandResult(outcome=detect.OUTCOME_SPAWN_FAILED), "probe_failed"),
        (CommandResult(returncode=1, stderr="NVIDIA-SMI has failed"), "probe_failed"),
        (CommandResult(stdout="total garbage"), "parse_failed"),
        (CommandResult(stdout="\n"), "no_devices"),
    ],
)
def test_nvidia_failures_map_to_stable_reason_codes(
    fake_probe: object, empty_sysfs: Path, result: CommandResult, reason: str
) -> None:
    install = fake_probe  # type: ignore[operator]
    report = report_with(install({"nvidia-smi": result}), empty_sysfs)
    nvidia = vendor_of(report, GpuVendor.NVIDIA)
    assert nvidia.available is False
    assert nvidia.reason == reason
    # The CPU pseudo-device is unaffected by a broken NVIDIA stack (GPU-08).
    assert [device.vendor for device in report.devices] == [GpuVendor.CPU]


@pytest.mark.parametrize(
    ("amd_result", "rocm_result", "reason"),
    [
        (CommandResult(outcome=detect.OUTCOME_TIMEOUT), None, "probe_timeout"),
        (CommandResult(returncode=2), None, "probe_failed"),
        (CommandResult(stdout="{broken"), None, "parse_failed"),
        (CommandResult(stdout="{}"), None, "no_devices"),
        (None, CommandResult(returncode=1), "probe_failed"),
        (None, None, "rocm_smi_missing"),
    ],
)
def test_amd_failures_map_to_stable_reason_codes(
    fake_probe: object,
    empty_sysfs: Path,
    amd_result: CommandResult | None,
    rocm_result: CommandResult | None,
    reason: str,
) -> None:
    install = fake_probe  # type: ignore[operator]
    results: dict[str, CommandResult] = {}
    if amd_result is not None:
        results["amd-smi"] = amd_result
    if rocm_result is not None:
        results["rocm-smi"] = rocm_result
    report = report_with(install(results), empty_sysfs)
    assert vendor_of(report, GpuVendor.AMD).reason == reason


def test_the_first_amd_tool_that_answers_wins(fake_probe: object, empty_sysfs: Path) -> None:
    install = fake_probe  # type: ignore[operator]
    probe = install(
        {
            "amd-smi": CommandResult(returncode=1, stderr="unsupported"),
            "rocm-smi": CommandResult(stdout=ROCM_SMI),
        }
    )
    report = report_with(probe, empty_sysfs)
    assert vendor_of(report, GpuVendor.AMD).available is True
    assert [device.memory_total_mib for device in report.devices] == [16368, None]
    assert probe.count("rocm-smi") == 1


def test_the_sysfs_fallback_is_used_when_both_tools_are_absent(
    fake_probe: object, tmp_path: Path
) -> None:
    install = fake_probe  # type: ignore[operator]
    write_sysfs_card(tmp_path, "card0", total=VRAM_16GIB, used=USED_256MIB)
    report = report_with(install({}), tmp_path)
    assert vendor_of(report, GpuVendor.AMD).available is True
    assert [device.vendor for device in report.devices] == [GpuVendor.AMD, GpuVendor.CPU]
    assert report.devices[0].memory_free_mib == 16112


def test_both_vendors_are_reported_with_unique_indices(
    fake_probe: object, empty_sysfs: Path
) -> None:
    install = fake_probe  # type: ignore[operator]
    install(
        {
            "nvidia-smi": CommandResult(stdout=NVIDIA_TWO),
            "amd-smi": CommandResult(stdout=AMD_SMI_LIST),
        }
    )
    report = (
        report_with(install({}), empty_sysfs)
        if False
        else detect.probe_report(use_cache=False, sysfs_root=empty_sysfs)
    )
    # Documented order: NVIDIA, then AMD, then the CPU pseudo-device last.
    assert [device.vendor for device in report.devices] == [
        GpuVendor.NVIDIA,
        GpuVendor.NVIDIA,
        GpuVendor.AMD,
        GpuVendor.AMD,
        GpuVendor.CPU,
    ]
    # AMD's ordinals would collide with NVIDIA's, so the group continues from the
    # highest index already taken: GPU-04 addresses devices by index.
    assert [device.index for device in report.devices] == [0, 1, 2, 3, -1]
    assert len({device.index for device in report.devices}) == len(report.devices)


def test_a_non_colliding_amd_ordinal_is_preserved(fake_probe: object, tmp_path: Path) -> None:
    install = fake_probe  # type: ignore[operator]
    install({"nvidia-smi": CommandResult(stdout=NVIDIA_ONE)})
    # card1 only: index 1 does not collide with NVIDIA's index 0, and it is the
    # ordinal HIP_VISIBLE_DEVICES expects in M3 (D-13), so it is left alone.
    write_sysfs_card(tmp_path, "card1", total=VRAM_16GIB, used=USED_256MIB)
    report = detect.probe_report(use_cache=False, sysfs_root=tmp_path)
    assert [device.index for device in report.devices] == [0, 1, -1]


def test_reason_codes_are_snake_case_tokens_not_prose(
    fake_probe: object, empty_sysfs: Path
) -> None:
    install = fake_probe  # type: ignore[operator]
    report = report_with(install({}), empty_sysfs)
    reasons = [entry.reason for entry in report.vendors if entry.reason is not None]
    assert reasons
    for reason in reasons:
        assert re.fullmatch(r"[a-z][a-z0-9_]*", reason), reason
        assert " " not in reason


def test_a_probe_that_raises_is_contained(
    monkeypatch: pytest.MonkeyPatch, fake_probe: object, empty_sysfs: Path
) -> None:
    install = fake_probe  # type: ignore[operator]
    install({"nvidia-smi": CommandResult(stdout=NVIDIA_ONE)})

    def explode(stdout: str) -> list[GpuDeviceInfo]:
        raise RuntimeError("the driver handed back something nobody anticipated")

    monkeypatch.setattr(detect, "parse_nvidia_smi", explode)
    report = detect.probe_report(use_cache=False, sysfs_root=empty_sysfs)
    assert [device.vendor for device in report.devices] == [GpuVendor.CPU]
    assert vendor_of(report, GpuVendor.NVIDIA).reason == "probe_failed"


def test_a_missing_binary_is_reported_without_spawning_a_process() -> None:
    result = detect.run_probe_command(("praelector-no-such-tool", "--help"))
    assert result.outcome == detect.OUTCOME_MISSING


# --- the 5 s cache ----------------------------------------------------------


def test_two_calls_within_the_window_probe_once(fake_probe: object, empty_sysfs: Path) -> None:
    install = fake_probe  # type: ignore[operator]
    probe = install({"nvidia-smi": CommandResult(stdout=NVIDIA_ONE)})
    clock = FakeClock()

    first = detect.probe_report(now=clock, sysfs_root=empty_sysfs)
    second = detect.probe_report(now=clock, sysfs_root=empty_sysfs)

    assert probe.count("nvidia-smi") == 1
    assert second is first
    assert len(second.devices) == 2


def test_a_call_after_the_window_probes_again(fake_probe: object, empty_sysfs: Path) -> None:
    install = fake_probe  # type: ignore[operator]
    probe = install({"nvidia-smi": CommandResult(stdout=NVIDIA_ONE)})
    clock = FakeClock()

    detect.probe_report(now=clock, sysfs_root=empty_sysfs)
    clock.advance(detect.CACHE_TTL_S - 0.001)
    detect.probe_report(now=clock, sysfs_root=empty_sysfs)
    assert probe.count("nvidia-smi") == 1

    clock.advance(0.002)
    third = detect.probe_report(now=clock, sysfs_root=empty_sysfs)
    assert probe.count("nvidia-smi") == 2
    # A refreshed report is a new object, so a caller holding the old one is safe.
    assert len(third.devices) == 2


def test_bypassing_the_cache_probes_every_time_and_does_not_fill_it(
    fake_probe: object, empty_sysfs: Path
) -> None:
    install = fake_probe  # type: ignore[operator]
    probe = install({"nvidia-smi": CommandResult(stdout=NVIDIA_ONE)})
    clock = FakeClock()

    detect.probe_report(use_cache=False, now=clock, sysfs_root=empty_sysfs)
    detect.probe_report(use_cache=False, now=clock, sysfs_root=empty_sysfs)
    assert probe.count("nvidia-smi") == 2

    detect.probe_report(now=clock, sysfs_root=empty_sysfs)
    assert probe.count("nvidia-smi") == 3


def test_invalidate_cache_forces_a_new_probe(fake_probe: object, empty_sysfs: Path) -> None:
    install = fake_probe  # type: ignore[operator]
    probe = install({"nvidia-smi": CommandResult(stdout=NVIDIA_ONE)})
    clock = FakeClock()

    detect.probe_report(now=clock, sysfs_root=empty_sysfs)
    detect.invalidate_cache()
    detect.probe_report(now=clock, sysfs_root=empty_sysfs)
    assert probe.count("nvidia-smi") == 2


def test_detect_devices_shares_the_cache(fake_probe: object, empty_sysfs: Path) -> None:
    install = fake_probe  # type: ignore[operator]
    probe = install({"nvidia-smi": CommandResult(stdout=NVIDIA_ONE)})
    clock = FakeClock()

    detect.detect_devices(now=clock, sysfs_root=empty_sysfs)
    detect.detect_devices(now=clock, sysfs_root=empty_sysfs)
    assert probe.count("nvidia-smi") == 1


# --- the device model -------------------------------------------------------


def test_the_device_model_is_frozen() -> None:
    device = detect.cpu_device()
    with pytest.raises(ValidationError):
        device.available = False  # type: ignore[misc]


def test_the_cpu_pseudo_device_is_a_value(fake_probe: object, empty_sysfs: Path) -> None:
    install = fake_probe  # type: ignore[operator]
    install({})
    assert detect.probe_cpu() == [detect.cpu_device()]
    assert detect.probe_nvidia() == []
    assert detect.probe_amd(sysfs_root=empty_sysfs) == []
