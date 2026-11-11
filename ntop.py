#!/usr/bin/env python3
"""npu_top.py — Furiosa RNGD NPU htop-style TUI 모니터 (옵션 C)

`furiosa-smi status --format json` 과 `furiosa-smi info --format json` 출력을 합쳐
htop 처럼 디바이스마다 메모리·8코어 사용률·온도·전력을 막대그래프로 보여줍니다.
`nctop` 으로 부르면 첫 화면에 CPU·RAM 요약과 GPU(`nvidia-smi`) 표가 같이 나오고,
CPU 코어별 사용률과 GPU 상세는 → 키로 넘기는 둘째 화면에 있습니다.

사용:
    python3 npu_top.py
    python3 npu_top.py -i 0.5        # 0.5초 새로고침
    python3 npu_top.py --no-ps       # 프로세스 패널 끄기
    python3 npu_top.py --raw         # JSON 원본 표시 (디버그)
    python3 npu_top.py --gpu         # GPU 패널 켜기 (nctop 은 nvidia-smi 가 있으면 켜진 채로 시작)
    python3 npu_top.py -p 2          # 둘째 화면에서 시작

키:
    → / ←    다음 / 이전 화면  (l / h, Tab / Shift+Tab, 숫자 1·2 도 같음)
    q        종료  (Ctrl+C 도 됨)

의존:
    pip install rich
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import pwd
import re
import select
import shutil
import signal
import subprocess
import sys
import termios
import threading
import time
import tty
from dataclasses import dataclass, field
from datetime import datetime

try:
    from rich.align import Align
    from rich.console import Console, Group
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
except ImportError:
    print("❌ rich 가 필요합니다:  pip install rich", file=sys.stderr)
    sys.exit(1)


# ──────────────────────────── 데이터 모델 ────────────────────────────
@dataclass
class NpuDev:
    name: str = ""
    arch: str = ""
    liveness: str = ""
    mem_used: float = 0.0        # GiB
    mem_total: float = 0.0       # GiB
    mem_ratio: float = 0.0       # 0.0 ~ 1.0
    core_utils: list[float] = field(default_factory=list)   # 0.0 ~ 1.0 per core
    core_busy: list[bool] = field(default_factory=list)
    temp_c: float = 0.0
    power_w: float = 0.0
    governor: str = ""
    pci_bdf: str = ""
    firmware: str = ""

    @property
    def util_avg(self) -> float:
        if not self.core_utils:
            return 0.0
        return sum(self.core_utils) / len(self.core_utils)

    @property
    def util_max(self) -> float:
        if not self.core_utils:
            return 0.0
        return max(self.core_utils)


@dataclass
class GpuDev:
    """nvidia-smi --query-gpu 한 줄. 드라이버마다 있는 필드가 달라서 값은 필드 이름으로 꺼낸다."""
    q: dict[str, str] = field(default_factory=dict)

    def num(self, key: str) -> float | None:
        """숫자 필드. 'N/A'·'[N/A]' 이거나 드라이버가 모르는 필드면 None."""
        try:
            return float(self.q.get(key, ""))
        except ValueError:
            return None

    def ratio(self, key: str) -> float | None:
        """퍼센트 필드를 0.0 ~ 1.0 으로."""
        v = self.num(key)
        return None if v is None else v / 100.0

    def txt(self, key: str) -> str:
        """문자열 필드. 값이 없다는 표시('N/A' 등)는 빈 문자열로."""
        v = self.q.get(key, "")
        return "" if v.strip("[]") in ("", "N/A", "Not Supported", "Unknown Error") else v

    @property
    def index(self) -> int:
        return int(self.num("index") or 0)

    @property
    def name(self) -> str:
        return self.q.get("name", "") or "?"

    @property
    def mem_used(self) -> float:         # GiB (nvidia-smi 는 MiB 로 준다)
        return (self.num("memory.used") or 0.0) / 1024

    @property
    def mem_total(self) -> float:        # GiB
        return (self.num("memory.total") or 0.0) / 1024

    @property
    def clock_events(self) -> list[tuple[str, str]] | None:
        """지금 클럭을 붙잡고 있는 사유 [(이름, 스타일)]. 드라이버가 안 알려 주면 None."""
        try:
            mask = int(self.txt("clocks_event_reasons.active"), 16)
        except ValueError:
            return None
        return [(name, style) for bit, name, style in GPU_CLOCK_EVENTS if mask & bit]


@dataclass
class GpuProc:
    """nvidia-smi pmon 한 줄 + /proc 에서 읽은 사용자·명령줄."""
    gpu: int = 0
    pid: int = 0
    type: str = ""               # C(compute) / G(graphics) / C+G
    sm: float | None = None      # 연산 사용률 %
    mem: float | None = None     # 메모리 읽기·쓰기 사용률 %
    enc: float | None = None
    dec: float | None = None
    fb_mib: float | None = None  # GPU 메모리 (MiB)
    name: str = ""               # pmon 이 주는 이름 (15자에서 잘림)
    user: str = ""
    cmd: str = ""


@dataclass
class HostStat:
    cpu_total: float = 0.0       # 0.0 ~ 1.0
    cpu_ids: list[int] = field(default_factory=list)
    cpu_utils: list[float] = field(default_factory=list)    # cpu_ids 와 같은 순서
    ram_used: float = 0.0        # GiB
    ram_total: float = 0.0
    swap_used: float = 0.0
    swap_total: float = 0.0
    loadavg: str = ""
    model: str = "?"


@dataclass
class Snapshot:
    """한 번 수집한 결과 — 화면은 이것만 보고 그린다 (그리는 쪽은 아무것도 실행하지 않는다)."""
    ts: float = 0.0              # 수집을 마친 시각 (time.monotonic)
    devs: list[NpuDev] = field(default_factory=list)
    raw_payload: str = ""
    host: HostStat | None = None
    gpus: list[GpuDev] = field(default_factory=list)
    gpu_error: str = ""
    gpu_procs: list[GpuProc] = field(default_factory=list)
    gpu_procs_error: str = ""
    ps_rows: list[tuple[str, ...]] | None = None    # None = ps 실패
    error: str = ""              # 수집 중 잡힌 예외


def _gib(x_bytes: float) -> float:
    return x_bytes / (1024 ** 3)


def _parse_float(s: str) -> float:
    m = re.search(r"-?[0-9]+(?:\.[0-9]+)?", s or "")
    return float(m.group(0)) if m else 0.0


# ──────────────────────────── SMI 호출 ────────────────────────────
def run_smi_json(subcmd: str, timeout: float = 3.0) -> list[dict]:
    try:
        r = subprocess.run(
            ["furiosa-smi", subcmd, "--format", "json"],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
        if r.returncode != 0:
            return []
        return json.loads(r.stdout or "[]")
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return []


def run_smi_text(subcmd: str, timeout: float = 3.0) -> str:
    try:
        r = subprocess.run(
            ["furiosa-smi", subcmd],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
        return (r.stdout or "") + (("\n" + r.stderr) if r.stderr.strip() else "")
    except Exception as e:
        return f"(error: {e})"


MGMT_SYSFS = "/sys/class/rngd_mgmt/rngd!{}mgmt"
HEARTBEAT_STALL_S = 5.0
_heartbeat_seen: dict[str, tuple[str, float]] = {}   # dev → (마지막 값, 바뀐 시각)


def _read_sysfs(path: str) -> str | None:
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def sysfs_liveness(name: str) -> str:
    """furiosa-smi 2026.4.0 부터 status JSON 에 liveness 가 없어져서 sysfs 로 판정.

    device_state 0 = 정상, heartbeat 는 펌웨어가 초당 올리는 카운터 → 멈추면 hang.
    """
    base = MGMT_SYSFS.format(name)
    state = _read_sysfs(base + "/device_state")
    if state is None:
        return ""
    if state != "0":
        return "err"
    hb = _read_sysfs(base + "/heartbeat")
    if hb is None:
        return "alive"
    now = time.monotonic()
    prev = _heartbeat_seen.get(name)
    if prev is None or prev[0] != hb:
        _heartbeat_seen[name] = (hb, now)
        return "alive"
    return "hang" if now - prev[1] > HEARTBEAT_STALL_S else "alive"


def gather() -> list[NpuDev]:
    """status + info 를 JSON 으로 받아서 디바이스 단위로 머지."""
    status = run_smi_json("status")
    info = run_smi_json("info")
    info_by_dev = {d.get("dev_name"): d for d in info}

    devs: list[NpuDev] = []
    for s in status:
        name = s.get("device", "")
        dev = NpuDev(
            name=name,
            arch=s.get("arch", ""),
            liveness=s.get("liveness") or sysfs_liveness(name),
        )

        mem = s.get("memory") or {}
        dram = mem.get("DRAM") or mem     # 2026.4.0 부터 DRAM 단계 없이 memory 에 바로
        dev.mem_used = _gib(dram.get("used_size", 0))
        dev.mem_total = _gib(dram.get("total_size", 0))
        dev.mem_ratio = float(dram.get("used_ratio", 0.0))

        for pe in (s.get("pe_utilizations") or []):
            dev.core_utils.append(float(pe.get("pe_utilization", 0.0)))
            dev.core_busy.append(bool(pe.get("pe_occupancy", False)))

        meta = info_by_dev.get(name) or {}
        dev.temp_c = _parse_float(meta.get("temperature", ""))
        dev.power_w = _parse_float(meta.get("power", ""))
        dev.governor = meta.get("governor", "")
        dev.pci_bdf = meta.get("pci_bdf", "")
        dev.firmware = meta.get("firmware", "")

        devs.append(dev)
    return devs


# ──────────────────────────── GPU (nvidia-smi) ────────────────────────────
def run_cmd(argv: list[str], timeout: float = 3.0) -> tuple[int, str, str]:
    """(returncode, stdout, stderr). 실행 파일이 없거나 시간을 넘기면 returncode -1."""
    try:
        r = subprocess.run(argv, capture_output=True, text=True, errors="replace",
                           timeout=timeout, check=False)
        return r.returncode, r.stdout or "", r.stderr or ""
    except subprocess.TimeoutExpired:
        return -1, "", f"{argv[0]} 응답 없음 ({timeout:.0f}s 초과)"
    except OSError as e:
        return -1, "", f"{argv[0]} 실행 실패: {e.strerror or e}"


def _first_line(s: str) -> str:
    for line in s.splitlines():
        if line.strip():
            return line.strip()
    return ""


# 이름에 쉼표가 있어도 열이 안 밀리도록 name 은 맨 끝.
GPU_FIELDS = [
    "index", "uuid", "pci.bus_id", "driver_version",
    "utilization.gpu", "utilization.memory", "utilization.encoder", "utilization.decoder",
    "utilization.jpeg", "utilization.ofa",
    "memory.used", "memory.total", "memory.reserved",
    "temperature.gpu", "temperature.gpu.tlimit", "fan.speed", "pstate",
    "power.draw", "power.draw.average", "power.draw.instant", "power.limit",
    "clocks.current.graphics", "clocks.max.graphics",
    "clocks.current.memory", "clocks.max.memory",
    "pcie.link.gen.gpucurrent", "pcie.link.gen.current", "pcie.link.gen.max",
    "pcie.link.width.current", "pcie.link.width.max",
    "compute_mode", "persistence_mode",
    "ecc.errors.corrected.volatile.total", "ecc.errors.uncorrected.volatile.total",
    "clocks_event_reasons.active",
    "name",
]
_gpu_fields = list(GPU_FIELDS)      # 드라이버가 모르는 필드는 빼 가며 줄어든다

# nvml.h 의 nvmlClocksEventReason* 비트 → (이름, 스타일)
GPU_CLOCK_EVENTS = [
    (0x001, "idle", "dim"),
    (0x002, "app clocks", "dim"),
    (0x004, "sw power cap", "yellow"),
    (0x008, "hw slowdown", "bold red"),
    (0x010, "sync boost", "dim"),
    (0x020, "sw thermal", "bold red"),
    (0x040, "hw thermal", "bold red"),
    (0x080, "hw power brake", "bold red"),
    (0x100, "display clocks", "dim"),
]


def parse_gpu_csv(out: str, fields: list[str]) -> list[GpuDev]:
    """`--format=csv,noheader,nounits` 출력 → GPU 목록. 마지막 필드는 쉼표를 품어도 된다."""
    gpus: list[GpuDev] = []
    for line in out.splitlines():
        vals = [v.strip() for v in line.split(",", len(fields) - 1)]
        if len(vals) == len(fields):
            gpus.append(GpuDev(dict(zip(fields, vals))))
    return gpus


def gather_gpus() -> tuple[list[GpuDev], str]:
    """(GPU 목록, 오류 문구). 드라이버가 모르는 필드는 빼고 다시 묻는다."""
    while True:
        fields = list(_gpu_fields)
        rc, out, err = run_cmd(["nvidia-smi", "--query-gpu=" + ",".join(fields),
                                "--format=csv,noheader,nounits"])
        m = re.search(r'Field "([^"]+)" is not a valid field', out + err)
        if rc != 0 and m and m.group(1) in _gpu_fields and len(_gpu_fields) > 1:
            _gpu_fields.remove(m.group(1))
            continue
        break
    if rc != 0:
        return [], _first_line(err) or _first_line(out) or f"nvidia-smi 실패 (종료 코드 {rc})"
    return parse_gpu_csv(out, fields), ""


def parse_pmon(out: str) -> list[GpuProc]:
    """`nvidia-smi pmon -c 1 -s um` 출력 → 프로세스 목록. 열 구성은 머리줄에서 읽는다."""
    cols: list[str] = []
    procs: list[GpuProc] = []
    for line in out.splitlines():
        if line.startswith("#"):
            if not cols:
                cols = line.lstrip("#").split()     # gpu pid type sm mem enc dec ... fb ... command
            continue
        if not cols:
            continue
        row = dict(zip(cols, line.split(None, len(cols) - 1)))
        if not row.get("pid", "").isdigit():        # 프로세스가 없는 GPU 는 pid 자리가 '-'
            continue

        def num(key: str) -> float | None:
            try:
                return float(row.get(key, ""))
            except ValueError:
                return None

        procs.append(GpuProc(
            gpu=int(num("gpu") or 0), pid=int(row["pid"]), type=row.get("type", ""),
            sm=num("sm"), mem=num("mem"), enc=num("enc"), dec=num("dec"),
            fb_mib=num("fb"), name=row.get("command", "").strip(),
        ))
    return procs


_user_names: dict[int, str] = {}


def _proc_user_cmd(pid: int) -> tuple[str, str]:
    """(사용자, 명령줄). 프로세스가 이미 끝났거나 못 읽으면 빈 문자열."""
    user = cmd = ""
    try:
        uid = os.stat(f"/proc/{pid}").st_uid
        if uid not in _user_names:
            try:
                _user_names[uid] = pwd.getpwuid(uid).pw_name
            except KeyError:
                _user_names[uid] = str(uid)
        user = _user_names[uid]
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            cmd = f.read().replace(b"\0", b" ").decode(errors="replace").strip()
    except OSError:
        pass
    return user, cmd


def gather_gpu_procs() -> tuple[list[GpuProc], str]:
    """(GPU 를 쓰는 프로세스 — 메모리 큰 순, 오류 문구)."""
    rc, out, err = run_cmd(["nvidia-smi", "pmon", "-c", "1", "-s", "um"])
    if rc != 0:
        return [], _first_line(err) or _first_line(out) or f"nvidia-smi pmon 실패 (종료 코드 {rc})"
    procs = parse_pmon(out)
    for p in procs:
        p.user, p.cmd = _proc_user_cmd(p.pid)
    procs.sort(key=lambda p: -(p.fb_mib or 0.0))
    return procs, ""


# ──────────────────────────── 렌더 helpers ────────────────────────────
def util_color(ratio: float) -> str:
    """ratio: 0.0 ~ 1.0"""
    pct = ratio * 100
    if pct < 30:
        return "green"
    if pct < 70:
        return "yellow"
    return "red"


# 유니코드 블록 문자 (가로 막대 - 풀 채움)
BAR_FULL = "█"
BAR_EMPTY = "░"
# 1/8 단위 세로 막대 (single-cell 가변 채움)
EIGHTHS = " ▁▂▃▄▅▆▇█"


def pct_text(ratio: float, *, width: int = 5) -> Text:
    """ratio: 0~1 → 색칠된 ' XX.X%'. idle 은 dim."""
    pct = max(0.0, min(1.0, ratio)) * 100
    style = "dim" if ratio < 0.005 else util_color(ratio)
    return Text(f"{pct:{width}.1f}%", style=style)


def mem_only_text(used_g: float, total_g: float) -> Text:
    """' 0.0/48G (0.0%)' — 막대 없이 숫자만."""
    ratio = (used_g / total_g) if total_g > 0 else 0.0
    style = "dim" if ratio < 0.01 else util_color(ratio)
    t = Text(f"{used_g:5.1f}/{total_g:.0f}G", style=style)
    t.append(f" ({ratio*100:4.1f}%)", style="dim")
    return t


def fmt_mib(mib: float | None) -> str:
    """MiB → '38.6G' / '512M'."""
    if mib is None:
        return "-"
    return f"{mib / 1024:.1f}G" if mib >= 1024 else f"{mib:.0f}M"


def bar_text(ratio: float, width: int, style: str = "") -> Text:
    """가로 막대 — ratio(0~1) 만큼 채운다."""
    ratio = max(0.0, min(1.0, ratio))
    filled = int(round(ratio * width))
    t = Text(BAR_FULL * filled, style=style or util_color(ratio))
    t.append(BAR_EMPTY * (width - filled), style="bright_black")
    return t


def _join(parts: list[Text]) -> Text:
    """조각들을 '  ·  ' 로 잇는다 (빈 조각은 건너뜀)."""
    out = Text()
    for p in parts:
        if not p.plain:
            continue
        if out.plain:
            out.append("  ·  ", style="dim")
        out.append(p)
    return out


def _core_cell(i: int, u: float, busy_flag: bool, label_width: int) -> Text:
    """단일 코어 셀 'cNN:XX%' — Table.grid 의 cell 단위로 들어가 wrap 에서 안 깨짐."""
    t = Text()
    label_style = "bold cyan" if busy_flag else "dim"
    t.append(f"c{i:>{label_width}}:", style=label_style)
    val_style = "dim" if u < 0.005 else util_color(u)
    t.append(f"{u*100:3.0f}%", style=val_style)
    return t


def cores_grid(utils: list[float], busy: list[bool], per_row: int = 8,
               label_width: int = 0, ids: list[int] | None = None):
    """N개 코어를 per_row 컬럼 Table.grid 로 그림.
    각 셀이 Table.grid 의 cell 이라 rich wrap 에서 절대 안 끊김.
    NPU 표 안의 cell 에 들어가도 OK 하도록 expand=False 로 콘텐츠 폭만 차지.
    ids 를 주면 셀 번호로 그 값을 쓴다 (NUMA 노드별로 묶을 때 실제 CPU 번호)."""
    if label_width == 0:
        label_width = len(str(max(len(utils) - 1, 0)))
    grid = Table.grid(padding=(0, 1), expand=False)
    for _ in range(per_row):
        grid.add_column(no_wrap=True)
    # per_row 단위로 행 채움
    for row_start in range(0, len(utils), per_row):
        row_cells = []
        for j in range(per_row):
            i = row_start + j
            if i >= len(utils):
                row_cells.append("")
            else:
                row_cells.append(_core_cell(ids[i] if ids else i, utils[i], busy[i], label_width))
        grid.add_row(*row_cells)
    return grid


# 하위 호환 — render_devices 가 Table.grid 도 cell 로 받음
def cores_text(utils, busy, per_row=8, label_width=0):
    return cores_grid(utils, busy, per_row=per_row, label_width=label_width)


def cores_strip(utils: list[float]) -> Text:
    """코어 하나를 한 칸 세로 막대로 — 화면이 작아 그리드가 다 안 들어갈 때 쓴다."""
    t = Text()
    for u in utils:
        level = max(1, min(8, int(round(u * 8))))
        t.append(EIGHTHS[level], style="dim" if u < 0.005 else util_color(u))
    return t


def cores_per_row(console_width: int, n_cores: int, label_width: int = 1) -> int:
    """터미널 폭에 따라 한 행에 표시할 코어 수 결정.
    NPU 표의 다른 컬럼들이 차지하는 폭과 보더/패딩을 빼고 per-core 컬럼이 실제로
    받게 될 폭을 추정한 뒤, 코어 한 칸(c+label+':'+'NN%'+gap) 폭으로 나눠 결정."""
    # NPU 표: padding=(0,0), 보더 8칸 (외곽 2 + 사이 6). 고정폭 컬럼 합 ≈ 43.
    # min_width Per-core(15) + Memory(14) 가 남는 폭(=W-8-43-29) 을 절반씩 분배.
    # → per-core 가 받는 실효 폭 ≈ 15 + (W - 80) / 2 = W/2 - 25
    cell_w = 1 + label_width + 1 + 3 + 2          # c + label + : + 'NN%' + '  '
    avail = max(12, (console_width // 2) - 25)
    fit = max(1, avail // cell_w)
    if fit >= n_cores:
        return n_cores
    for cand in (8, 4, 2, 1):
        if cand <= fit:
            return cand
    return 1


def mem_text(d: "NpuDev", width: int = 12) -> Text:
    """NPU 메모리 — 막대 없이 숫자만."""
    return mem_only_text(d.mem_used, d.mem_total)


def render_devices(devs: list[NpuDev], console_width: int = 140, compact: bool = False) -> Table:
    # per-core 컬럼 표시 여부 — 8코어 기준 2행 안에 들어갈 때만 (3행 이상이면 숨김)
    n_cores = len(devs[0].core_utils) if devs and devs[0].core_utils else 8
    label_w = len(str(max(n_cores - 1, 0)))
    per_row = cores_per_row(console_width, n_cores, label_width=label_w)
    show_percore = per_row * 2 >= n_cores       # 2행 이내일 때만 표시

    # padding=(0,0) 으로 컬럼 양 옆 공백 제거 → 좁은 콘솔에서 표가 안 잘리도록
    # compact: 세로 자리가 모자랄 때 행 사이 구분선을 뺀다
    tbl = Table(expand=True, show_lines=not compact, header_style="bold cyan",
                border_style="bright_black", padding=(0, 0))
    tbl.add_column("Device", style="bold yellow", width=5)
    tbl.add_column("Status", width=5)
    tbl.add_column("Util", width=6, justify="right")
    if show_percore:
        tbl.add_column("Per-core", min_width=15, overflow="fold")
    tbl.add_column("Memory", min_width=14)
    tbl.add_column("Temp", width=7, justify="right")
    tbl.add_column("Power", width=5, justify="right")

    if not devs:
        cols = 7 if show_percore else 6
        tbl.add_row(*(["(no NPU)"] + ["-"] * (cols - 1)))
        return tbl

    for d in devs:
        status = Text(d.liveness or "?",
                      style="bold green" if d.liveness == "alive" else "bold red")
        util_avg = pct_text(d.util_avg, width=5)
        mem = mem_text(d)
        temp_style = "red" if d.temp_c >= 70 else ("yellow" if d.temp_c >= 55 else "")
        temp = Text(f"{d.temp_c:.1f}°C", style=temp_style)
        power = Text(f"{d.power_w:.0f}W", style="magenta")

        row = [d.name, status, util_avg]
        if show_percore:
            row.append(cores_text(d.core_utils, d.core_busy,
                                   per_row=per_row, label_width=label_w))
        row += [mem, temp, power]
        tbl.add_row(*row)
    return tbl


def render_header(devs: list[NpuDev], title: str = "ntop", *, pages: list[str] | None = None,
                  page: int = 0, keys_on: bool = False, width: int = 0,
                  warn: str = "") -> Panel:
    """요약 한 줄. 화면이 둘 이상이면 위 테두리에 화면 탭, 아래 테두리에 키 안내를 단다."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    n_alive = sum(1 for d in devs if d.liveness == "alive")
    n_busy = sum(1 for d in devs if any(d.core_busy))
    total_pwr = sum(d.power_w for d in devs)
    avg_temp = (sum(d.temp_c for d in devs) / len(devs)) if devs else 0
    # 총합 util: 모든 디바이스의 모든 코어 평균
    all_utils = [u for d in devs for u in d.core_utils]
    total_util = sum(all_utils) / len(all_utils) if all_utils else 0.0
    # 총합 메모리: GiB 합
    mem_used = sum(d.mem_used for d in devs)
    mem_total = sum(d.mem_total for d in devs)
    mem_ratio = (mem_used / mem_total) if mem_total > 0 else 0.0

    util_color_style = util_color(total_util) if total_util > 0.005 else "dim"
    mem_color_style = util_color(mem_ratio) if mem_ratio > 0.01 else "dim"

    parts = [Text(title, style="bold bright_cyan"), Text(now, style="white")]
    if warn:
        parts.append(Text(warn, style="bold red"))
    parts += [
        Text(f"{n_alive}/{len(devs)} alive", style="green"),
        Text.assemble(("NPU ", "bold"), (f"{total_util*100:5.1f}%", util_color_style)),
        Text.assemble(("MEM ", "bold"), (f"{mem_used:4.1f}/{mem_total:.0f}G", mem_color_style)),
        Text(f"{n_busy} busy", style="yellow"),
        Text(f"{total_pwr:.0f}W", style="magenta"),
        Text(f"avg {avg_temp:.1f}°C", style="red" if avg_temp >= 70 else ""),
    ]
    # 한 줄에 안 들어가면 뒤에서부터 뺀다 — 줄이 넘어가면 둘째 줄은 잘려서 안 보인다
    while width and len(parts) > 2 and \
            sum(p.cell_len for p in parts) + 5 * (len(parts) - 1) > width - 4:
        parts.pop()

    pages = pages or []
    tabs = None
    hint = "q/Ctrl+C: quit" if keys_on else "Ctrl+C: quit"
    if len(pages) > 1:
        tabs = Text()
        for i, name in enumerate(pages):
            tabs.append(f" {i + 1} {name} ", style="bold reverse" if i == page else "dim")
        if keys_on:
            hint = "←/→: page  ·  " + hint
    summary = _join(parts)
    summary.no_wrap, summary.overflow = True, "ellipsis"
    return Panel(Align.center(summary), style="cyan", padding=(0, 1),
                 title=tabs, title_align="left",
                 subtitle=Text(hint, style="dim italic"), subtitle_align="right")


