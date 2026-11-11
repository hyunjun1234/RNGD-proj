#!/usr/bin/env python3
"""ntop.py 단위·합성 시험 (실제 smi 를 부르지 않는다).

사용: python3 test_ntop.py [-v]
"""
import argparse
import io
import os
import pty
import sys
import time
import types
import unittest

# ntop.py 는 저장소 맨 위(이 파일에서 두 단계 위)에 있다. 다른 사본을 시험하려면 NTOP_DIR 로 폴더를 준다.
sys.path.insert(0, os.environ.get("NTOP_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
import ntop
from rich.console import Console

FIELDS = ntop.GPU_FIELDS


def gpu_line(index=0, name="NVIDIA RTX PRO 6000 Blackwell Server Edition", **over) -> str:
    """nvidia-smi --query-gpu csv 한 줄을 만든다 (필드 순서는 GPU_FIELDS)."""
    vals = {
        "index": str(index), "uuid": f"GPU-0000-{index}", "pci.bus_id": f"00000000:3{index}:00.0",
        "driver_version": "595.99.02",
        "utilization.gpu": "0", "utilization.memory": "0", "utilization.encoder": "0",
        "utilization.decoder": "0", "utilization.jpeg": "0", "utilization.ofa": "0",
        "memory.used": "39564", "memory.total": "97887", "memory.reserved": "636",
        "temperature.gpu": "36", "temperature.gpu.tlimit": "49", "fan.speed": "[N/A]", "pstate": "P0",
        "power.draw": "89.50", "power.draw.average": "89.50", "power.draw.instant": "89.99",
        "power.limit": "600.00",
        "clocks.current.graphics": "2317", "clocks.max.graphics": "2430",
        "clocks.current.memory": "12481", "clocks.max.memory": "12481",
        "pcie.link.gen.gpucurrent": "5", "pcie.link.gen.current": "5", "pcie.link.gen.max": "5",
        "pcie.link.width.current": "16", "pcie.link.width.max": "16",
        "compute_mode": "Default", "persistence_mode": "Disabled",
        "ecc.errors.corrected.volatile.total": "0", "ecc.errors.uncorrected.volatile.total": "0",
        "clocks_event_reasons.active": "0x0000000000000000",
        "name": name,
    }
    vals.update({k.replace("__", "."): v for k, v in over.items()})
    return ", ".join(vals[f] for f in FIELDS)


PMON = """# gpu         pid   type     sm    mem    enc    dec    jpg    ofa     fb   ccpm    command
# Idx           #    C/G      %      %      %      %      %      %     MB     MB    name
    0       3139     G      -      -      -      -      -      -      4      0    Xorg
    0     950487     C     87     41      -      -      -      -  39542      0    VLLM::EngineCor
    1          -     -      -      -      -      -      -      -      -      -    -
"""

PMON_OLD = """# gpu        pid  type    sm   mem   enc   dec   fb   command
# Idx          #   C/G     %     %     %     %   MB   name
    0      12345     C    55    20     -     -  1024   python
    0      12346   C+G     3     1     0     0   200   my app name
"""


def npu_devs(n=4, busy=False):
    return [ntop.NpuDev(name=f"npu{i}", arch="RNGD", liveness="alive", mem_used=38.2, mem_total=47.5,
                        mem_ratio=0.8, core_utils=[0.9 if busy else 0.0] * 8, core_busy=[busy] * 8,
                        temp_c=35.0 + i, power_w=40.0) for i in range(n)]


def host(n=128, numa=True, hot=()):
    utils = [0.0] * n
    for c in hot:
        utils[c] = 1.0
    return ntop.HostStat(cpu_total=0.012, cpu_ids=list(range(n)), cpu_utils=utils,
                         ram_used=50.5, ram_total=125.3, swap_used=0.0, swap_total=8.0,
                         loadavg="1.39 1.23 1.25", model="Intel(R) Xeon(R) 6530P")


def snapshot(gpus=1, gpu_over=None, procs=PMON, **kw) -> ntop.Snapshot:
    lines = "\n".join(gpu_line(i, **(gpu_over or {})) for i in range(gpus))
    s = ntop.Snapshot(ts=time.monotonic(), devs=npu_devs(), host=host(),
                      gpus=ntop.parse_gpu_csv(lines, FIELDS),
                      gpu_procs=ntop.parse_pmon(procs) if procs else [],
                      ps_rows=[("444724", "jun", "101", "27.7", "10:59:14",
                                "python3 /x/furiosa-llm serve furiosa-ai/gpt-oss-20b --served-model-name a --devices npu:0,npu:1"),
                               ("950487", "jun", "4.5", "2.4", "49:49", "VLLM::EngineCore")])
    for p in s.gpu_procs:
        p.user, p.cmd = "jun", {950487: "VLLM::EngineCore", 3139: "/usr/lib/xorg/Xorg vt1 -displayfd 3"}.get(p.pid, "")
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def args(**kw) -> argparse.Namespace:
    base = dict(interval=0.5, no_ps=False, raw=False, cpu=True, gpu=True, page=1)
    base.update(kw)
    return argparse.Namespace(**base)


def render(snap, a=None, w=160, h=45, page=0, pages=None, keys_on=True) -> list[str]:
    """build_layout 을 w x h 콘솔에 그려 줄 목록으로."""
    a = a or args()
    pages = pages or (["Overview"] + (["Detail"] if a.cpu or a.gpu else []))
    console = Console(width=w, height=h, file=io.StringIO(), force_terminal=True,
                      color_system=None, legacy_windows=False)
    layout = ntop.build_layout(snap, a, console=console, pages=pages, page=page,
                               title="nctop", keys_on=keys_on)
    console.print(layout, end="")
    out = console.file.getvalue()
    return (out[:-1] if out.endswith("\n") else out).split("\n")


class NumaPatch:
    """numa_nodes() 를 시험 값으로 바꿔 끼운다."""

    def __init__(self, nodes):
        self.nodes = nodes

    def __enter__(self):
        self.saved = ntop._numa_nodes
        ntop._numa_nodes = self.nodes

    def __exit__(self, *a):
        ntop._numa_nodes = self.saved


NUMA2 = [(0, "0-31,64-95", ntop.parse_cpulist("0-31,64-95")),
         (1, "32-63,96-127", ntop.parse_cpulist("32-63,96-127"))]


class ParseKeys(unittest.TestCase):
    def test_arrows_csi(self):
        self.assertEqual(ntop.parse_keys("\x1b[C"), (["right"], ""))
        self.assertEqual(ntop.parse_keys("\x1b[D"), (["left"], ""))

    def test_arrows_ss3(self):
        self.assertEqual(ntop.parse_keys("\x1bOC\x1bOD"), (["right", "left"], ""))

    def test_modified_arrows(self):
        self.assertEqual(ntop.parse_keys("\x1b[1;5C\x1b[1;2D"), (["right", "left"], ""))

    def test_shift_tab(self):
        self.assertEqual(ntop.parse_keys("\x1b[Z"), (["shift-tab"], ""))

    def test_plain(self):
        self.assertEqual(ntop.parse_keys("q1\tl"), (["q", "1", "\t", "l"], ""))

    def test_unknown_sequences_dropped(self):
        # 위/아래, PageUp, F5, Home
        self.assertEqual(ntop.parse_keys("\x1b[A\x1b[B\x1b[5~\x1b[15~\x1b[H"), ([], ""))
        self.assertEqual(ntop.parse_keys("\x1bOP"), ([], ""))      # F1

    def test_alt_key_ignored(self):
        self.assertEqual(ntop.parse_keys("\x1bq"), ([], ""))       # Alt+q 는 종료가 아니다

    def test_partial(self):
        self.assertEqual(ntop.parse_keys("\x1b"), ([], "\x1b"))
        self.assertEqual(ntop.parse_keys("\x1b["), ([], "\x1b["))
        self.assertEqual(ntop.parse_keys("\x1b[1;"), ([], "\x1b[1;"))
        self.assertEqual(ntop.parse_keys("\x1bO"), ([], "\x1bO"))
        self.assertEqual(ntop.parse_keys("q\x1b[C\x1b["), (["q", "right"], "\x1b["))

    def test_mixed_burst(self):
        keys, rest = ntop.parse_keys("\x1b[C" * 50 + "\x1b[D" * 49 + "q")
        self.assertEqual(keys.count("right"), 50)
        self.assertEqual(keys.count("left"), 49)
        self.assertEqual(keys[-1], "q")
        self.assertEqual(rest, "")

    def test_hangul_q(self):
        self.assertIn("ㅂ", ntop.QUIT_KEYS)
        self.assertEqual(ntop.parse_keys("ㅂ"), (["ㅂ"], ""))


class KeyReaderPty(unittest.TestCase):
    """실제 pty 로 KeyReader.read 를 돌려 본다 (cbreak 설정은 건너뛰고 읽기만)."""

    def setUp(self):
        self.master, self.slave = pty.openpty()
        self.kr = ntop.KeyReader()
        self.kr.fd = self.slave

    def tearDown(self):
        for fd in (self.master, self.slave):
            try:
                os.close(fd)
            except OSError:
                pass

    def test_split_sequence_joined(self):
        import threading
        import tty
        tty.setraw(self.slave)
        os.write(self.master, b"\x1b")
        threading.Timer(0.01, lambda: os.write(self.master, b"[C")).start()
        self.assertEqual(self.kr.read(), ["right"])

    def test_lone_esc_dropped_then_q(self):
        import tty
        tty.setraw(self.slave)
        os.write(self.master, b"\x1b")
        t0 = time.monotonic()
        self.assertEqual(self.kr.read(), [])
        self.assertLess(time.monotonic() - t0, 0.5)
        self.assertEqual(self.kr._pending, "")
        os.write(self.master, b"q")
        self.assertEqual(self.kr.read(), ["q"])

    def test_eof_disables(self):
        r, w = os.pipe()
        os.close(w)
        self.kr.fd = r
        self.assertEqual(self.kr.read(), [])
        self.assertIsNone(self.kr.fd)
        os.close(r)

    def test_utf8_hangul(self):
        import tty
        tty.setraw(self.slave)
        os.write(self.master, "ㅂ".encode())
        self.assertEqual(self.kr.read(), ["ㅂ"])


class ParseGpu(unittest.TestCase):
    def test_basic(self):
        (g,) = ntop.parse_gpu_csv(gpu_line(), FIELDS)
        self.assertEqual(g.index, 0)
        self.assertEqual(g.name, "NVIDIA RTX PRO 6000 Blackwell Server Edition")
        self.assertAlmostEqual(g.mem_used, 39564 / 1024)
        self.assertAlmostEqual(g.mem_total, 97887 / 1024)
        self.assertEqual(g.ratio("utilization.gpu"), 0.0)
        self.assertIsNone(g.num("fan.speed"))           # [N/A]
        self.assertEqual(g.txt("fan.speed"), "")
        self.assertEqual(g.txt("pstate"), "P0")
        self.assertEqual(g.clock_events, [])

    def test_name_with_comma(self):
        (g,) = ntop.parse_gpu_csv(gpu_line(name="Weird, Name, Inc"), FIELDS)
        self.assertEqual(g.name, "Weird, Name, Inc")
        self.assertEqual(g.txt("pstate"), "P0")

    def test_na_values(self):
        (g,) = ntop.parse_gpu_csv(gpu_line(utilization__gpu="[N/A]", power__draw="N/A",
                                           temperature__gpu="[Unknown Error]",
                                           temperature__gpu__tlimit="N/A",
                                           memory__used="[N/A]", memory__total="[N/A]"), FIELDS)
        self.assertIsNone(g.ratio("utilization.gpu"))
        self.assertIsNone(g.num("power.draw"))
        self.assertIsNone(g.num("temperature.gpu"))
        self.assertEqual(g.mem_used, 0.0)
        self.assertEqual(g.mem_total, 0.0)

    def test_clock_events(self):
        (g,) = ntop.parse_gpu_csv(gpu_line(clocks_event_reasons__active="0x0000000000000044"), FIELDS)
        self.assertEqual([n for n, _ in g.clock_events], ["sw power cap", "hw thermal"])
        (g,) = ntop.parse_gpu_csv(gpu_line(clocks_event_reasons__active="[N/A]"), FIELDS)
        self.assertIsNone(g.clock_events)

    def test_short_or_garbage_lines_skipped(self):
        self.assertEqual(ntop.parse_gpu_csv("No devices were found\n\n", FIELDS), [])

    def test_multi(self):
        gs = ntop.parse_gpu_csv("\n".join(gpu_line(i) for i in range(8)), FIELDS)
        self.assertEqual([g.index for g in gs], list(range(8)))


class GatherGpus(unittest.TestCase):
    """드라이버가 모르는 필드를 빼 가며 다시 묻는 길."""

    def setUp(self):
        self.saved_run, self.saved_fields = ntop.run_cmd, list(ntop._gpu_fields)

    def tearDown(self):
        ntop.run_cmd = self.saved_run
        ntop._gpu_fields[:] = self.saved_fields

    def test_drops_unknown_fields(self):
        unknown = {"utilization.jpeg", "utilization.ofa", "temperature.gpu.tlimit",
                   "clocks_event_reasons.active", "pcie.link.gen.gpucurrent"}
        calls = []

        def fake(argv, timeout=3.0):
            fields = argv[1].split("=", 1)[1].split(",")
            calls.append(fields)
            for f in fields:
                if f in unknown:
                    return 2, f'Field "{f}" is not a valid field to query.\n\n', ""
            full = dict(zip(FIELDS, [v.strip() for v in gpu_line().split(",", len(FIELDS) - 1)]))
            return 0, ", ".join(full[f] for f in fields) + "\n", ""

        ntop.run_cmd = fake
        gpus, err = ntop.gather_gpus()
        self.assertEqual(err, "")
        self.assertEqual(len(gpus), 1)
        self.assertEqual(len(calls), len(unknown) + 1)
        g = gpus[0]
        self.assertIsNone(g.num("utilization.jpeg"))
        self.assertIsNone(g.clock_events)
        self.assertEqual(g.name, "NVIDIA RTX PRO 6000 Blackwell Server Edition")
        self.assertFalse(unknown & set(ntop._gpu_fields))
        # 다음 호출은 한 번에 된다
        calls.clear()
        ntop.gather_gpus()
        self.assertEqual(len(calls), 1)
        # 줄어든 필드로도 두 화면이 그려진다
        snap = snapshot()
        snap.gpus = gpus
        with NumaPatch(NUMA2):
            render(snap, page=0)
            out = "\n".join(render(snap, page=1))
        self.assertIn("Gen5 x16", out)       # gpucurrent 가 없어도 pcie.link.gen.current 로

    def test_driver_down(self):
        ntop.run_cmd = lambda argv, timeout=3.0: (
            9, "NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver. "
               "Make sure that the latest NVIDIA driver is installed and running.\n\n", "")
        gpus, err = ntop.gather_gpus()
        self.assertEqual(gpus, [])
        self.assertTrue(err.startswith("NVIDIA-SMI has failed"))

    def test_timeout_and_missing(self):
        ntop.run_cmd = self.saved_run
        rc, out, err = ntop.run_cmd(["sleep", "5"], timeout=0.2)
        self.assertEqual(rc, -1)
        self.assertIn("응답 없음", err)
        rc, out, err = ntop.run_cmd(["/nonexistent/nvidia-smi"])
        self.assertEqual(rc, -1)
        self.assertIn("실행 실패", err)

    def test_invalid_field_loop_terminates(self):
        # 모든 필드를 모른다고 해도 끝난다
        ntop.run_cmd = lambda argv, timeout=3.0: (
            2, 'Field "%s" is not a valid field to query.\n' % argv[1].split("=", 1)[1].split(",")[0], "")
        gpus, err = ntop.gather_gpus()
        self.assertEqual(gpus, [])
        self.assertIn("not a valid field", err)


class ParsePmon(unittest.TestCase):
    def test_new_format(self):
        procs = ntop.parse_pmon(PMON)
        self.assertEqual([(p.gpu, p.pid, p.type) for p in procs], [(0, 3139, "G"), (0, 950487, "C")])
        vllm = procs[1]
        self.assertEqual((vllm.sm, vllm.mem, vllm.enc, vllm.fb_mib), (87.0, 41.0, None, 39542.0))
        self.assertEqual(vllm.name, "VLLM::EngineCor")
        self.assertEqual((procs[0].sm, procs[0].fb_mib), (None, 4.0))

    def test_old_format_and_spaces_in_name(self):
        procs = ntop.parse_pmon(PMON_OLD)
        self.assertEqual([(p.pid, p.type, p.fb_mib, p.name) for p in procs],
                         [(12345, "C", 1024.0, "python"), (12346, "C+G", 200.0, "my app name")])
        self.assertEqual(procs[1].enc, 0.0)

    def test_empty_and_garbage(self):
        self.assertEqual(ntop.parse_pmon(""), [])
        self.assertEqual(ntop.parse_pmon("garbage line without header\n"), [])
        self.assertEqual(ntop.parse_pmon("# gpu pid type sm mem enc dec fb command\n"), [])


class Misc(unittest.TestCase):
    def test_parse_cpulist(self):
        self.assertEqual(ntop.parse_cpulist("0-3,8,10-11\n"), [0, 1, 2, 3, 8, 10, 11])
        self.assertEqual(ntop.parse_cpulist(""), [])
        self.assertEqual(ntop.parse_cpulist("5"), [5])

    def test_fmt_mib(self):
        self.assertEqual(ntop.fmt_mib(39542), "38.6G")
        self.assertEqual(ntop.fmt_mib(4), "4M")
        self.assertEqual(ntop.fmt_mib(1023.6), "1024M")
        self.assertEqual(ntop.fmt_mib(1024), "1.0G")
        self.assertEqual(ntop.fmt_mib(None), "-")

    def test_flow_breaks_only_between_parts(self):
        from rich.text import Text
        parts = [Text("aaaa bbbb"), Text("cc"), Text(""), Text("dddd eeee"), Text("f")]
        self.assertEqual(ntop._flow(parts, 100).plain, "aaaa bbbb  ·  cc  ·  dddd eeee  ·  f")
        self.assertEqual(ntop._flow(parts, 20).plain, "aaaa bbbb  ·  cc\ndddd eeee  ·  f")
        self.assertEqual(ntop._flow(parts, 9).plain, "aaaa bbbb\ncc\ndddd eeee\nf")
        self.assertEqual(ntop._flow(parts, 3).plain, "aaaa bbbb\ncc\ndddd eeee\nf")    # 조각이 폭보다 길어도 조각 안에서는 안 끊는다
        self.assertEqual(ntop._flow([], 10).plain, "")

    def test_clock_events_unknown_bits(self):
        (g,) = ntop.parse_gpu_csv(gpu_line(clocks_event_reasons__active="0x0000000000000200"), FIELDS)
        self.assertEqual([n for n, _ in g.clock_events], ["board limit"])
        (g,) = ntop.parse_gpu_csv(gpu_line(clocks_event_reasons__active="0x0000000000001404"), FIELDS)
        self.assertEqual([n for n, _ in g.clock_events], ["sw power cap", "reliability", "other 0x1000"])
        with NumaPatch(NUMA2):
            out = "\n".join(render(snapshot(gpu_over=dict(clocks_event_reasons__active="0x0000000000001000")), page=1))
        self.assertIn("throttle other 0x1000", out)
        self.assertNotIn("throttle none", out)

    def test_in_foreground_is_bool(self):
        self.assertIn(ntop.in_foreground(), (True, False))

    def test_bar(self):
        self.assertEqual(ntop.bar_text(0.5, 10).plain, "█████░░░░░")
        self.assertEqual(ntop.bar_text(-1, 4).plain, "░░░░")
        self.assertEqual(ntop.bar_text(7, 4).plain, "████")

    def test_proc_brief(self):
        P = ntop.GpuProc
        self.assertEqual(ntop._gpu_proc_brief(P(pid=1, cmd="VLLM::EngineCore")), "VLLM::EngineCore")
        self.assertEqual(ntop._gpu_proc_brief(P(pid=1, cmd="/usr/lib/xorg/Xorg vt1 -displayfd 3")), "Xorg")
        self.assertEqual(ntop._gpu_proc_brief(P(pid=1, cmd="/venv/bin/python3.12 -u /work/train.py --epochs 3")),
                         "python3.12 train.py")
        self.assertEqual(ntop._gpu_proc_brief(P(pid=7, cmd="", name="gone")), "gone")
        self.assertEqual(ntop._gpu_proc_brief(P(pid=7)), "7")

    def test_cpu_utils_ids(self):
        saved_read, saved_prev = ntop._read_proc_stat, dict(ntop._CPU_PREV)
        try:
            ntop._CPU_PREV.clear()
            # cpu1 이 꺼져 있어 번호가 건너뛴 기계
            ntop._read_proc_stat = lambda: {-1: (100, 1000), 0: (10, 100), 2: (50, 100), 3: (0, 100)}
            total, ids, utils = ntop.get_cpu_utils()
            self.assertEqual((total, ids, utils), (0.0, [0, 2, 3], [0.0, 0.0, 0.0]))
            ntop._read_proc_stat = lambda: {-1: (200, 2000), 0: (10, 200), 2: (150, 200), 3: (50, 200)}
            total, ids, utils = ntop.get_cpu_utils()
            self.assertAlmostEqual(total, 0.1)
            self.assertEqual(ids, [0, 2, 3])
            self.assertEqual(utils, [0.0, 1.0, 0.5])
        finally:
            ntop._read_proc_stat = saved_read
            ntop._CPU_PREV.clear()
            ntop._CPU_PREV.update(saved_prev)


class RunCmd(unittest.TestCase):
    """하위 프로세스: 시간 초과, 안 죽는 프로세스, 끝낼 때 정리."""

    def tearDown(self):
        for p in list(ntop._running) + list(ntop._stuck.values()):
            try:
                p.kill()
                p.wait(2)
            except Exception:
                pass
        ntop._running.clear()
        ntop._stuck.clear()
        ntop._closing = False

    def test_ok_and_stdin_is_devnull(self):
        rc, out, err = ntop.run_cmd(["sh", "-c", "readlink /proc/$$/fd/0; echo OUT; echo ERR >&2; exit 3"])
        self.assertEqual((rc, err.strip()), (3, "ERR"))
        self.assertEqual(out.split(), ["/dev/null", "OUT"])
        self.assertEqual(ntop._running, set())

    def test_timeout_kills_and_reaps(self):
        t0 = time.monotonic()
        rc, out, err = ntop.run_cmd(["sleep", "30"], timeout=0.3)
        self.assertLess(time.monotonic() - t0, 2.0)
        self.assertEqual(rc, -1)
        self.assertIn("sleep 응답 없음", err)
        self.assertEqual((ntop._running, ntop._stuck), (set(), {}))

    def test_missing_binary(self):
        rc, out, err = ntop.run_cmd(["/nonexistent/dir/nvidia-smi", "x"])
        self.assertEqual(rc, -1)
        self.assertIn("nvidia-smi 실행 실패", err)

    def test_unkillable_child_is_not_respawned(self):
        import subprocess
        real_kill = subprocess.Popen.kill
        subprocess.Popen.kill = lambda self: None          # 드라이버 안에서 멈춰 SIGKILL 이 안 듣는 smi 흉내
        try:
            t0 = time.monotonic()
            rc, _, err = ntop.run_cmd(["sleep", "30"], timeout=0.2)
            self.assertLess(time.monotonic() - t0, 3.0)    # 끝없이 기다리지 않는다
            self.assertEqual(rc, -1)
            stuck = ntop._stuck["sleep"]
            self.assertIsNone(stuck.poll())
            rc, _, err = ntop.run_cmd(["sleep", "30"], timeout=0.2)     # 새로 띄우지 않는다
            self.assertEqual(rc, -1)
            self.assertIn(f"멈춘 프로세스 {stuck.pid}", err)
            self.assertEqual(len(ntop._stuck), 1)
        finally:
            subprocess.Popen.kill = real_kill
        stuck.kill()
        stuck.wait(2)
        rc, out, _ = ntop.run_cmd(["echo", "ok"])           # 사라지면 다시 띄운다 (다른 이름이라 바로 됨)
        self.assertEqual((rc, out.strip()), (0, "ok"))
        rc, _, err = ntop.run_cmd(["sleep", "0"])
        self.assertEqual(rc, 0)
        self.assertEqual(ntop._stuck, {})

    def test_kill_children(self):
        import subprocess
        import threading
        res = []
        th = threading.Thread(target=lambda: res.append(ntop.run_cmd(["sleep", "30"], timeout=20)))
        th.start()
        t0 = time.monotonic()
        while not ntop._running and time.monotonic() - t0 < 2:
            time.sleep(0.01)
        (p,) = ntop._running
        ntop.kill_children()
        th.join(3)
        self.assertFalse(th.is_alive())
        self.assertEqual(res[0][0], -9)
        self.assertIsNotNone(p.poll())

    def test_no_spawn_while_closing(self):
        # 2차 검토 procs:1 — status 가 죽은 뒤 수집 스레드가 info 를 새로 띄워 고아가 남던 것
        import threading
        res = []

        def two_calls():                       # gather() 처럼 smi 를 잇달아 둘 부른다
            res.append(ntop.run_cmd(["sleep", "30"], timeout=20))
            res.append(ntop.run_cmd(["sleep", "31"], timeout=20))
        th = threading.Thread(target=two_calls)
        th.start()
        t0 = time.monotonic()
        while not ntop._running and time.monotonic() - t0 < 2:
            time.sleep(0.01)
        ntop.kill_children()
        th.join(3)
        self.assertFalse(th.is_alive())
        self.assertEqual(res[0][0], -9)                      # 돌던 것은 죽었고
        self.assertEqual(res[1][0], -1)                      # 다음 것은 띄우지 않았다
        self.assertIn("끝내는 중", res[1][2])
        self.assertEqual(ntop._running, set())
        import subprocess
        left = subprocess.run(["pgrep", "-P", str(os.getpid()), "-x", "sleep"], capture_output=True, text=True).stdout.split()
        self.assertEqual(left, [])

    def test_smi_helpers_use_run_cmd(self):
        saved = ntop.run_cmd
        calls = []
        try:
            def fake(argv, timeout=3.0):
                calls.append(argv)
                if "--format" in argv:
                    return 0, '[{"device": "npu0"}]', ""
                return 0, "TEXT", "warn"
            ntop.run_cmd = fake
            self.assertEqual(ntop.run_smi_json("status"), [{"device": "npu0"}])
            self.assertEqual(ntop.run_smi_text("ps"), "TEXT\nwarn")
            self.assertEqual(calls, [["furiosa-smi", "status", "--format", "json"], ["furiosa-smi", "ps"]])
            ntop.run_cmd = lambda argv, timeout=3.0: (-1, "", "furiosa-smi 응답 없음 (3s 초과)")
            self.assertEqual(ntop.run_smi_json("status"), [])
            ntop.run_cmd = lambda argv, timeout=3.0: (0, "not json", "")
            self.assertEqual(ntop.run_smi_json("status"), [])
        finally:
            ntop.run_cmd = saved


class PmonChunks(unittest.TestCase):
    def setUp(self):
        self.saved = ntop.run_cmd

    def tearDown(self):
        ntop.run_cmd = self.saved

    def test_more_than_four_gpus_are_asked_in_chunks(self):
        calls = []

        def fake(argv, timeout=3.0):
            calls.append(argv)
            ids = argv[argv.index("-i") + 1].split(",") if "-i" in argv else ["0"]
            body = "".join(f"    {i}      {1000 + int(i)}     C     10      5      -      -      -      -   {100 * (int(i) + 1)}      0    w{i}\n" for i in ids)
            return 0, "# gpu pid type sm mem enc dec jpg ofa fb ccpm command\n# Idx # C/G % % % % % % MB MB name\n" + body, ""
        ntop.run_cmd = fake
        procs, err = ntop.gather_gpu_procs([0, 1, 2, 3, 4, 5])
        self.assertEqual(err, "")
        self.assertEqual([c[6:] for c in calls], [["-i", "0,1,2,3"], ["-i", "4,5"]])
        self.assertEqual(sorted(p.gpu for p in procs), [0, 1, 2, 3, 4, 5])
        self.assertEqual(procs[0].gpu, 5)                   # 메모리 큰 순
        calls.clear()
        ntop.gather_gpu_procs([0, 1, 2, 3])
        ntop.gather_gpu_procs([])
        ntop.gather_gpu_procs()
        self.assertTrue(all("-i" not in c for c in calls))
        self.assertEqual(len(calls), 3)

    def test_failure_in_any_chunk_is_an_error(self):
        n = []

        def fake(argv, timeout=3.0):
            n.append(1)
            return (0, "# gpu pid type sm mem enc dec fb command\n", "") if len(n) == 1 else (1, "", "boom")
        ntop.run_cmd = fake
        self.assertEqual(ntop.gather_gpu_procs(list(range(8))), ([], "boom"))


class GatherPs(unittest.TestCase):
    def setUp(self):
        self.saved = ntop.run_cmd

    def tearDown(self):
        ntop.run_cmd = self.saved

    def test_filter_and_own_children_excluded(self):
        me = os.getpid()
        out = "\n".join([
            "   PPID     PID USER     %CPU %MEM     ELAPSED CMD",
            f"      1  444724 jun       101 27.7    10:59:14 /usr/bin/python3 /opt/furiosa/bin/furiosa-llm serve x",
            f"{me:>7} 1000001 jun       9.0  0.0       00:00 furiosa-smi status --format json",
            f"{me:>7} 1000002 jun       9.0  0.0       00:00 nvidia-smi pmon -c 1 -s um",
            f"      1  950487 jun       4.5  2.4       49:49 VLLM::EngineCore",
            f"      1  950194 jun       0.8  1.2       49:58 /v/bin/python /v/bin/vllm serve gpt-oss-20b",
            f"      1    3139 gdm       0.0  0.0  1-01:00:00 /usr/lib/xorg/Xorg vt1",
            f"      1    7777 kim       0.0  0.0       00:01 furiosa-smi status",
            f"      1    6000 lee       2.0  0.1       10:00 python3 /home/lee/.local/bin/nctop -i 1",
            f"   6000    6001 lee       9.0  0.0       00:00 furiosa-smi status --format json",
            f"      1    6100 lee       2.0  0.1       10:00 /usr/bin/python3 /srv/RNGD-proj/ntop.py",
            f"   6100    6101 lee       9.0  0.0       00:00 furiosa-smi info --format json",
            f"      1    6200 lee       0.1  0.1       10:00 top -b",
            f"   6200    6201 lee       0.1  0.0       00:00 furiosa-smi status --watch 1",
            f"      1    8888 kim       0.0  0.0       00:01 grep furiosa-llm",
            f"      1    9999 kim       0.0  0.0       00:01 vim notes.txt",
        ])
        ntop.run_cmd = lambda argv, timeout=3.0: (0, out, "")
        rows = ntop.gather_ps({950487})
        # 6001·6101: 다른 사람의 nctop·ntop.py 가 띄운 smi 는 빠진다. 6201: 부모가 ntop 이 아니면 남는다
        self.assertEqual([r[0] for r in rows], ["444724", "950487", "950194", "7777", "6201"])
        self.assertEqual(rows[1], ("950487", "jun", "4.5", "2.4", "49:49", "VLLM::EngineCore"))
        self.assertEqual(rows[0][5], "/usr/bin/python3 /opt/furiosa/bin/furiosa-llm serve x")

    def test_limit_and_failure(self):
        many = "HEAD\n" + "\n".join(f"      1 {100 + i:>7} u 1.0 1.0 00:01 furiosa-llm serve {i}" for i in range(20))
        ntop.run_cmd = lambda argv, timeout=3.0: (0, many, "")
        self.assertEqual(len(ntop.gather_ps(set())), 8)
        ntop.run_cmd = lambda argv, timeout=3.0: (-1, "", "ps 실행 실패")
        self.assertIsNone(ntop.gather_ps(set()))


class Polling(unittest.TestCase):
    """수집 스레드: 종류별 주기, 서로 막지 않기, 실패·멈춤 표시."""

    NAMES = ("gather", "gather_gpus", "gather_gpu_procs", "gather_host", "gather_ps", "gather_raw")

    def setUp(self):
        self.saved = {n: getattr(ntop, n) for n in self.NAMES}
        self.sources = None

    def tearDown(self):
        if self.sources:
            self.sources.stop()
            for p in self.sources.pollers.values():
                p.join(5.0)
        for n, f in self.saved.items():
            setattr(ntop, n, f)

    def fake(self, **fns):
        base = dict(gather=npu_devs, gather_gpus=lambda: (ntop.parse_gpu_csv(gpu_line(), FIELDS), ""),
                    gather_gpu_procs=lambda *a: (ntop.parse_pmon(PMON), ""), gather_host=host,
                    gather_ps=lambda pids: [], gather_raw=lambda: "RAW")
        base.update(fns)
        for n, f in base.items():
            setattr(ntop, n, f)

    def start(self, a, on_update=lambda: None):
        self.sources = ntop.Sources(a, on_update)
        self.sources.start()
        return self.sources

    def test_poller_runs_periodically(self):
        n = []
        p = ntop.Poller("t", lambda: n.append(1) or len(n), 0.05)
        p.start()
        self.assertTrue(p.ready.wait(1.0))
        time.sleep(0.33)
        p.stop()
        p.join(1.0)
        self.assertFalse(p.is_alive())
        self.assertTrue(5 <= len(n) <= 9, len(n))
        self.assertEqual(p.value, len(n))
        self.assertGreater(p.ts, 0)

    def test_poller_pauses(self):
        n = []
        p = ntop.Poller("t", lambda: n.append(1), 0.02)
        ntop.Poller.paused = True
        try:
            p.start()
            time.sleep(0.3)
            self.assertEqual(n, [])
            self.assertFalse(p.ready.is_set())
            ntop.Poller.paused = False
            self.assertTrue(p.ready.wait(1.0))
        finally:
            ntop.Poller.paused = False
            p.stop()
            p.join(1.0)
        self.assertFalse(p.is_alive())

    def test_result_spanning_a_suspend_is_discarded(self):
        # 도는 사이에 Ctrl+Z 로 멈췄다 깬 호출(가짜 시간 초과)은 내놓지 않고 다시 돈다
        n = []

        def fn():
            n.append(1)
            if len(n) == 1:
                ntop.Poller.resumed_at = time.monotonic() + 0.001      # 이 호출 도중에 SIGCONT 가 왔다
                time.sleep(0.01)
                return "bogus"
            return "good"
        saved = ntop.Poller.resumed_at
        p = ntop.Poller("t", fn, 5.0)
        try:
            p.start()
            self.assertTrue(p.ready.wait(2.0))
            self.assertEqual(p.value, "good")
            self.assertEqual(len(n), 2)
        finally:
            ntop.Poller.resumed_at = saved
            p.stop()
            p.join(1.0)

    def test_poller_survives_exception_and_recovers(self):
        n = []

        def fn():
            n.append(1)
            if len(n) <= 2:
                raise RuntimeError("boom")
            return "ok"
        woke = []
        p = ntop.Poller("t", fn, 0.03, lambda: woke.append(1))
        p.start()
        self.assertTrue(p.ready.wait(1.0))
        self.assertIn("RuntimeError: boom", p.error)
        self.assertIsNone(p.value)
        time.sleep(0.2)
        p.stop()
        p.join(1.0)
        self.assertEqual((p.value, p.error), ("ok", ""))
        self.assertGreaterEqual(len(woke), 3)

    def test_periods(self):
        n = {"npu": 0, "gpu": 0, "procs": 0, "ps": 0, "host": 0}

        def count(key, ret):
            def f(*a):
                n[key] += 1
                return ret() if callable(ret) else ret
            return f
        self.fake(gather=count("npu", npu_devs), gather_host=count("host", host),
                  gather_gpus=count("gpu", lambda: (ntop.parse_gpu_csv(gpu_line(), FIELDS), "")),
                  gather_gpu_procs=count("procs", lambda: (ntop.parse_pmon(PMON), "")),
                  gather_ps=count("ps", []))
        s = self.start(args(interval=0.1))
        time.sleep(2.45)
        s.stop()
        self.assertTrue(20 <= n["npu"] <= 26, n)
        self.assertTrue(20 <= n["host"] <= 26, n)
        self.assertEqual(n["gpu"], 3, n)             # t=0,1,2
        self.assertEqual(n["procs"], 2, n)           # t=0,2
        self.assertEqual(n["ps"], 2, n)

    def test_pmon_waits_for_gpu_indices(self):
        # 2차 검토 fixcheck:1 — 첫 바퀴에도 GPU 번호를 알고 pmon 을 묻는다
        seen = []

        def slow_gpus():
            time.sleep(0.3)
            return ntop.parse_gpu_csv("\n".join(gpu_line(i) for i in range(6)), FIELDS), ""

        def procs(indices=None):
            seen.append(list(indices or []))
            return [], ""
        self.fake(gather_gpus=slow_gpus, gather_gpu_procs=procs)
        s = self.start(args(interval=0.1))
        t0 = time.monotonic()
        while not seen and time.monotonic() - t0 < 3:
            time.sleep(0.02)
        self.assertEqual(seen[0], [0, 1, 2, 3, 4, 5])

    def test_long_interval_overrides_periods(self):
        self.fake()
        s = ntop.Sources(args(interval=5.0), lambda: None)
        self.assertEqual({k: p.period for k, p in s.pollers.items()},
                         {"npu": 5.0, "host": 5.0, "gpu": 5.0, "gpu_procs": 5.0, "ps": 5.0})
        s = ntop.Sources(args(interval=0.01, raw=True, no_ps=True, gpu=False), lambda: None)
        self.assertEqual({k: p.period for k, p in s.pollers.items()},
                         {"npu": 0.1, "raw": 0.1, "host": 0.1})
        s = ntop.Sources(args(cpu=False), lambda: None)
        self.assertEqual({k: p.period for k, p in s.pollers.items()},
                         {"npu": 0.5, "gpu": 1.0, "gpu_procs": 2.0, "ps": 2.0})

    def test_snapshot_merges_and_ps_gets_compute_pids(self):
        seen = []

        def ps(pids):
            seen.append(pids)
            return [("950487", "jun", "1", "1", "0:01", "VLLM::EngineCore")]
        self.fake(gather_ps=ps)
        woke = []
        s = self.start(args(raw=True), lambda: woke.append(1))
        s.wait_ready()
        snap = s.snapshot()
        self.assertEqual(len(snap.devs), 4)
        self.assertGreater(snap.ts, 0)
        self.assertEqual(snap.raw_payload, "RAW")
        self.assertEqual(len(snap.host.cpu_ids), 128)
        self.assertEqual((len(snap.gpus), snap.gpu_error), (1, ""))
        self.assertEqual((len(snap.gpu_procs), snap.gpu_procs_error), (2, ""))
        self.assertEqual(snap.ps_rows[0][0], "950487")
        self.assertEqual(seen[0], {950487})          # C 타입만, 첫 바퀴부터
        self.assertEqual(snap.error, "")
        self.assertGreaterEqual(len(woke), 1)        # NPU 수집이 화면을 깨운다

    def test_slow_gpu_does_not_block_others(self):
        def slow_gpu():
            time.sleep(1.2)
            return ntop.parse_gpu_csv(gpu_line(), FIELDS), ""
        n = {"npu": 0}

        def npu():
            n["npu"] += 1
            return npu_devs()
        self.fake(gather_gpus=slow_gpu, gather=npu)
        s = self.start(args(interval=0.1))
        t0 = time.monotonic()
        s.wait_ready()
        self.assertLess(time.monotonic() - t0, 0.9)  # 느린 GPU 를 기다리느라 첫 화면이 늦지 않는다
        snap = s.snapshot()
        self.assertEqual(len(snap.devs), 4)
        self.assertEqual((snap.gpus, snap.gpu_error), ([], "nvidia-smi 응답 대기 중"))
        with NumaPatch(NUMA2):
            self.assertIn("응답 대기 중", "\n".join(render(snap)))
        time.sleep(0.5)
        self.assertGreaterEqual(n["npu"], 6)         # NPU 는 제 주기로 계속 돈다
        time.sleep(0.6)
        snap = s.snapshot()
        self.assertEqual((len(snap.gpus), snap.gpu_error), (1, ""))

    def test_stalled_smi_shown_as_error(self):
        self.fake()
        s = self.start(args())
        s.wait_ready()
        s.stop()
        for p in s.pollers.values():
            p.join(5.0)
        gpu = s.pollers["gpu"]
        gpu.started = time.monotonic() - 30          # 30초째 안 끝나는 nvidia-smi 호출
        gpu.ts = gpu.started - 1
        snap = s.snapshot()
        self.assertEqual(snap.gpus, [])
        self.assertRegex(snap.gpu_error, r"nvidia-smi 응답 없음 \(3\d초째\)")
        # 첫 호출이 영영 안 끝나는 경우(ts 가 0)도 멈춤으로 본다
        gpu.started, gpu.ts = time.monotonic() - 30, 0.0
        self.assertRegex(s.snapshot().gpu_error, r"nvidia-smi 응답 없음 \(3\d초째\)")
        gpu.started = time.monotonic() - 30
        gpu.ts = gpu.started - 1
        self.assertEqual(len(snap.gpu_procs), 2)     # pmon 쪽은 멀쩡
        s.pollers["npu"].ts -= 30
        with NumaPatch(NUMA2):
            out = "\n".join(render(s.snapshot()))
        self.assertRegex(out, r"NPU 데이터 3\d초 전")
        self.assertRegex(out, r"nvidia-smi 응답 없음")

    def test_gpu_failure_then_recovery(self):
        state = {"fail": True}
        self.fake(gather_gpus=lambda: ([], "nvidia-smi 응답 없음 (3s 초과)") if state["fail"] else (
            ntop.parse_gpu_csv(gpu_line(), FIELDS), ""))
        s = self.start(args(interval=0.1))
        s.wait_ready()
        snap = s.snapshot()
        self.assertEqual(snap.gpus, [])
        self.assertIn("응답 없음", snap.gpu_error)
        with NumaPatch(NUMA2):
            self.assertIn("응답 없음", "\n".join(render(snap)))
            self.assertIn("응답 없음", "\n".join(render(snap, page=1)))
        state["fail"] = False
        time.sleep(1.3)
        snap = s.snapshot()
        self.assertEqual((len(snap.gpus), snap.gpu_error), (1, ""))

    def test_ps_failure_and_pending(self):
        self.fake(gather_ps=lambda pids: None)
        s = ntop.Sources(args(), lambda: None)
        self.assertEqual(s.snapshot().ps_rows, [])   # 아직 안 돈 상태: 빈 목록
        self.sources = s
        s.start()
        s.wait_ready()
        self.assertIsNone(s.snapshot().ps_rows)      # ps 실패
        with NumaPatch(NUMA2):
            self.assertIn("(ps 실패)", "\n".join(render(s.snapshot())))

    def test_collection_exception_reaches_header(self):
        def boom():
            raise RuntimeError("boom")
        self.fake(gather_host=boom)
        s = self.start(args(interval=0.1))
        s.wait_ready()
        time.sleep(0.25)
        snap = s.snapshot()
        self.assertEqual(snap.error, "host: RuntimeError: boom")
        self.assertEqual(len(snap.devs), 4)          # 다른 수집은 계속 된다
        with NumaPatch(NUMA2):
            self.assertIn("수집 오류: host: RuntimeError: boom", "\n".join(render(snap, w=200)))

    def test_npu_pending_warning(self):
        with NumaPatch(NUMA2):
            self.assertIn("furiosa-smi 응답 대기 중", "\n".join(render(ntop.Snapshot())))


class Layout(unittest.TestCase):
    SIZES = [(250, 70), (200, 55), (160, 45), (140, 40), (120, 40), (119, 36), (118, 36),
             (100, 30), (80, 24), (60, 20), (40, 12), (20, 6)]

    def check_fits(self, lines, w, h, what):
        self.assertLessEqual(len(lines), h, f"{what}: {len(lines)} 줄 > {h}")
        from rich.cells import cell_len
        widest = max(cell_len(l) for l in lines)
        self.assertLessEqual(widest, w, f"{what}: 폭 {widest} > {w}")

    def test_all_sizes_all_pages_all_modes(self):
        variants = {
            "기본": (snapshot(), args()),
            "GPU 8장": (snapshot(gpus=8), args()),
            "GPU 오류": (snapshot(gpus=0, procs="", gpu_error="NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver."), args()),
            "GPU 없음": (snapshot(gpus=0, procs=""), args()),
            "pmon 오류": (snapshot(procs="", gpu_procs_error="nvidia-smi pmon 실패 (종료 코드 1)"), args()),
            "NPU 없음": (snapshot(devs=[]), args()),
            "host 없음": (snapshot(host=None), args()),
            "ps 실패": (snapshot(ps_rows=None), args()),
            "no-ps": (snapshot(), args(no_ps=True)),
            "raw": (snapshot(raw_payload="=== status ===\n{...}\n" * 30), args(raw=True)),
            "no-gpu": (snapshot(gpus=0, procs=""), args(gpu=False)),
            "gpu만": (snapshot(host=None), args(cpu=False)),
            "ntop": (snapshot(gpus=0, procs="", host=None), args(cpu=False, gpu=False)),
            "N/A 투성이": (snapshot(gpu_over=dict(utilization__gpu="[N/A]", power__draw="[N/A]",
                                                   temperature__gpu="[N/A]", memory__used="[N/A]",
                                                   memory__total="[N/A]", power__limit="[N/A]",
                                                   temperature__gpu__tlimit="[N/A]")), args()),
        }
        for name, (snap, a) in variants.items():
            pages = ["Overview"] + (["Detail"] if a.cpu or a.gpu else [])
            for numa in (NUMA2, []):
                with NumaPatch(numa):
                    for w, h in self.SIZES:
                        for page in range(len(pages)):
                            what = f"{name} {w}x{h} p{page + 1} numa={bool(numa)}"
                            with self.subTest(what):
                                lines = render(snap, a, w, h, page=page, pages=pages)
                                self.check_fits(lines, w, h, what)

    def test_overview_content(self):
        with NumaPatch(NUMA2):
            out = "\n".join(render(snapshot(), w=160, h=45))
        self.assertIn("GPU Devices", out)
        self.assertIn("RTX PRO 6000 Blackwell Server Edition", out)
        self.assertIn("VLLM::EngineCore 38.6G", out)
        self.assertIn("Xorg 4M", out)
        self.assertIn("1 Overview", out)
        self.assertIn("←/→: page", out)
        self.assertNotIn("NUMA", out)
        self.assertNotIn("c  0:", out)
        self.assertRegex(out, r"950487 jun\s+4\.5%\s+2\.4%\s+49:49\s+38\.6G\s+VLLM::EngineCore")
        self.assertRegex(out, r"444724 jun\s+101%\s+27\.7%\s+10:59:14\s+-\s+python3 /x/furiosa-llm serve")

    def test_detail_content_busy(self):
        snap = snapshot(gpu_over=dict(utilization__gpu="97", utilization__memory="55",
                                      power__draw="540.2", temperature__gpu="84",
                                      temperature__gpu__tlimit="3",
                                      clocks_event_reasons__active="0x0000000000000024"))
        snap.host = host(hot=(32, 64))
        with NumaPatch(NUMA2):
            out = "\n".join(render(snap, w=160, h=45, page=1))
        self.assertIn("NUMA node0  ·  cpus 0-31,64-95", out)
        self.assertIn("NUMA node1  ·  cpus 32-63,96-127", out)
        self.assertRegex(out, r"c 32:100%")
        self.assertRegex(out, r"c 64:100%")
        self.assertIn("97.0%", out)
        self.assertRegex(out, r"mem I/O\s+55%")
        self.assertIn("540.2/600W (90.0%)", out)
        self.assertIn("84.0°C", out)
        self.assertIn("3°C below T.Limit", out)
        self.assertIn("throttle sw power cap, sw thermal", out)
        self.assertIn("load 1.39 1.23 1.25", out)
        self.assertRegex(out, r"950487 jun\s+C\s+38\.6G\s+87\s+41\s+-\s+-\s+VLLM::EngineCore")
        self.assertNotIn("NPU Devices", out)

    def test_detail_strip_when_short(self):
        with NumaPatch(NUMA2):
            tall = "\n".join(render(snapshot(), w=160, h=45, page=1))
            short = "\n".join(render(snapshot(), w=160, h=28, page=1))
        self.assertIn("c  0:", tall)
        self.assertNotIn("c  0:", short)
        self.assertIn("▁" * 64, short)
        self.assertIn("gpu0  ·  NVIDIA", short)
        self.assertIn("GPU-MEM", short)

    def test_detail_drops_gpu_extras_when_many_gpus(self):
        snap = snapshot(gpus=4)
        with NumaPatch(NUMA2):
            tall = "\n".join(render(snap, w=160, h=120, page=1))
            short = "\n".join(render(snap, w=160, h=50, page=1))
        self.assertEqual(tall.count("UUID"), 4)
        self.assertIn("c  0:", tall)
        self.assertNotIn("UUID", short)             # 세부 값을 빼서
        self.assertNotIn("PCIe", short)
        self.assertEqual(short.count("GPU-MEM"), 4)  # 네 장의 프로세스 표가 다 보인다
        self.assertEqual(short.count("Util "), 4)

    def test_compact_gpu_keeps_alarms(self):
        snap = snapshot(gpus=4, gpu_over=dict(clocks_event_reasons__active="0x0000000000000040",
                                              ecc__errors__uncorrected__volatile__total="3"))
        with NumaPatch(NUMA2):
            short = "\n".join(render(snap, w=160, h=58, page=1))
        self.assertNotIn("UUID", short)
        self.assertEqual(short.count("throttle hw thermal"), 4)
        self.assertEqual(short.count("3 uncorrected"), 4)

    def test_tlimit_text(self):
        with NumaPatch(NUMA2):
            over = "\n".join(render(snapshot(gpu_over=dict(temperature__gpu__tlimit="-2")), page=1))
            zero = "\n".join(render(snapshot(gpu_over=dict(temperature__gpu__tlimit="0")), page=1))
            below = "\n".join(render(snapshot(gpu_over=dict(temperature__gpu__tlimit="7")), page=1))
        self.assertIn("2°C over T.Limit", over)
        self.assertIn("0°C over T.Limit", zero)
        self.assertIn("7°C below T.Limit", below)

    def test_wide_but_short_terminal_keeps_gpu_rows(self):
        # 검토 overview:1 — 160x24: NPU 표가 Per-core 로 2줄씩 먹어 GPU 행이 잘리던 크기
        with NumaPatch(NUMA2):
            lines = render(snapshot(), w=160, h=24)
        out = "\n".join(lines)
        self.assertIn("gpu0", out)
        self.assertRegex(out, r"gpu0\s*│RTX PRO 6000")
        self.assertNotIn("Per-core", out)                    # 자리를 내려고 열을 숨겼다
        self.assertEqual(sum(1 for l in lines if l.startswith("╰")), 4)     # 요약·NPU·CPU·GPU 패널이 다 닫혔다
        self.assertNotIn("잘림", out)
        with NumaPatch(NUMA2):
            roomy = "\n".join(render(snapshot(), w=160, h=45))
        self.assertIn("Per-core", roomy)                     # 넉넉하면 그대로

    def test_percore_is_not_hidden_just_for_processes(self):
        # 표가 다 들어가면 프로세스 패널 자리를 내려고 Per-core 를 숨기지는 않는다
        with NumaPatch(NUMA2):
            out = "\n".join(render(snapshot(), w=160, h=30))
        self.assertIn("Per-core", out)
        self.assertIn("gpu0", out)

    def test_many_gpus_overview_compacts_then_warns(self):
        snap = snapshot(gpus=8)
        with NumaPatch(NUMA2):
            h36 = render(snap, w=160, h=36)
            h20 = render(snap, w=160, h=20)
        out = "\n".join(h36)
        self.assertTrue(all(f"gpu{i}" in out for i in range(8)), "160x36 에서 GPU 8장이 다 보여야 한다")
        self.assertNotIn("잘림", out)
        self.assertIn("창이 작아 아래가 잘림", "\n".join(h20))

    def test_clip_warning_on_detail(self):
        with NumaPatch(NUMA2):
            small = "\n".join(render(snapshot(), w=100, h=14, page=1))
            fine = "\n".join(render(snapshot(), w=160, h=45, page=1))
        self.assertIn("창이 작아 아래가 잘림", small)
        self.assertNotIn("잘림", fine)

    def test_detail_lines_break_between_items(self):
        # 검토 goal:1 — 'ofa' 와 그 값이 다른 줄로 갈라지지 않는다
        busy = snapshot(gpu_over=dict(utilization__gpu="97", utilization__memory="100",
                                      utilization__encoder="100", power__draw="571.3"))
        for w in (80, 90, 100, 110, 117, 118, 119, 130, 160):
            for snap in (snapshot(), busy):
                with NumaPatch(NUMA2):
                    lines = render(snap, w=w, h=60, page=1)
                for label in ("mem I/O", "enc", "dec", "jpeg", "ofa", "avg", "instant", "fan"):
                    for l in lines:
                        if f" {label} " in l or l.rstrip(" │").endswith(" " + label):
                            self.assertRegex(l, rf"{label}\s+[\d.NA/]+", f"w={w}: {l!r}")
                # 값이 바뀌어도 줄 수는 같다 (패널 높이가 출렁이지 않게)
            with NumaPatch(NUMA2):
                a = render(snapshot(), w=w, h=60, page=1)
                b = render(busy, w=w, h=60, page=1)
            self.assertEqual(len([l for l in a if l.strip()]), len([l for l in b if l.strip()]), f"w={w}")

    def test_header_groups_when_gpu_on(self):
        with NumaPatch(NUMA2):
            on = render(snapshot(), w=200, h=45)[1]
            off = render(snapshot(gpus=0, procs=""), args(gpu=False), w=200, h=45)[1]
            narrow = render(snapshot(), w=118, h=45)[1]
        self.assertRegex(on, r"NPU 4/4 alive\s+·\s+util\s+0\.0%\s+·\s+MEM 152\.8/190G")
        self.assertRegex(on, r"GPU\s+0\.0%\s+38\.6/96G \(40\.4%\)\s+90W")
        self.assertRegex(off, r"4/4 alive\s+·\s+NPU\s+0\.0%\s+·\s+MEM")     # GPU 가 꺼져 있으면 예전 그대로
        self.assertNotIn("GPU", off)
        self.assertNotIn("util", off)
        self.assertIn("NPU 4/4 alive", narrow)               # 좁으면 뒤(GPU 묶음)부터 빠진다
        self.assertNotIn("GPU", narrow)

    def test_header_keeps_warning_when_narrow(self):
        # 2차 검토 layout:1 — 좁은 창에서 경고가 먼저 빠지던 것
        snap = snapshot(gpus=8)
        with NumaPatch(NUMA2):
            for w in (40, 50, 58, 59, 70):
                head = render(snap, w=w, h=9, page=1)[1]
                self.assertIn("창이", head, f"w={w}: {head!r}")
            wide = render(snap, w=120, h=9, page=1)[1]
        self.assertIn("창이 작아 아래가 잘림", wide)
        err = snapshot(error="gpu: RuntimeError: " + "x" * 90)
        with NumaPatch(NUMA2):
            for w in (60, 100, 140):
                self.assertIn("수집 오류", render(err, w=w, h=40)[1], f"w={w}")

    def test_throttle_text_does_not_change_row_count(self):
        # 2차 검토 fixcheck:2 — 사유가 바뀌어도(하나짜리) 줄 수가 같다
        for w in (80, 90, 100, 118, 160):
            counts = set()
            for mask in ("0x0000000000000000", "0x0000000000000001", "0x0000000000000004",
                         "0x0000000000000008", "0x0000000000000020", "0x0000000000000080"):
                with NumaPatch(NUMA2):
                    lines = render(snapshot(gpu_over=dict(clocks_event_reasons__active=mask)), w=w, h=70, page=1)
                counts.add(len([l for l in lines if l.strip()]))
            self.assertEqual(len(counts), 1, f"w={w}: {counts}")

    def test_cpu_summary_wraps_between_items(self):
        with NumaPatch(NUMA2):
            lines = render(snapshot(), w=80, h=40, page=1)
        self.assertTrue(any("load 1.39 1.23 1.25" in l for l in lines))
        self.assertFalse(any(l.rstrip(" │").endswith("load") for l in lines))

    def test_numa_mismatch_falls_back_to_single_group(self):
        # 노드 정보가 실제 CPU 와 안 맞으면 묶지 않는다 (코어를 빠뜨리지 않게)
        bad = [(0, "0-3", [0, 1, 2, 3]), (1, "4-7", [4, 5, 6, 7])]
        with NumaPatch(bad):
            out = "\n".join(render(snapshot(), w=200, h=60, page=1))
        self.assertNotIn("NUMA", out)
        self.assertIn("c127:", out)
        self.assertIn("c  0:", out)

    def test_overview_compact_when_tight(self):
        with NumaPatch(NUMA2):
            roomy = render(snapshot(), w=118, h=45)
            tight = render(snapshot(), w=118, h=36)
        self.assertTrue(any(l.startswith("│ ├") for l in roomy))
        self.assertFalse(any(l.startswith("│ ├") for l in tight))       # 행 구분선을 뺐다
        self.assertIn("Per-core", "\n".join(tight))                     # 열은 그대로
        self.assertIn("furiosa-llm", "\n".join(tight))

    def test_no_gpu_keeps_old_overview(self):
        a = args(gpu=False)
        snap = snapshot(gpus=0, procs="")
        with NumaPatch(NUMA2):
            wide = "\n".join(render(snap, a, w=160, h=50))
            narrow = "\n".join(render(snap, a, w=118, h=50))
        self.assertIn("c  0:", wide)             # ≥ 120칸: 첫 화면에 코어 그리드
        self.assertNotIn("NUMA", wide)           # 첫 화면은 예전 그대로 한 덩어리
        self.assertNotIn("c  0:", narrow)
        self.assertNotIn("GPU", wide.replace("NPU", ""))
        self.assertIn("Top NPU-related host processes", wide)

    def test_header_drops_parts_when_narrow(self):
        with NumaPatch(NUMA2):
            for w in (200, 160, 118, 100, 80, 60, 40):
                lines = render(snapshot(), w=w, h=45)
                self.assertEqual(lines[2][0], "╰", f"머리 패널이 3줄이 아니다 (w={w})")
                self.assertIn("nctop", lines[1])

    def test_stale_and_error_warning(self):
        old = snapshot()
        old.ts = time.monotonic() - 12
        with NumaPatch(NUMA2):
            self.assertRegex("\n".join(render(old)), r"NPU 데이터 1[23]초 전")
            self.assertNotIn("초 전", "\n".join(render(snapshot())))

    def test_keys_off_hint(self):
        with NumaPatch(NUMA2):
            out = "\n".join(render(snapshot(), keys_on=False))
        self.assertNotIn("←/→", out)
        self.assertIn("Ctrl+C: quit", out)
        self.assertNotIn("q/Ctrl+C", out)

    def test_long_process_names_do_not_wrap(self):
        snap = snapshot()
        snap.ps_rows = [("1", "averyveryverylonguser", "99.9", "99.9", "123-10:59:14",
                         "python3 " + "/very/long/path/segment" * 20 + " serve " + "--flag=value " * 40)]
        for p in snap.gpu_procs:
            p.cmd = "/opt/" + "x" * 500 + " --serve"
        with NumaPatch(NUMA2):
            for w in (200, 160, 118, 80):
                self.check_fits(render(snap, w=w, h=50), w, 50, f"긴 이름 p1 {w}")
                self.check_fits(render(snap, w=w, h=60, page=1), w, 60, f"긴 이름 p2 {w}")
                p1 = render(snap, w=w, h=50)
                row = [l for l in p1 if "averyvery" in l]
                self.assertEqual(len(row), 1)
                nxt = p1[p1.index(row[0]) + 1]
                self.assertTrue(nxt.startswith("│  ") and nxt.strip("│ ") == "" or nxt.startswith("╰"),
                                f"프로세스 줄이 넘어갔다 (w={w}): {nxt!r}")


if __name__ == "__main__":
    unittest.main(verbosity=1)
