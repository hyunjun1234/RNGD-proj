#!/usr/bin/env python3
"""npu_top.py — Furiosa RNGD NPU htop-style TUI 모니터 (옵션 C)

`furiosa-smi status --format json` 과 `furiosa-smi info --format json` 출력을 합쳐
htop 처럼 디바이스마다 메모리·8코어 사용률·온도·전력을 막대그래프로 보여줍니다.

사용:
    python3 npu_top.py
    python3 npu_top.py -i 0.5        # 0.5초 새로고침
    python3 npu_top.py --no-ps       # 프로세스 패널 끄기
    python3 npu_top.py --raw         # JSON 원본 표시 (디버그)

종료: Ctrl+C

의존:
    pip install rich
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime

try:
    from rich.align import Align
    from rich.console import Console
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


def _core_cell(i: int, u: float, busy_flag: bool, label_width: int) -> Text:
    """단일 코어 셀 'cNN:XX%' — Table.grid 의 cell 단위로 들어가 wrap 에서 안 깨짐."""
    t = Text()
    label_style = "bold cyan" if busy_flag else "dim"
    t.append(f"c{i:>{label_width}}:", style=label_style)
    val_style = "dim" if u < 0.005 else util_color(u)
    t.append(f"{u*100:3.0f}%", style=val_style)
    return t


def cores_grid(utils: list[float], busy: list[bool], per_row: int = 8,
               label_width: int = 0):
    """N개 코어를 per_row 컬럼 Table.grid 로 그림.
    각 셀이 Table.grid 의 cell 이라 rich wrap 에서 절대 안 끊김.
    NPU 표 안의 cell 에 들어가도 OK 하도록 expand=False 로 콘텐츠 폭만 차지."""
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
                row_cells.append(_core_cell(i, utils[i], busy[i], label_width))
        grid.add_row(*row_cells)
    return grid


# 하위 호환 — render_devices 가 Table.grid 도 cell 로 받음
def cores_text(utils, busy, per_row=8, label_width=0):
    return cores_grid(utils, busy, per_row=per_row, label_width=label_width)


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


def render_devices(devs: list[NpuDev], console_width: int = 140) -> Table:
    # per-core 컬럼 표시 여부 — 8코어 기준 2행 안에 들어갈 때만 (3행 이상이면 숨김)
    n_cores = len(devs[0].core_utils) if devs and devs[0].core_utils else 8
    label_w = len(str(max(n_cores - 1, 0)))
    per_row = cores_per_row(console_width, n_cores, label_width=label_w)
    show_percore = per_row * 2 >= n_cores       # 2행 이내일 때만 표시

    # padding=(0,0) 으로 컬럼 양 옆 공백 제거 → 좁은 콘솔에서 표가 안 잘리도록
    tbl = Table(expand=True, show_lines=True, header_style="bold cyan",
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


def render_header(devs: list[NpuDev], title: str = "ntop") -> Panel:
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

    summary = Text.assemble(
        (title, "bold bright_cyan"),
        ("  ·  ", "dim"),
        (now, "white"),
        ("  ·  ", "dim"),
        (f"{n_alive}/{len(devs)} alive", "green"),
        ("  ·  ", "dim"),
        ("NPU ", "bold"),
        (f"{total_util*100:5.1f}%", util_color_style),
        ("  ·  ", "dim"),
        ("MEM ", "bold"),
        (f"{mem_used:4.1f}/{mem_total:.0f}G", mem_color_style),
        ("  ·  ", "dim"),
        (f"{n_busy} busy", "yellow"),
        ("  ·  ", "dim"),
        (f"{total_pwr:.0f}W", "magenta"),
        ("  ·  ", "dim"),
        (f"avg {avg_temp:.1f}°C", "red" if avg_temp >= 70 else ""),
        ("  ·  ", "dim"),
        ("q/Ctrl+C: quit", "dim italic"),
    )
    return Panel(Align.center(summary), style="cyan", padding=(0, 1))


try:
    import psutil  # type: ignore
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


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


def get_cpu_utils() -> tuple[float, list[float]]:
    """(total_util_ratio, per_core_util_ratios). /proc/stat delta 기반."""
    cur = _read_proc_stat()
    out_total = 0.0
    per_core: list[float] = []
    if not cur or not _CPU_PREV:
        _CPU_PREV.update(cur)
        # 첫 호출이면 0 반환 (다음 tick부터 실측)
        n_cores = max((k for k in cur if k >= 0), default=-1) + 1
        return 0.0, [0.0] * n_cores
    for cpu_id, (busy, total) in cur.items():
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
    return out_total, per_core


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


def render_cpu(console_width: int = 140) -> Panel:
    """CPU 사용률 + 호스트 RAM + SWAP + (선택) per-core 그리드."""
    total, percore = get_cpu_utils()
    n = len(percore)
    ram_used, ram_total = read_meminfo_gib()
    swap_used, swap_total = read_swapinfo_gib()

    # CPU 모델
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

    # 상단 1행: CPU · RAM · SWAP · 칩셋 — 우측부터 폭에 맞춰 자동 생략
    # cell width 추정: 'CPU XXX.X%'=10, sep=5, 'RAM XXX.X/XXXG (XX.X%)'=22,
    # 'SWAP XXX.X/XXXG (XX.X%)'=23
    PANEL_CHROME = 6
    body = Text()
    body.append("CPU ", style="bold")
    body.append(pct_text(total, width=5))
    body.append("  ·  ", style="dim")
    body.append("RAM ", style="bold")
    body.append(mem_only_text(ram_used, ram_total))

    head_w = 10 + 5 + 22         # 현재까지 사용한 폭 (CPU + sep + RAM)

    # SWAP — CPU/RAM 처럼 항상 표시 (swap_total>0 일 때).
    # 매우 좁은 콘솔이면 rich wrap 으로 다음 줄로 넘어감 — 잘리지는 않음.
    swap_w = 5 + 5 + 22          # sep + 'SWAP ' (5) + mem 표기 ≈ 32
    if swap_total > 0:
        body.append("  ·  ", style="dim")
        body.append("SWAP ", style="bold")
        body.append(mem_only_text(swap_used, swap_total))
        head_w += swap_w

    # 칩셋(model) 은 한 행에 같이 들어갈 폭 일 때만 (자동 생략)
    if console_width >= PANEL_CHROME + head_w + 5 + len(model):
        body.append("  ·  ", style="dim")
        body.append(model, style="dim italic")

    # per-core 그리드 — 좁은 콘솔(< 120칸)에선 숨김
    show_percore = console_width >= 120
    if show_percore:
        label_w = len(str(max(n - 1, 0)))
        # 한 컬럼 = 'cNN:NNN%' (label_w + 5) + Table.grid padding 양옆 (2) = label_w + 7
        cell_w = label_w + 7
        avail = max(20, console_width - 6)
        per_row = max(1, avail // cell_w)
        grid = cores_grid(percore, [False] * n, per_row=per_row, label_width=label_w)
        from rich.console import Group
        content = Group(body, Text(""), grid)
    else:
        content = body
    return Panel(content, title=f"CPU ({n} cores) + RAM + SWAP",
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


def render_ps(smi_ps_raw: str) -> Panel:
    body = Text()
    body.append("Top NPU-related host processes:\n", style="bold cyan")
    body.append(f"{'PID':>7} {'USER':<8} {'%CPU':>6} {'%MEM':>6} {'ETIME':>10}  CMD\n",
                style="dim")
    try:
        r = subprocess.run(["ps", "-eo", "pid,user,pcpu,pmem,etime,cmd", "--sort=-pcpu"],
                           capture_output=True, text=True, timeout=2)
        n = 0
        for line in r.stdout.splitlines()[1:]:
            if not (any(k in line for k in ("furiosa-llm", "furiosa-smi"))
                    or re.search(r"python[0-9.]*\s.*(build|serve|orchestrator)", line)):
                continue
            if any(k in line for k in ("grep", "npu_top", "npu-top")):
                continue
            f = line.split(None, 5)
            if len(f) < 6:
                continue
            pid, user, pcpu, pmem, etime, cmd = f
            body.append(f"{pid:>7} ", style="bold yellow")
            body.append(f"{user:<8} ", style="white")
            body.append(f"{pcpu+'%':>6} ", style="red")
            body.append(f"{pmem+'%':>6} ", style="green")
            body.append(f"{etime:>10}  ", style="cyan")
            body.append(_shorten_cmd(cmd, maxlen=110) + "\n", style="white")
            n += 1
            if n >= 8:
                break
        if n == 0:
            body.append("(none)\n", style="dim")
    except Exception:
        body.append("(ps 실패)", style="red")
    return Panel(body, title="Processes", border_style="yellow")


def build_layout(devs: list[NpuDev], smi_ps_raw: str, show_ps: bool, raw_mode: bool,
                 raw_payload: str = "", *, show_cpu: bool = False,
                 console_width: int = 140, title: str = "ntop") -> Layout:
    layout = Layout()
    secs = [Layout(name="header", size=3)]
    if raw_mode:
        secs.append(Layout(name="raw"))
    else:
        # 디바이스 수 + per-core 줄바꿈 가능성 고려.
        # per-core 가 2행 안에 안 들어가면(즉 3행 이상이면) 컬럼 자체를 숨김 → Util(avg) 만.
        n_cores = len(devs[0].core_utils) if devs and devs[0].core_utils else 8
        label_w = len(str(max(n_cores - 1, 0)))
        per_row = cores_per_row(console_width, n_cores, label_width=label_w)
        show_percore = per_row * 2 >= n_cores
        if show_percore:
            rows_per_dev = -(-n_cores // per_row)   # ceil (1 또는 2)
        else:
            rows_per_dev = 1                         # per-core 컬럼 숨김
        # show_lines=True 라 행 사이 구분선이 들어가서 +1 더
        dev_size = max(6, 4 + len(devs) * (rows_per_dev + 1))
        secs.append(Layout(name="devices", size=dev_size))
    if show_cpu:
        # CPU 패널: 좁은 콘솔이면 한 행만(헤더), 넓으면 per-core 그리드까지
        if console_width >= 120:
            n_cpu = max(1, (psutil.cpu_count(logical=True) if _HAS_PSUTIL else os.cpu_count() or 1))
            label_w = len(str(max(n_cpu - 1, 0)))
            cell_w = 1 + label_w + 1 + 3 + 2
            avail = max(20, console_width - 6)
            per_row_cpu = max(1, avail // cell_w)
            cpu_rows = -(-n_cpu // per_row_cpu)
            # 헤더 1줄 + 빈줄 1 + per-core N줄 + 패널 테두리 2줄
            secs.append(Layout(name="cpu", size=cpu_rows + 4))
        else:
            # 헤더 — 매우 좁은 콘솔이면 CPU/RAM/SWAP 이 한 줄에 안 들어가서 wrap 될 수 있음.
            # 폭이 70 미만이면 헤더 2~3줄로 잡고, 그 이상이면 1줄.
            head_lines = 3 if console_width < 70 else (2 if console_width < 95 else 1)
            secs.append(Layout(name="cpu", size=head_lines + 2))
    if show_ps:
        secs.append(Layout(name="ps"))
    layout.split(*secs)

    layout["header"].update(render_header(devs, title=title))
    if raw_mode:
        layout["raw"].update(Panel(Text(raw_payload), title="furiosa-smi status/info (raw JSON)",
                                    border_style="cyan"))
    else:
        layout["devices"].update(Panel(render_devices(devs, console_width=console_width),
                                        title="NPU Devices", border_style="cyan"))
    if show_cpu:
        layout["cpu"].update(render_cpu(console_width=console_width))
    if show_ps:
        layout["ps"].update(render_ps(smi_ps_raw))
    return layout


# ──────────────────────────── 메인 ────────────────────────────
def main() -> None:
    # argv[0] 이 'nctop' 으로 호출되면 --cpu 디폴트 ON, 타이틀도 'nctop'
    invoked_as_nctop = os.path.basename(sys.argv[0]).lower().startswith("nctop")
    default_title = "nctop" if invoked_as_nctop else "ntop"

    ap = argparse.ArgumentParser(description="htop-like NPU (and optional CPU) monitor for Furiosa RNGD")
    ap.add_argument("-i", "--interval", type=float, default=0.5, help="refresh interval (s)")
    ap.add_argument("--no-ps", action="store_true", help="hide processes panel")
    ap.add_argument("--raw", action="store_true",
                    help="show raw JSON from furiosa-smi (debug)")
    ap.add_argument("--cpu", action="store_true", default=invoked_as_nctop,
                    help="also show CPU per-core usage panel (default ON when invoked as 'nctop')")
    ap.add_argument("--no-cpu", dest="cpu", action="store_false",
                    help="force-disable CPU panel (overrides nctop default)")
    args = ap.parse_args()

    if not shutil.which("furiosa-smi"):
        print("❌ furiosa-smi 가 PATH 에 없습니다. Furiosa SDK 가 설치돼 있나요?", file=sys.stderr)
        sys.exit(1)

    console = Console()
    refresh_hz = max(1, int(1 / max(args.interval, 0.1)))
    # CPU delta 가 의미있으려면 한 번 read 해서 baseline 잡아두기
    if args.cpu:
        _read_proc_stat()  # populate _CPU_PREV via side effect

    try:
        with Live(console=console, screen=True, refresh_per_second=refresh_hz) as live:
            while True:
                devs = gather()
                smi_ps = run_smi_text("ps")
                raw_payload = ""
                if args.raw:
                    raw_payload = (
                        "=== status ===\n"
                        + run_smi_text("status") + "\n\n"
                        + "=== info ===\n"
                        + run_smi_text("info") + "\n\n"
                        + "=== ps ===\n"
                        + smi_ps
                    )
                live.update(build_layout(
                    devs, smi_ps,
                    show_ps=not args.no_ps,
                    raw_mode=args.raw,
                    raw_payload=raw_payload,
                    show_cpu=args.cpu,
                    console_width=console.size.width,
                    title=default_title,
                ))
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print(f"\n[{default_title}] bye.")


if __name__ == "__main__":
    main()