# CPU 패널을 위한 직전 값 캐시 (/proc/stat polling용)
_CPU_PREV: dict = {}


def _read_proc_stat() -> dict[int, tuple[int, int]]:
    """/proc/stat → {cpu_id: (busy_jiffies, total_jiffies)}.
    cpu_id == -1 은 합계 (cpu 라인)."""
    out: dict[int, tuple[int, int]] = {}
    try:
        with open("/proc/stat") as f:
            for line in f:
                if not line.startswith("cpu"):
                    break
                parts = line.split()
                head = parts[0]
                fields = [int(x) for x in parts[1:8]]
                # user, nice, system, idle, iowait, irq, softirq
                total = sum(fields)
                idle = fields[3] + fields[4]
                busy = total - idle
                if head == "cpu":
                    out[-1] = (busy, total)
                else:
                    out[int(head[3:])] = (busy, total)
    except Exception:
        pass
    return out


def get_cpu_utils() -> tuple[float, list[int], list[float]]:
    """(total_util_ratio, cpu_ids, per_core_util_ratios). /proc/stat delta 기반."""
    cur = _read_proc_stat()
    ids = sorted(k for k in cur if k >= 0)
    if not cur or not _CPU_PREV:
        _CPU_PREV.update(cur)
        # 첫 호출이면 0 반환 (다음 tick부터 실측)
        return 0.0, ids, [0.0] * len(ids)
    out_total = 0.0
    per_core: list[float] = []
    for cpu_id in [-1] + ids:
        if cpu_id not in cur:
            continue
        busy, total = cur[cpu_id]
        pb, pt = _CPU_PREV.get(cpu_id, (busy, total))
        db = busy - pb
        dt = total - pt
        util = (db / dt) if dt > 0 else 0.0
        util = max(0.0, min(1.0, util))
        if cpu_id == -1:
            out_total = util
        else:
            per_core.append(util)
    _CPU_PREV.update(cur)
    return out_total, ids, per_core


def _read_meminfo_kb() -> dict[str, int]:
    info: dict[str, int] = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                k, _, v = line.partition(":")
                parts = v.strip().split()
                if parts:
                    info[k.strip()] = int(parts[0])  # kB
    except Exception:
        pass
    return info


def read_meminfo_gib() -> tuple[float, float]:
    """RAM (used_GiB, total_GiB). free -h 와 같은 식: total - available."""
    info = _read_meminfo_kb()
    total = info.get("MemTotal", 0) / 1024 / 1024
    avail = info.get("MemAvailable", info.get("MemFree", 0)) / 1024 / 1024
    used = max(0.0, total - avail)
    return used, total


def read_swapinfo_gib() -> tuple[float, float]:
    """SWAP (used_GiB, total_GiB)."""
    info = _read_meminfo_kb()
    total = info.get("SwapTotal", 0) / 1024 / 1024
    free = info.get("SwapFree", 0) / 1024 / 1024
    used = max(0.0, total - free)
    return used, total


_cpu_model: str | None = None


def cpu_model() -> str:
    """CPU 모델 이름 — 안 바뀌니 한 번만 읽는다."""
    global _cpu_model
    if _cpu_model is None:
        model = "?"
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if "model name" in line:
                        model = line.split(":", 1)[1].strip()
                        break
        except Exception:
            pass
        if len(model) > 50:
            model = model[:48] + "…"
        _cpu_model = model
    return _cpu_model


def parse_cpulist(s: str) -> list[int]:
    """'0-31,64-95' → [0, 1, …, 31, 64, …, 95]"""
    out: list[int] = []
    for part in s.strip().split(","):
        lo, _, hi = part.partition("-")
        try:
            out.extend(range(int(lo), int(hi or lo) + 1))
        except ValueError:
            pass
    return out


_numa_nodes: list[tuple[int, str, list[int]]] | None = None


def numa_nodes() -> list[tuple[int, str, list[int]]]:
    """[(노드 번호, cpulist 문자열, CPU 번호들)] — 안 바뀌니 한 번만 읽는다. CPU 없는 노드는 뺀다."""
    global _numa_nodes
    if _numa_nodes is None:
        nodes = []
        for path in glob.glob("/sys/devices/system/node/node[0-9]*"):
            cpulist = _read_sysfs(path + "/cpulist")
            if cpulist:
                nodes.append((int(path.rsplit("node", 1)[1]), cpulist, parse_cpulist(cpulist)))
        _numa_nodes = sorted(nodes)
    return _numa_nodes


def gather_host() -> HostStat:
    total, ids, utils = get_cpu_utils()
    ram_used, ram_total = read_meminfo_gib()
    swap_used, swap_total = read_swapinfo_gib()
    load = ""
    try:
        with open("/proc/loadavg") as f:
            load = " ".join(f.read().split()[:3])
    except Exception:
        pass
    return HostStat(cpu_total=total, cpu_ids=ids, cpu_utils=utils,
                    ram_used=ram_used, ram_total=ram_total,
                    swap_used=swap_used, swap_total=swap_total,
                    loadavg=load, model=cpu_model())


def _cpu_summary(host: HostStat, console_width: int, load: bool = False) -> Text:
    """'CPU · RAM · SWAP (· load) (· 칩셋)' 한 줄 — 칩셋은 폭이 남을 때만."""
    # cell width 추정: 'CPU XXX.X%'=10, sep=5, 'RAM XXX.X/XXXG (XX.X%)'=22,
    # 'SWAP XXX.X/XXXG (XX.X%)'=23
    PANEL_CHROME = 6
    body = Text()
    body.append("CPU ", style="bold")
    body.append(pct_text(host.cpu_total, width=5))
    body.append("  ·  ", style="dim")
    body.append("RAM ", style="bold")
    body.append(mem_only_text(host.ram_used, host.ram_total))

    head_w = 10 + 5 + 22         # 현재까지 사용한 폭 (CPU + sep + RAM)

    # SWAP — CPU/RAM 처럼 항상 표시 (swap_total>0 일 때).
    # 매우 좁은 콘솔이면 rich wrap 으로 다음 줄로 넘어감 — 잘리지는 않음.
    swap_w = 5 + 5 + 22          # sep + 'SWAP ' (5) + mem 표기 ≈ 32
    if host.swap_total > 0:
        body.append("  ·  ", style="dim")
        body.append("SWAP ", style="bold")
        body.append(mem_only_text(host.swap_used, host.swap_total))
        head_w += swap_w

    if load and host.loadavg:
        body.append("  ·  ", style="dim")
        body.append("load ", style="bold")
        body.append(host.loadavg)
        head_w += 5 + 5 + len(host.loadavg)

    # 칩셋(model) 은 한 행에 같이 들어갈 폭 일 때만 (자동 생략)
    if console_width >= PANEL_CHROME + head_w + 5 + len(host.model):
        body.append("  ·  ", style="dim")
        body.append(host.model, style="dim italic")
    return body


def _cpu_cores(host: HostStat, console_width: int, strip: bool, by_node: bool) -> list:
    """코어별 사용률 줄들. by_node 면 NUMA 노드별로 묶고 노드 평균을 단다 (노드가 둘 이상일 때)."""
    by_id = dict(zip(host.cpu_ids, host.cpu_utils))
    groups = [(f"NUMA node{node}", cpulist, [c for c in cpus if c in by_id])
              for node, cpulist, cpus in (numa_nodes() if by_node else [])]
    groups = [g for g in groups if g[2]]
    if len(groups) < 2 or sum(len(g[2]) for g in groups) != len(by_id):
        groups = [("", "", host.cpu_ids)]        # 노드가 하나거나 정보가 안 맞으면 한 덩어리로

    label_w = len(str(max(host.cpu_ids, default=0)))
    # 한 컬럼 = 'cNN:NNN%' (label_w + 5) + Table.grid padding 양옆 (2) = label_w + 7
    cell_w = label_w + 7
    per_row = max(1, max(20, console_width - 6) // cell_w)

    lines: list = []
    for name, cpulist, ids in groups:
        utils = [by_id[c] for c in ids]
        if name:
            head = Text()
            head.append(name, style="bold")
            head.append(f"  ·  cpus {cpulist}  ·  avg ", style="dim")
            head.append(pct_text(sum(utils) / len(utils), width=1))
            lines.append(head)
        if strip:
            lines.append(cores_strip(utils))
        else:
            lines.append(cores_grid(utils, [False] * len(utils), per_row=per_row,
                                    label_width=label_w, ids=ids))
    return lines


def render_cpu(host: HostStat | None, console_width: int = 140, cores: str = "",
               detail: bool = False) -> Panel:
    """CPU 사용률 + 호스트 RAM + SWAP. cores 가 'grid'(셀)·'strip'(한 칸 막대) 이면 코어별도.
    detail(둘째 화면)이면 load average 를 더하고 코어를 NUMA 노드별로 묶는다."""
    host = host or HostStat()
    body = _cpu_summary(host, console_width, load=detail)
    if cores and host.cpu_ids:
        content = Group(body, Text(""), *_cpu_cores(host, console_width, strip=(cores == "strip"),
                                                    by_node=detail))
    else:
        content = body
    return Panel(content, title=f"CPU ({len(host.cpu_ids)} cores) + RAM + SWAP",
                 border_style="bright_magenta")


def render_host() -> Panel:
    mem_out = ""
    try:
        r = subprocess.run(["free", "-h"], capture_output=True, text=True, timeout=2)
        mem_out = r.stdout.strip()
    except Exception:
        mem_out = "(free 실패)"

    load = "?"
    try:
        with open("/proc/loadavg") as f:
            load = " ".join(f.read().strip().split()[:3])
    except Exception:
        pass

    swap_used = "?"
    try:
        for line in mem_out.splitlines():
            if line.startswith("Swap:"):
                parts = line.split()
                swap_used = f"{parts[2]}/{parts[1]}"
                break
    except Exception:
        pass

    body = Text()
    body.append(mem_out + "\n", style="white")
    body.append(f"loadavg: {load}", style="bold green")
    body.append("  ·  ", style="dim")
    body.append(f"swap: {swap_used}", style="cyan")
    return Panel(body, title="Host", border_style="green")


def _shorten_cmd(cmd: str, maxlen: int = 80) -> str:
    """긴 cmdline 단축 — 절대경로의 base name 만 남기고, 매우 길면 잘라냄."""
    # 경로 + 첫 인자만 추출 (furiosa-llm build ... 같은 패턴)
    parts = cmd.split()
    if not parts:
        return ""
    head = parts[0].rsplit("/", 1)[-1]
    # furiosa-llm 첫 인자(serve/build) 만 더
    rest_args = []
    skip_next = False
    for p in parts[1:]:
        if skip_next:
            skip_next = False
            continue
        if p.startswith("/") and len(p) > 30:
            rest_args.append(p.rsplit("/", 1)[-1])
        elif p.startswith("--log_dir") or p.startswith("--config_list") or p.startswith("--session"):
            skip_next = ("=" not in p)
            continue
        elif "=" in p and len(p) > 60:
            continue
        else:
            rest_args.append(p)
    short = " ".join([head] + rest_args)
    if len(short) > maxlen:
        short = short[:maxlen - 1] + "…"
    return short


def gather_ps(gpu_pids: set[int]) -> list[tuple[str, ...]] | None:
    """NPU·GPU 관련 호스트 프로세스 — (pid, user, %cpu, %mem, etime, cmd), CPU 높은 순 최대 8개.
    ps 가 실패하면 None."""
    rc, out, _ = run_cmd(["ps", "-eo", "ppid,pid,user,pcpu,pmem,etime,cmd", "--sort=-pcpu"],
                         timeout=2)
    if rc != 0:
        return None
    me = str(os.getpid())
    rows: list[tuple[str, ...]] = []
    for line in out.splitlines()[1:]:
        ppid, _, line = line.strip().partition(" ")
        if ppid == me:                      # 내가 띄운 smi·ps — 다른 수집 스레드와 같이 돌아서 잡힌다
            continue
        f = line.split(None, 5)
        if len(f) < 6:
            continue
        if not (f[0].isdigit() and int(f[0]) in gpu_pids):
            if not (any(k in line for k in ("furiosa-llm", "furiosa-smi"))
                    or re.search(r"python[0-9.]*\s.*(build|serve|orchestrator)", line)):
                continue
            if any(k in line for k in ("grep", "npu_top", "npu-top")):
                continue
        rows.append(tuple(f))
        if len(rows) >= 8:
            break
    return rows


def render_ps(rows: list[tuple[str, ...]] | None, gpu_mem: dict[int, float] | None = None) -> Panel:
    """rows 는 gather_ps() 결과. gpu_mem(pid → MiB)을 주면 GPU 메모리 열도 보인다."""
    body = Text(no_wrap=True, overflow="ellipsis")      # 긴 명령줄은 넘기지 않고 줄 끝에서 자른다
    kinds = "NPU-related" if gpu_mem is None else "NPU/GPU-related"
    body.append(f"Top {kinds} host processes:\n", style="bold cyan")
    head = f"{'PID':>7} {'USER':<8} {'%CPU':>6} {'%MEM':>6} {'ETIME':>10}"
    if gpu_mem is not None:
        head += f" {'GPU':>7}"
    body.append(head + "  CMD\n", style="dim")
    if rows is None:
        body.append("(ps 실패)", style="red")
        return Panel(body, title="Processes", border_style="yellow")
    for pid, user, pcpu, pmem, etime, cmd in rows:
        body.append(f"{pid:>7} ", style="bold yellow")
        body.append(f"{user:<8} ", style="white")
        body.append(f"{pcpu+'%':>6} ", style="red")
        body.append(f"{pmem+'%':>6} ", style="green")
        body.append(f"{etime:>10}", style="cyan")
        if gpu_mem is not None:
            mib = gpu_mem.get(int(pid))
            body.append(f" {fmt_mib(mib):>7}", style="green" if mib is not None else "dim")
        body.append("  " + _shorten_cmd(cmd, maxlen=110) + "\n", style="white")
    if not rows:
        body.append("(none)\n", style="dim")
    return Panel(body, title="Processes", border_style="yellow")


# ──────────────────────────── GPU 렌더 ────────────────────────────
def _gpu_temp_style(temp: float, margin: float | None) -> str:
    """margin = 스로틀 한계(T.Limit)까지 남은 온도. 없으면 절대 온도로 판정."""
    if margin is not None:
        return "red" if margin <= 0 else ("yellow" if margin <= 10 else "")
    return "red" if temp >= 85 else ("yellow" if temp >= 70 else "")


def _gpu_proc_label(p: GpuProc, maxlen: int) -> str:
    return _shorten_cmd(p.cmd, maxlen=maxlen) or p.name or str(p.pid)


def _gpu_proc_brief(p: GpuProc) -> str:
    """표 한 칸에 여럿 늘어놓을 짧은 이름 — 실행 파일 이름, 인터프리터면 스크립트 이름까지."""
    parts = p.cmd.split()
    if not parts:
        return p.name or str(p.pid)
    name = os.path.basename(parts[0])
    if re.fullmatch(r"python[0-9.]*|bash|sh|node", name):
        script = next((a for a in parts[1:] if not a.startswith("-")), "")
        if script:
            name += " " + os.path.basename(script)
    return name


def render_gpus(snap: Snapshot, console_width: int = 140) -> Table:
    """첫 화면의 GPU 표 — GPU 한 장에 한 줄."""
    failed = bool(snap.gpu_error) or not snap.gpus
    show_name = console_width >= 80 or failed       # 오류 문구는 Name 칸에 쓴다
    show_procs = console_width >= 120

    tbl = Table(expand=True, show_lines=True, header_style="bold cyan",
                border_style="bright_black", padding=(0, 0))
    tbl.add_column("Device", style="bold yellow", width=6)
    if show_name:
        tbl.add_column("Name", ratio=2, no_wrap=True, overflow="ellipsis")
    tbl.add_column("Util", width=6, justify="right")
    tbl.add_column("Memory", min_width=14)
    tbl.add_column("Temp", width=7, justify="right")
    tbl.add_column("Power", width=5, justify="right")
    if show_procs:
        tbl.add_column("Processes", ratio=3, no_wrap=True, overflow="ellipsis")

    if failed:
        msg = Text(snap.gpu_error or "(no GPU)", style="red" if snap.gpu_error else "dim")
        tbl.add_row("-", msg, "-", "-", "-", "-", *(["-"] if show_procs else []))
        return tbl

    na = Text("N/A", style="dim")
    for g in snap.gpus:
        util = g.ratio("utilization.gpu")
        temp = g.num("temperature.gpu")
        power = g.num("power.draw")
        row: list = [f"gpu{g.index}"]
        if show_name:
            row.append(g.name.removeprefix("NVIDIA "))
        row += [
            pct_text(util, width=5) if util is not None else na,
            mem_only_text(g.mem_used, g.mem_total),
            Text(f"{temp:.1f}°C", style=_gpu_temp_style(temp, g.num("temperature.gpu.tlimit")))
            if temp is not None else na,
            Text(f"{power:.0f}W", style="magenta") if power is not None else na,
        ]
        if show_procs:
            brief = Text()
            for p in (p for p in snap.gpu_procs if p.gpu == g.index):
                if brief.plain:
                    brief.append(", ", style="dim")
                brief.append(_gpu_proc_brief(p))
                brief.append(f" {fmt_mib(p.fb_mib)}", style="green")
            if not brief.plain:
                brief = Text(snap.gpu_procs_error or "-", style="red" if snap.gpu_procs_error else "dim")
            row.append(brief)
        tbl.add_row(*row)
    return tbl


def _gpu_detail_panel(g: GpuDev, procs: list[GpuProc], procs_error: str,
                      console_width: int, compact: bool = False) -> Panel:
    """둘째 화면의 GPU 한 장 — 막대 넷(사용률·메모리·전력·온도) + 세부 값 + 프로세스.
    compact 면 세부 값(클럭·PCIe·드라이버·UUID)을 뺀다."""
    bar_w = max(10, min(40, console_width // 4))
    na = Text("N/A", style="dim")
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold", no_wrap=True)
    grid.add_column()

    def bar_row(label: str, ratio: float, value: Text, extras: list[Text], style: str = "") -> None:
        row = bar_text(ratio, bar_w, style)
        row.append(" ")
        row.append(_join([value] + extras))
        grid.add_row(label, row)

    # 사용률 — GPU 전체와 엔진별
    util = g.ratio("utilization.gpu")
    engines = []
    for key, label in (("utilization.memory", "mem I/O"), ("utilization.encoder", "enc"),
                       ("utilization.decoder", "dec"), ("utilization.jpeg", "jpeg"),
                       ("utilization.ofa", "ofa")):
        v = g.ratio(key)
        if v is not None:
            engines.append(Text.assemble((f"{label} ", "dim"), pct_text(v, width=1)))
    bar_row("Util", util or 0.0, pct_text(util, width=5) if util is not None else na, engines)

    # 메모리
    extras = []
    reserved = g.num("memory.reserved")
    if reserved is not None:
        extras.append(Text(f"reserved {fmt_mib(reserved)}", style="dim"))
    bar_row("Memory", g.mem_used / g.mem_total if g.mem_total > 0 else 0.0,
            mem_only_text(g.mem_used, g.mem_total), extras)

    # 전력 — 한도 대비
    power, limit = g.num("power.draw"), g.num("power.limit")
    p_ratio = power / limit if power is not None and limit else 0.0
    value = na
    if power is not None:
        value = Text(f"{power:5.1f}" + (f"/{limit:.0f}" if limit else "") + "W", style="magenta")
        if limit:
            value.append(f" ({p_ratio * 100:4.1f}%)", style="dim")
    extras = [Text(f"{label} {v:.1f}W", style="dim")
              for key, label in (("power.draw.average", "avg"), ("power.draw.instant", "instant"))
              if (v := g.num(key)) is not None]
    bar_row("Power", p_ratio, value, extras)

    # 온도 — 스로틀 한계(T.Limit) 대비. margin 은 한계까지 남은 온도.
    temp, margin = g.num("temperature.gpu"), g.num("temperature.gpu.tlimit")
    t_ratio, value, t_style = 0.0, na, ""
    if temp is not None:
        full = temp + margin if margin is not None else 100.0
        t_ratio = temp / full if full > 0 else 1.0
        t_style = _gpu_temp_style(temp, margin)
        value = Text(f"{temp:5.1f}°C", style=t_style)
    extras = []
    if margin is not None and margin > 0:
        extras.append(Text(f"{margin:.0f}°C below T.Limit", style="dim"))
    elif margin is not None:
        extras.append(Text(f"{-margin:.0f}°C over T.Limit", style="bold red"))
    fan = g.num("fan.speed")
    extras.append(Text(f"fan {fan:.0f}%" if fan is not None else "fan N/A", style="dim"))
    if g.txt("pstate"):
        extras.append(Text(g.txt("pstate"), style="dim"))
    bar_row("Temp", t_ratio, value, extras, style=t_style or "green")

    # 클럭과 스로틀 사유 (스로틀 중이면 간략판에도 남긴다)
    clocks = []
    for label, cur_key, max_key in (("graphics", "clocks.current.graphics", "clocks.max.graphics"),
                                    ("memory", "clocks.current.memory", "clocks.max.memory")):
        cur, top = g.num(cur_key), g.num(max_key)
        if cur is not None:
            clocks.append(Text(f"{label} {cur:.0f}" + (f"/{top:.0f}" if top is not None else "") + " MHz"))
    events = g.clock_events
    if events is not None:
        ev = Text("throttle ", style="dim")
        if events:
            for i, (name, style) in enumerate(events):
                ev.append(("" if i == 0 else ", ") + name, style=style)
        else:
            ev.append("none", style="green")
        clocks.append(ev)
    if clocks and not (compact and not events):
        grid.add_row("Clocks", _join(clocks))

    # PCIe 링크 (유휴일 때는 드라이버가 세대를 낮추기도 한다)
    link = []
    gen = g.txt("pcie.link.gen.gpucurrent") or g.txt("pcie.link.gen.current")
    lanes = g.txt("pcie.link.width.current")
    if gen and lanes:
        s = f"Gen{gen} x{lanes}"
        if g.txt("pcie.link.gen.max") and g.txt("pcie.link.width.max"):
            s += f" (max Gen{g.txt('pcie.link.gen.max')} x{g.txt('pcie.link.width.max')})"
        link.append(Text(s))
    if g.txt("pci.bus_id"):
        link.append(Text(f"bus {g.txt('pci.bus_id')}", style="dim"))
    if link and not compact:
        grid.add_row("PCIe", _join(link))

    # 드라이버·모드·ECC
    info = []
    if g.txt("driver_version"):
        info.append(Text(g.txt("driver_version")))
    if g.txt("compute_mode"):
        info.append(Text(f"compute {g.txt('compute_mode')}", style="dim"))
    if g.txt("persistence_mode"):
        info.append(Text(f"persistence {g.txt('persistence_mode')}", style="dim"))
    ecc_ok, ecc_bad = (g.num("ecc.errors.corrected.volatile.total"),
                       g.num("ecc.errors.uncorrected.volatile.total"))
    if ecc_ok is not None or ecc_bad is not None:
        info.append(Text(f"ECC {ecc_ok or 0:.0f} corrected / {ecc_bad or 0:.0f} uncorrected",
                         style="bold red" if ecc_bad else "dim"))
    if info and not (compact and not ecc_bad):
        grid.add_row("Driver", _join(info))
    if g.txt("uuid") and not compact:
        grid.add_row("UUID", Text(g.txt("uuid"), style="dim"))

    # 이 GPU 를 쓰는 프로세스
    def pct(v: float | None) -> str:
        return "-" if v is None else f"{v:.0f}"

    lines = [Text(f"{'PID':>7} {'USER':<8} {'TYPE':<4} {'GPU-MEM':>8} {'SM%':>5} {'MEM%':>5} "
                  f"{'ENC%':>5} {'DEC%':>5}  CMD", style="dim")]
    for p in procs:
        line = Text()
        line.append(f"{p.pid:>7} ", style="bold yellow")
        line.append(f"{p.user:<8} ", style="white")
        line.append(f"{p.type:<4} ", style="cyan")
        line.append(f"{fmt_mib(p.fb_mib):>8} ", style="green")
        line.append(f"{pct(p.sm):>5} {pct(p.mem):>5} {pct(p.enc):>5} {pct(p.dec):>5}", style="red")
        line.append("  " + _gpu_proc_label(p, maxlen=110), style="white")
        lines.append(line)
    if procs_error:
        lines.append(Text(procs_error, style="red"))
    elif not procs:
        lines.append(Text("(none)", style="dim"))

    # 긴 명령줄은 넘기지 않고 줄 끝에서 자른다
    table = Text("\n", no_wrap=True, overflow="ellipsis").join(lines)
    return Panel(Group(grid, Text(""), table),
                 title=f"gpu{g.index}  ·  {g.name}", border_style="green")


def render_gpu_detail(snap: Snapshot, console_width: int = 140, compact: bool = False):
    """둘째 화면의 GPU 부분 — GPU 마다 패널 하나씩 세로로."""
    if snap.gpu_error or not snap.gpus:
        return Panel(Text(snap.gpu_error or "(no GPU)", style="red" if snap.gpu_error else "dim"),
                     title="GPU", border_style="green")
    return Group(*[
        _gpu_detail_panel(g, [p for p in snap.gpu_procs if p.gpu == g.index],
                          snap.gpu_procs_error, console_width, compact=compact)
        for g in snap.gpus
    ])


# ──────────────────────────── 화면 배치 ────────────────────────────
def _height(console: Console, renderable, width: int) -> int:
    """renderable 을 폭 width 로 그렸을 때의 줄 수 — 고정 높이 구획의 size 로 쓴다."""
    return len(console.render_lines(renderable, console.options.update_width(max(1, width)),
                                    pad=False))


def build_layout(snap: Snapshot, args: argparse.Namespace, *, console: Console,
                 pages: list[str], page: int = 0, title: str = "ntop",
                 keys_on: bool = False) -> Layout:
    width, height = console.size.width, console.size.height

    warn = ""
    if snap.error:
        warn = f"수집 오류: {snap.error}"
    elif not snap.ts:
        warn = "furiosa-smi 응답 대기 중"
    elif time.monotonic() - snap.ts > max(3.0, 5 * args.interval):
        warn = f"NPU 데이터 {time.monotonic() - snap.ts:.0f}초 전"

    # (이름, 내용, 높이) — 높이 None 은 남는 자리를 다 쓴다
    blocks: list[tuple[str, object, int | None]] = [
        ("header", render_header(snap.devs, title=title, pages=pages, page=page,
                                 keys_on=keys_on, width=width, warn=warn), 3),
    ]

    def fixed(name: str, renderable) -> None:
        blocks.append((name, renderable, _height(console, renderable, width)))

    if pages[page] == "Detail":
        # 다 안 들어가면 ① 코어를 한 칸 막대로 줄이고 ② 그래도 모자라면 GPU 세부 값을 뺀다
        for cores, compact in (("grid", False), ("strip", False), ("strip", True)):
            cpu = render_cpu(snap.host, width, cores=cores, detail=True) if args.cpu else None
            gpu = render_gpu_detail(snap, width, compact=compact) if args.gpu else None
            cpu_h = _height(console, cpu, width) if cpu else 0
            if 3 + cpu_h + (_height(console, gpu, width) if gpu else 0) <= height:
                break
        if cpu:
            blocks.append(("cpu", cpu, cpu_h))
        blocks.append(("gpu", gpu if gpu is not None else Text(""), None))
    else:
        if args.raw:
            blocks.append(("raw", Panel(Text(snap.raw_payload),
                                        title="furiosa-smi status/info (raw JSON)",
                                        border_style="cyan"), None))
        else:
            fixed("devices", Panel(render_devices(snap.devs, console_width=width),
                                   title="NPU Devices", border_style="cyan"))
        if args.cpu:
            # GPU 표가 있으면 요약 한 줄만 — 코어별은 둘째 화면에 있다.
            # GPU 가 없으면 예전처럼 넓은 콘솔(≥ 120칸)에서 코어 그리드까지.
            cores = "" if args.gpu or width < 120 else "grid"
            fixed("cpu", render_cpu(snap.host, width, cores=cores))
        if args.gpu:
            fixed("gpu", Panel(render_gpus(snap, console_width=width),
                               title="GPU Devices", border_style="green"))

        # 프로세스 패널 몫으로 남는 줄. 모자라면 NPU 표의 행 구분선부터 뺀다.
        PS_ROOM = 8                             # 테두리·머리 4줄 + 프로세스 4줄
        want = 0 if args.no_ps else PS_ROOM
        room = height - sum(size or 0 for _, _, size in blocks)
        if room < want and not args.raw:
            i = next(i for i, b in enumerate(blocks) if b[0] == "devices")
            dev = Panel(render_devices(snap.devs, console_width=width, compact=True),
                        title="NPU Devices", border_style="cyan")
            dev_h = _height(console, dev, width)
            room += blocks[i][2] - dev_h
            blocks[i] = ("devices", dev, dev_h)
        if not args.no_ps and room >= 5:        # 5줄 미만이면 프로세스가 한 줄도 안 보인다
            gpu_mem = {p.pid: p.fb_mib for p in snap.gpu_procs if p.fb_mib is not None} \
                if args.gpu else None
            blocks.append(("ps", render_ps(snap.ps_rows, gpu_mem), None))

    layout = Layout()
    layout.split(*[Layout(renderable, name=name, size=size) for name, renderable, size in blocks])
    return layout


# ──────────────────────────── 수집 스레드 ────────────────────────────
# nvidia-smi·ps 는 한 번에 CPU 를 30~45 ms 씩 쓴다. 갱신 간격마다 다 부르면 nctop 이 코어 하나의
# 1/3 을 먹으므로 덜 자주 부른다 (-i 가 이보다 길면 -i 를 따른다).
GPU_PERIOD = 1.0        # GPU 상태 — 드라이버의 사용률 표본 주기도 1/6 ~ 1초
PROCS_PERIOD = 2.0      # 프로세스 목록 (nvidia-smi pmon, ps)


def gather_raw() -> str:
    return (
        "=== status ===\n"
        + run_smi_text("status") + "\n\n"
        + "=== info ===\n"
        + run_smi_text("info") + "\n\n"
        + "=== ps ===\n"
        + run_smi_text("ps")
    )


class Poller(threading.Thread):
    """fn 을 period 초마다 불러 마지막 결과를 들고 있는다."""

    def __init__(self, name: str, fn, period: float, on_update=None) -> None:
        super().__init__(name=f"ntop-{name}", daemon=True)
        self.fn, self.period, self.on_update = fn, period, on_update
        self.value = None
        self.ts = 0.0                       # 마지막으로 fn 이 끝난 시각 (time.monotonic)
        self.error = ""                     # fn 이 던진 예외
        self.ready = threading.Event()      # 첫 수집이 끝나면 켜진다
        self._halt = threading.Event()

    def run(self) -> None:
        while not self._halt.is_set():
            t0 = time.monotonic()
            try:
                self.value, self.error = self.fn(), ""
            except Exception as e:          # 수집 버그로 스레드가 죽어 화면이 굳는 일은 없게
                self.error = f"{type(e).__name__}: {e}"
            self.ts = time.monotonic()
            self.ready.set()
            if self.on_update:
                self.on_update()
            self._halt.wait(max(0.0, self.period - (time.monotonic() - t0)))

    def stalled(self, now: float) -> float:
        """fn 이 오래 안 끝나고 있으면(죽지도 않는 smi 등) 멈춘 지 몇 초인지, 아니면 0."""
        age = now - self.ts
        return age if self.ts and age > max(5.0, 5 * self.period) else 0.0

    def stop(self) -> None:
        self._halt.set()


class Sources:
    """수집 종류마다 Poller 하나 — 그리는 쪽은 수집을 기다리지 않고, 한쪽 smi 가 멈춰도
    다른 패널은 제 주기로 갱신된다. snapshot() 이 각 Poller 의 마지막 결과를 하나로 모은다."""

    def __init__(self, args: argparse.Namespace, on_update) -> None:
        interval = max(args.interval, 0.1)
        # 화면은 NPU 수집이 끝날 때마다 다시 그린다 (on_update)
        self.pollers: dict[str, Poller] = {"npu": Poller("npu", gather, interval, on_update)}
        if args.raw:
            self.pollers["raw"] = Poller("raw", gather_raw, interval)
        if args.cpu:
            self.pollers["host"] = Poller("host", gather_host, interval)
        if args.gpu:
            self.pollers["gpu"] = Poller("gpu", gather_gpus, max(interval, GPU_PERIOD))
            self.pollers["gpu_procs"] = Poller("gpu_procs", gather_gpu_procs,
                                               max(interval, PROCS_PERIOD))
        if not args.no_ps:
            self.pollers["ps"] = Poller("ps", self._ps, max(interval, PROCS_PERIOD))

    def _ps(self) -> list[tuple[str, ...]] | None:
        procs: list[GpuProc] = []
        pmon = self.pollers.get("gpu_procs")
        if pmon is not None:
            pmon.ready.wait(4.0)            # 첫 바퀴에 GPU 프로세스가 빠지지 않게 pmon 을 기다린다
            procs = (pmon.value or ([], ""))[0]
        return gather_ps({p.pid for p in procs if "C" in p.type})

    def start(self) -> None:
        for p in self.pollers.values():
            p.start()

    def wait_ready(self) -> None:
        """첫 화면에 빈 표가 번쩍이지 않게 첫 수집을 기다린다. NPU 는 5초, 나머지는 0.5초 더."""
        self.pollers["npu"].ready.wait(5.0)
        deadline = time.monotonic() + 0.5
        for p in self.pollers.values():
            p.ready.wait(max(0.0, deadline - time.monotonic()))

    def stop(self) -> None:
        for p in self.pollers.values():
            p.stop()

    def snapshot(self) -> Snapshot:
        now = time.monotonic()
        snap = Snapshot()
        for name, p in self.pollers.items():
            if p.error and not snap.error:
                snap.error = f"{name}: {p.error}"

        def value(name: str, default):
            p = self.pollers.get(name)
            return default if p is None or p.value is None else p.value

        def smi(name: str) -> tuple[list, str]:
            """nvidia-smi 결과 (목록, 오류 문구). 아직 안 왔거나 오래 멈춰 있으면 그 사정을 오류로."""
            p = self.pollers[name]
            if p.stalled(now):
                return [], f"nvidia-smi 응답 없음 ({p.stalled(now):.0f}초째)"
            return value(name, ([], "nvidia-smi 응답 대기 중"))

        snap.devs, snap.ts = value("npu", []), self.pollers["npu"].ts
        snap.raw_payload = value("raw", "")
        snap.host = value("host", None)
        if "gpu" in self.pollers:
            snap.gpus, snap.gpu_error = smi("gpu")
            snap.gpu_procs, snap.gpu_procs_error = smi("gpu_procs")
        ps = self.pollers.get("ps")
        if ps is not None and ps.ready.is_set():
            snap.ps_rows = ps.value         # None = ps 실패
        else:
            snap.ps_rows = []
        return snap


# ──────────────────────────── 키 입력 ────────────────────────────
# CSI(ESC [ …)·SS3(ESC O …) 시퀀스의 끝 글자 → 키 이름
_ESC_KEYS = {"C": "right", "D": "left", "Z": "shift-tab"}
NEXT_KEYS = {"right", "l", "\t"}
PREV_KEYS = {"left", "h", "shift-tab"}
QUIT_KEYS = {"q", "Q", "ㅂ"}            # ㅂ = 한글 입력 상태에서 누른 q


def parse_keys(buf: str) -> tuple[list[str], str]:
    """터미널 입력 → (키 목록, 아직 덜 온 이스케이프 시퀀스).

    화살표는 터미널 모드에 따라 'ESC [ C' 로도 'ESC O C' 로도 온다. 모르는 시퀀스는 버린다.
    """
    keys: list[str] = []
    i, n = 0, len(buf)
    while i < n:
        if buf[i] != "\x1b":
            keys.append(buf[i])
            i += 1
        elif i + 1 >= n:
            return keys, buf[i:]
        elif buf[i + 1] == "[":             # CSI: 매개변수 뒤 0x40~0x7e 한 글자로 끝난다
            j = i + 2
            while j < n and not "\x40" <= buf[j] <= "\x7e":
                j += 1
            if j >= n:
                return keys, buf[i:]
            if buf[j] in _ESC_KEYS:
                keys.append(_ESC_KEYS[buf[j]])
            i = j + 1
        elif buf[i + 1] == "O":             # SS3
            if i + 2 >= n:
                return keys, buf[i:]
            if buf[i + 2] in _ESC_KEYS:
                keys.append(_ESC_KEYS[buf[i + 2]])
            i += 3
        else:                               # Alt+키 — 안 쓴다
            i += 2
    return keys, ""


class KeyReader:
    """stdin 을 cbreak(한 글자씩, 에코 없음)로 두고 키를 읽는다.

    stdin 이 터미널이 아니거나 배경 작업으로 떠 있으면 손대지 않는다 (fd 가 None).
    """

    def __init__(self) -> None:
        self.fd: int | None = None          # 읽을 fd — 입력이 끝나면 None 으로 바뀐다
        self._tty: int | None = None        # 설정을 되돌릴 fd
        self._saved = None
        self._pending = ""

    def _foreground(self, fd: int) -> bool:
        return os.isatty(fd) and os.tcgetpgrp(fd) == os.getpgrp()

    def __enter__(self) -> "KeyReader":
        try:
            fd = sys.stdin.fileno()
            if self._foreground(fd):
                self._saved = termios.tcgetattr(fd)
                tty.setcbreak(fd)
                self.fd = self._tty = fd
        except (OSError, ValueError, AttributeError, termios.error):
            self.fd = None
        return self

    def __exit__(self, *exc) -> None:
        if self._tty is not None and self._saved is not None:
            try:
                # TCSAFLUSH: 안 읽은 키가 셸 프롬프트로 새지 않게 버린다
                termios.tcsetattr(self._tty, termios.TCSAFLUSH, self._saved)
            except termios.error:
                pass

    def resume(self) -> None:
        """Ctrl+Z 뒤 fg 로 돌아오면 셸이 터미널을 줄 단위 입력으로 돌려놓은 상태 — 다시 cbreak 로."""
        try:
            if self._tty is not None and self._foreground(self._tty):
                tty.setcbreak(self._tty)
        except (OSError, termios.error):
            pass

    def read(self) -> list[str]:
        """지금 들어와 있는 입력을 키 목록으로. select 가 읽을 수 있다고 한 뒤에 부른다."""
        keys: list[str] = []
        while self.fd is not None:
            try:
                data = os.read(self.fd, 256)
            except OSError:
                data = b""
            if not data:                    # EOF·오류 — 더 읽지 않는다 (select 가 계속 깨우므로)
                self.fd = None
                break
            self._pending += data.decode("utf-8", errors="ignore")
            got, self._pending = parse_keys(self._pending)
            keys += got
            if not self._pending:
                break
            # 이스케이프 시퀀스가 덜 왔다 — 잠깐 더 기다리고, 안 오면 Esc 만 누른 것으로 보고 버린다
            if not select.select([self.fd], [], [], 0.05)[0]:
                self._pending = ""
                break
        return keys


# ──────────────────────────── 메인 ────────────────────────────
def main() -> None:
    # argv[0] 이 'nctop' 으로 호출되면 --cpu·--gpu 디폴트 ON, 타이틀도 'nctop'
    invoked_as_nctop = os.path.basename(sys.argv[0]).lower().startswith("nctop")
    default_title = "nctop" if invoked_as_nctop else "ntop"

    ap = argparse.ArgumentParser(
        description="htop-like NPU (and optional CPU/GPU) monitor for Furiosa RNGD",
        epilog="keys: right/left (or l/h, Tab/Shift+Tab, 1/2) switch page, q quits")
    ap.add_argument("-i", "--interval", type=float, default=0.5, help="refresh interval (s)")
    ap.add_argument("--no-ps", action="store_true", help="hide processes panel")
    ap.add_argument("--raw", action="store_true",
                    help="show raw JSON from furiosa-smi (debug)")
    ap.add_argument("--cpu", action="store_true", default=invoked_as_nctop,
                    help="also show CPU/RAM panel, with per-core usage on page 2 "
                         "(default ON when invoked as 'nctop')")
    ap.add_argument("--no-cpu", dest="cpu", action="store_false",
                    help="force-disable CPU panel (overrides nctop default)")
    ap.add_argument("--gpu", action="store_true", default=None,
                    help="also show NVIDIA GPU panel from nvidia-smi, with details on page 2 "
                         "(default ON when invoked as 'nctop' and nvidia-smi is installed)")
    ap.add_argument("--no-gpu", dest="gpu", action="store_false",
                    help="force-disable GPU panel (overrides nctop default)")
    ap.add_argument("-p", "--page", type=int, default=1,
                    help="page to start on: 1 = overview, 2 = CPU per-core + GPU detail")
    args = ap.parse_args()
    if args.gpu is None:
        args.gpu = invoked_as_nctop and shutil.which("nvidia-smi") is not None

    if not shutil.which("furiosa-smi"):
        print("❌ furiosa-smi 가 PATH 에 없습니다. Furiosa SDK 가 설치돼 있나요?", file=sys.stderr)
        sys.exit(1)

    pages = ["Overview"] + (["Detail"] if args.cpu or args.gpu else [])
    page = max(0, min(len(pages) - 1, args.page - 1))

    # 수집 스레드·시그널이 메인 루프의 select 를 깨우는 파이프
    wake_r, wake_w = os.pipe()
    os.set_blocking(wake_r, False)
    os.set_blocking(wake_w, False)

    def wake(*_) -> None:
        try:
            os.write(wake_w, b"\0")
        except OSError:
            pass                            # 파이프가 찼다 = 이미 깨울 일이 쌓여 있다

    resumed = threading.Event()

    def on_cont(*_) -> None:
        resumed.set()
        wake()

    def on_term(*_) -> None:
        raise KeyboardInterrupt             # Ctrl+C 와 같은 길로 나가 터미널을 되돌린다

    signal.signal(signal.SIGWINCH, wake)    # 창 크기가 바뀌면 바로 다시 그린다
    signal.signal(signal.SIGCONT, on_cont)
    signal.signal(signal.SIGTERM, on_term)
    signal.signal(signal.SIGHUP, on_term)

    console = Console()
    sources = Sources(args, wake)
    try:
        with KeyReader() as keys, Live(console=console, screen=True, auto_refresh=False) as live:
            sources.start()
            sources.wait_ready()
            while True:
                live.update(build_layout(sources.snapshot(), args, console=console, pages=pages,
                                         page=page, title=default_title,
                                         keys_on=keys.fd is not None), refresh=True)
                # 새 NPU 수집 결과·키·창 크기 변경을 기다린다. 아무 일 없어도 1초마다 다시 그린다.
                watch = [wake_r] if keys.fd is None else [wake_r, keys.fd]
                readable, _, _ = select.select(watch, [], [], 1.0)
                if wake_r in readable:
                    try:
                        os.read(wake_r, 4096)
                    except OSError:
                        pass
                if resumed.is_set():
                    resumed.clear()
                    keys.resume()
                if keys.fd is not None and keys.fd in readable:
                    for key in keys.read():
                        if key in QUIT_KEYS:
                            raise KeyboardInterrupt
                        if key in NEXT_KEYS:
                            page = min(page + 1, len(pages) - 1)
                        elif key in PREV_KEYS:
                            page = max(page - 1, 0)
                        elif len(key) == 1 and key in "123456789" and int(key) <= len(pages):
                            page = int(key) - 1
    except KeyboardInterrupt:
        pass
    finally:
        sources.stop()
    print(f"\n[{default_title}] bye.")


if __name__ == "__main__":
    main()
