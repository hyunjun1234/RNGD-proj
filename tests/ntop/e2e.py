#!/usr/bin/env python3
"""tmux 로 nctop 을 실제 터미널에서 몰아 보는 종단 시험.

사용: python3 e2e.py [시험이름 ...]     (이름 없으면 전부)
전용 tmux 서버(-L nctop-e2e-<pid>)를 쓰고 끝나면 서버를 내린다.

기본으로 가짜 smi(fakebin/nvidia-smi, fakenpu/furiosa-smi)만 쓴다 — 실제 NPU·GPU 를 두드리지 않는다.
실제 smi 로 돌리려면 NCTOP_E2E_REAL=1 (이 서버 구성: NPU 4장, RTX PRO 6000 1장 기준의 시험이다).
"""
import atexit
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
NTOP_PY = os.path.join(os.environ.get("NTOP_DIR") or os.path.abspath(os.path.join(HERE, "..", "..")),
                       "ntop.py")
REAL = os.environ.get("NCTOP_E2E_REAL") == "1"
# argv[0] 이 이름을 정한다 — 임시 폴더에 nctop·ntop 이라는 심볼릭 링크를 만들어 띄운다
TMP = tempfile.mkdtemp(prefix="nctop-e2e-")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)
NCTOP = os.path.join(TMP, "nctop")       # CPU·GPU 기본 ON
NTOP = os.path.join(TMP, "ntop")
for _link in (NCTOP, NTOP):
    os.symlink(NTOP_PY, _link)
SOCK = f"nctop-e2e-{os.getpid()}"
FAKEBIN = os.path.join(HERE, "fakebin")
FAKENPU = os.path.join(HERE, "fakenpu")
RESULTS: list[tuple[str, bool, str]] = []


def tmux(*a: str, check: bool = True) -> str:
    r = subprocess.run(["tmux", "-L", SOCK, *a], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"tmux {' '.join(a)} → {r.returncode}: {r.stderr.strip()}")
    return r.stdout


class Term:
    """지정 크기의 tmux 창 하나 (안에서 bash 가 돈다)."""
    n = 0

    def __init__(self, w: int = 160, h: int = 45):
        Term.n += 1
        self.name = f"t{Term.n}"
        self.w, self.h = w, h
        # 가짜 smi 를 PATH 앞에 둔 셸 — fake()/fake_all() 로 상황을 바꾸지 않으면 '정상 1장' 이 기본
        fake_env = [] if REAL else [f"PATH={FAKENPU}:{FAKEBIN}:{os.environ.get('PATH', '')}",
                                    "FAKE_SMI=one", "FAKE_NPU=ok"]
        tmux("new-session", "-d", "-s", self.name, "-x", str(w), "-y", str(h),
             "env", "PS1=PROMPT$ ", *fake_env, "bash", "--norc", "--noprofile")
        tmux("set-option", "-t", self.name, "window-size", "manual")
        tmux("resize-window", "-t", self.name, "-x", str(w), "-y", str(h))
        time.sleep(0.4)

    def send(self, *keys: str) -> None:
        tmux("send-keys", "-t", self.name, *keys)

    def type(self, text: str) -> None:
        tmux("send-keys", "-t", self.name, "-l", text)

    def hexkeys(self, *hexbytes: str) -> None:
        tmux("send-keys", "-t", self.name, "-H", *hexbytes)

    def run(self, cmd: str) -> None:
        self.type(cmd)
        self.send("Enter")

    def screen(self, ansi: bool = False) -> str:
        return tmux("capture-pane", "-t", self.name, "-p", *(["-e"] if ansi else []))

    def wait_for(self, pattern: str, timeout: float = 6.0, absent: bool = False) -> tuple[bool, float, str]:
        """화면에 pattern 이 나타날(absent 면 사라질) 때까지 기다린다 → (성공, 걸린 초, 마지막 화면)."""
        t0 = time.monotonic()
        scr = ""
        while time.monotonic() - t0 < timeout:
            scr = self.screen()
            found = re.search(pattern, scr) is not None
            if found != absent:
                return True, time.monotonic() - t0, scr
            time.sleep(0.02)
        return False, time.monotonic() - t0, scr

    def resize(self, w: int, h: int) -> None:
        self.w, self.h = w, h
        tmux("resize-window", "-t", self.name, "-x", str(w), "-y", str(h))

    def pane_pid(self) -> int:
        return int(tmux("display-message", "-t", self.name, "-p", "#{pane_pid}").strip())

    def kill(self) -> None:
        tmux("kill-session", "-t", self.name, check=False)


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""), flush=True)
    return bool(ok)


def child_pid(shell_pid: int, pattern: str = "ntop") -> int | None:
    out = subprocess.run(["pgrep", "-P", str(shell_pid)], capture_output=True, text=True).stdout.split()
    return int(out[0]) if out else None


def stty(t: Term, tag: str) -> str:
    """셸에서 stty -a 를 찍어 터미널 설정을 문자열로 가져온다."""
    path = os.path.join(TMP, f"stty-{t.name}-{tag}.txt")
    t.run(f"stty -a > {path}; echo STTY-{tag}-DONE")
    t.wait_for(f"STTY-{tag}-DONE\n")
    time.sleep(0.1)
    with open(path) as f:
        s = f.read()
    os.unlink(path)
    return s


OVERVIEW = r"NPU Devices"
DETAIL = r"load \d+\.\d+"        # 둘째 화면의 CPU 요약에만 load average 가 나온다
NUMA_NODES = len([d for d in os.listdir("/sys/devices/system/node")
                  if re.fullmatch(r"node\d+", d)]) if os.path.isdir("/sys/devices/system/node") else 0


# ───────────────────────── 시험들 ─────────────────────────
def test_pages():
    """첫 화면 구성, →/← 로 화면 전환, 양 끝에서 멈춤, 응답 시간."""
    t = Term(160, 45)
    try:
        t.run(NCTOP)
        ok, dt, scr = t.wait_for(OVERVIEW)
        check("첫 화면이 뜬다", ok, f"{dt:.2f}s")
        t.wait_for(r"gpu0")
        scr = t.screen()
        check("첫 화면에 GPU 표", "GPU Devices" in scr and "gpu0" in scr and "RTX PRO 6000" in scr)
        check("첫 화면에 CPU 요약 줄", re.search(r"CPU\s+[\d.]+%\s+·\s+RAM", scr) is not None)
        check("첫 화면에 코어 그리드 없음", re.search(r"c\s*\d+:\s*\d+%\s+c\s*\d+:\s*\d+%\s+c\s*\d+:\s*\d+%\s+c\s*\d+:\s*\d+%\s+c\s*\d+:\s*\d+%", scr) is None)
        check("화면 탭과 키 안내", "1 Overview" in scr and "2 Detail" in scr and "←/→: page" in scr)
        check("프로세스 패널에 GPU 열", re.search(r"ETIME\s+GPU\s+CMD", scr) is not None)

        t.send("Right")
        ok, dt, scr = t.wait_for(DETAIL)
        check("→ 로 둘째 화면", ok, f"{dt*1000:.0f}ms")
        check("→ 응답 0.3초 이내", dt < 0.3, f"{dt*1000:.0f}ms")
        check("둘째 화면: 코어 그리드 + GPU 상세",
              re.search(r"c\s*0:\s*\d+%", scr) is not None and "gpu0  ·  NVIDIA" in scr
              and "Util" in scr and "GPU-MEM" in scr and "NPU Devices" not in scr)
        if NUMA_NODES >= 2:
            check("둘째 화면: NUMA 노드별 묶음", "NUMA node0" in scr and "NUMA node1" in scr)

        t.send("Right")
        time.sleep(0.4)
        check("끝에서 → 는 그대로", bool(re.search(DETAIL, t.screen())))
        t.send("Left")
        ok, dt, scr = t.wait_for(OVERVIEW)
        check("← 로 첫 화면", ok, f"{dt*1000:.0f}ms")
        t.send("Left")
        time.sleep(0.4)
        check("처음에서 ← 는 그대로", OVERVIEW in t.screen())

        # 다른 키들
        for key, want, label in (("l", DETAIL, "l"), ("h", OVERVIEW, "h"), ("Tab", DETAIL, "Tab"),
                                 ("BTab", OVERVIEW, "Shift+Tab"), ("2", DETAIL, "2"), ("1", OVERVIEW, "1")):
            t.send(key)
            ok, dt, _ = t.wait_for(want)
            check(f"키 {label}", ok, f"{dt*1000:.0f}ms")
        # application cursor 모드의 화살표 (ESC O C / ESC O D)
        t.hexkeys("1b", "4f", "43")
        ok, _, _ = t.wait_for(DETAIL)
        check("ESC O C (application 모드 →)", ok)
        t.hexkeys("1b", "4f", "44")
        ok, _, _ = t.wait_for(OVERVIEW)
        check("ESC O D (application 모드 ←)", ok)
        # 수식키 붙은 화살표 (Ctrl+→ = ESC [ 1 ; 5 C)
        t.hexkeys("1b", "5b", "31", "3b", "35", "43")
        ok, _, _ = t.wait_for(DETAIL)
        check("ESC [ 1;5 C (Ctrl+→)", ok)
        t.send("Left")
        t.wait_for(OVERVIEW)
        # 모르는 키는 무시
        t.send("Up", "Down", "x", "PageUp", "F5")
        time.sleep(0.4)
        scr = t.screen()
        check("모르는 키는 무시", OVERVIEW in scr and "Traceback" not in scr)
    finally:
        t.kill()


def test_quit_restores_tty():
    """q·Ctrl+C·SIGTERM 으로 나간 뒤 터미널 설정이 원래대로인지."""
    for how in ("q", "ctrl-c", "sigterm", "hangul-q"):
        t = Term(140, 40)
        try:
            before = stty(t, "before")
            t.run(NCTOP)
            ok, _, _ = t.wait_for(OVERVIEW)
            if not ok:
                check(f"[{how}] 뜬다", False)
                continue
            time.sleep(0.5)
            if how == "q":
                t.send("q")
            elif how == "hangul-q":
                t.type("ㅂ")
            elif how == "ctrl-c":
                t.send("C-c")
            else:
                pid = child_pid(t.pane_pid())
                os.kill(pid, 15)
            if how == "sigterm":
                ok, dt, scr = t.wait_for(r"Terminated\s*.*\nPROMPT\$")
                check(f"[{how}] 시그널로 끝남(bye 없음)", ok and "bye" not in scr, f"{dt*1000:.0f}ms")
                t.run("echo RC=$?")
                ok, _, scr = t.wait_for(r"RC=\d+\n")
                check(f"[{how}] 종료 코드 143", "RC=143" in scr)
            else:
                ok, dt, scr = t.wait_for(r"\[nctop\] bye\.")
                check(f"[{how}] 종료 인사", ok, f"{dt*1000:.0f}ms")
                ok, _, scr = t.wait_for(r"\[nctop\] bye\.\nPROMPT\$")
                t.run("echo RC=$?")
                t.wait_for(r"RC=\d+\n")
                check(f"[{how}] 종료 코드 0", "RC=0" in t.screen())
            scr = t.screen()
            check(f"[{how}] 원래 화면으로 복귀(대체 화면 해제)", OVERVIEW not in scr)
            after = stty(t, "after")
            check(f"[{how}] stty 설정 동일", before == after,
                  "" if before == after else f"before/after 다름")
            check(f"[{how}] icanon·echo 켜짐", " icanon" in after and " echo " in after and "-icanon" not in after)
            # 에코가 실제로 되는지
            t.run("echo ECHO-OK")
            ok, _, scr = t.wait_for(r"PROMPT\$ echo ECHO-OK\nECHO-OK")
            check(f"[{how}] 셸 입력 에코 정상", ok)
        finally:
            t.kill()


def test_esc_alone():
    """Esc 만 누른 뒤의 q 가 Alt+q 로 먹히지 않고 종료되는지."""
    t = Term(140, 40)
    try:
        t.run(NCTOP)
        t.wait_for(OVERVIEW)
        t.send("Escape")
        time.sleep(0.5)
        check("Esc 만 눌러도 그대로", OVERVIEW in t.screen())
        t.send("q")
        ok, _, _ = t.wait_for(r"\[nctop\] bye\.")
        check("Esc 뒤 q 로 종료", ok)
    finally:
        t.kill()


def test_resize():
    """창 크기를 바꾸면 바로 다시 그린다."""
    t = Term(160, 45)
    try:
        t.run(NCTOP)
        t.wait_for(OVERVIEW)
        time.sleep(0.5)
        t.resize(100, 30)
        t0 = time.monotonic()
        ok = False
        while time.monotonic() - t0 < 3:
            lines = t.screen().split("\n")
            # 머리 패널 첫 줄이 새 폭(100칸)에 맞춰졌는가
            if lines and len(lines[0]) == 100 and lines[0].endswith("╮"):
                ok = True
                break
            time.sleep(0.02)
        check("크기 변경 뒤 새 폭으로 다시 그림", ok, f"{(time.monotonic()-t0)*1000:.0f}ms")
        scr = t.screen()
        check("100x30 에서도 GPU 표가 보임", "GPU Devices" in scr and "gpu0" in scr)
        t.send("Right")
        ok, _, scr = t.wait_for(r"gpu0  ·  NVIDIA")
        check("100x30 둘째 화면에 GPU 상세가 보임", ok)
        t.send("q")
        t.wait_for(r"bye")
    finally:
        t.kill()


def test_small():
    """작은 터미널(80x24): 깨지지 않고, 둘째 화면은 코어를 한 칸 막대로 줄여 GPU 가 보인다."""
    t = Term(80, 24)
    try:
        t.run(NCTOP)
        ok, _, scr = t.wait_for(OVERVIEW)
        check("80x24 첫 화면", ok and "Traceback" not in scr)
        t.wait_for("gpu0")
        scr = t.screen()
        check("80x24 첫 화면에 GPU 줄", "gpu0" in scr)
        lines = scr.split("\n")
        check("80x24 줄이 폭을 안 넘음", all(len(l) <= 80 for l in lines), str(max(len(l) for l in lines)))
        t.send("Right")
        ok, _, scr = t.wait_for(DETAIL)
        check("80x24 둘째 화면", ok)
        check("80x24 둘째 화면: 한 칸 막대(▁)로 줄임", "▁" in scr and re.search(r"c\s*0:\s*\d+%", scr) is None)
        check("80x24 둘째 화면: GPU 상세가 보임", "gpu0" in scr and "Util" in scr and "Memory" in scr)
        t.send("q")
        t.wait_for(r"bye")
    finally:
        t.kill()


def test_variants():
    """ntop(NPU 만), --no-gpu(예전 배치), --no-ps, --raw, --gpu, -p 2."""
    t = Term(160, 45)
    try:
        # ntop: 화면 하나, 탭 없음, 화살표 무시
        t.run(NTOP)
        ok, _, scr = t.wait_for(OVERVIEW)
        time.sleep(0.6)
        scr = t.screen()
        check("ntop: NPU 만", ok and "GPU Devices" not in scr and "CPU (" not in scr)
        check("ntop: 탭 없음", "Overview" not in scr and "←/→" not in scr and "q/Ctrl+C: quit" in scr)
        check("ntop: 프로세스 패널에 GPU 열 없음", "Top NPU-related host processes" in scr
              and re.search(r"ETIME\s+CMD", scr) is not None)
        t.send("Right")
        time.sleep(0.4)
        check("ntop: → 는 무시", OVERVIEW in t.screen())
        t.send("q")
        ok, _, _ = t.wait_for(r"\[ntop\] bye\.")
        check("ntop: q 종료", ok)

        # ntop --gpu: GPU 만 켬 → 둘째 화면은 GPU 상세만
        t.run("clear; " + NTOP + " --gpu")
        ok, _, scr = t.wait_for("GPU Devices")
        check("ntop --gpu: GPU 표", ok and "CPU (" not in scr)
        t.send("Right")
        ok, _, scr = t.wait_for(r"gpu0  ·  NVIDIA")
        check("ntop --gpu: 둘째 화면은 GPU 상세만", ok and "NUMA" not in scr)
        t.send("q")
        t.wait_for(r"bye")

        # nctop --no-gpu: 첫 화면에 예전처럼 코어 그리드
        t.run("clear; " + NCTOP + " --no-gpu")
        ok, _, scr = t.wait_for(r"c\s*0:\s*\d+%")
        check("--no-gpu: 첫 화면에 코어 그리드(예전 배치)", ok and "GPU Devices" not in scr and OVERVIEW in scr)
        check("--no-gpu: 프로세스 패널 예전 제목", "Top NPU-related host processes" in scr)
        t.send("Right")
        ok, _, scr = t.wait_for(DETAIL)
        check("--no-gpu: 둘째 화면은 코어만", ok and "gpu0" not in scr)
        t.send("q")
        t.wait_for(r"bye")

        # --no-ps
        t.run("clear; " + NCTOP + " --no-ps")
        ok, _, scr = t.wait_for("GPU Devices")
        time.sleep(0.5)
        scr = t.screen()
        check("--no-ps: 프로세스 패널 없음", ok and "Processes ─" not in scr and "host processes" not in scr)
        t.send("q")
        t.wait_for(r"bye")

        # --raw
        t.run("clear; " + NCTOP + " --raw")
        ok, _, scr = t.wait_for(r"raw JSON")
        check("--raw: 원본 패널", ok and "=== status ===" in scr)
        t.send("q")
        t.wait_for(r"bye")

        # -p 2: 둘째 화면에서 시작
        t.run("clear; " + NCTOP + " -p 2")
        ok, _, scr = t.wait_for(DETAIL)
        check("-p 2: 둘째 화면에서 시작", ok and OVERVIEW not in scr)
        t.send("q")
        t.wait_for(r"bye")

        # -p 9: 범위 밖은 마지막 화면
        t.run("clear; " + NCTOP + " -p 9")
        ok, _, scr = t.wait_for(DETAIL)
        check("-p 9: 마지막 화면으로", ok)
        t.send("q")
        t.wait_for(r"bye")
    finally:
        t.kill()


def test_no_tty_stdin():
    """stdin 이 터미널이 아니면 키 없이 예전처럼 돈다."""
    t = Term(140, 40)
    try:
        t.run(NCTOP + " < /dev/null")
        ok, _, scr = t.wait_for(OVERVIEW)
        time.sleep(1.2)
        scr = t.screen()
        check("stdin=/dev/null: 뜬다", ok and "Traceback" not in scr)
        check("stdin=/dev/null: 키 안내 대신 Ctrl+C 안내", "←/→" not in scr and "Ctrl+C: quit" in scr and "q/Ctrl+C" not in scr)
        pid = child_pid(t.pane_pid())
        # CPU 를 태우며 헛돌지 않는가 (EOF 를 계속 읽는 바쁜 루프 방지)
        def cpu_ticks():
            with open(f"/proc/{pid}/stat") as f:
                p = f.read().rsplit(")", 1)[1].split()
            return int(p[11]) + int(p[12])
        a = cpu_ticks(); time.sleep(2.0); b = cpu_ticks()
        check("stdin=/dev/null: 헛돌지 않음", (b - a) < 60, f"{b-a} ticks / 2s")
        t.send("C-c")
        ok, _, _ = t.wait_for(r"bye")
        check("stdin=/dev/null: Ctrl+C 종료", ok)
    finally:
        t.kill()


def test_suspend_resume():
    """Ctrl+Z 로 멈췄다가 fg 로 돌아와도 키가 먹는다."""
    t = Term(140, 40)
    try:
        t.run(NCTOP)
        t.wait_for(OVERVIEW)
        time.sleep(0.5)
        t.send("C-z")
        ok, _, scr = t.wait_for(r"Stopped")
        check("Ctrl+Z 로 멈춤", ok)
        check("Ctrl+Z: 원래 화면으로", OVERVIEW not in scr)
        t.run("echo SHELL-ALIVE")
        ok, _, _ = t.wait_for(r"SHELL-ALIVE\n")
        check("멈춘 동안 셸 입력 정상", ok)
        t.run("fg")
        time.sleep(1.2)
        t.send("Right")
        ok, dt, scr = t.wait_for(DETAIL)
        check("fg 뒤 → 가 먹는다", ok, f"{dt*1000:.0f}ms")
        check("fg 뒤 화면에 키 찌꺼기(^[[C) 없음", "^[[C" not in scr)
        t.send("q")
        ok, _, _ = t.wait_for(r"bye")
        check("fg 뒤 q 종료", ok)
    finally:
        t.kill()


def test_key_storm():
    """키를 빠르게 연달아 눌러도 안 죽고 마지막 상태가 맞다."""
    t = Term(160, 45)
    try:
        t.run(NCTOP)
        t.wait_for(OVERVIEW)
        time.sleep(0.5)
        for _ in range(40):
            t.send("Right", "Left")
        t.send("Right")
        ok, _, scr = t.wait_for(DETAIL)
        check("연타 뒤 마지막 상태(둘째 화면)", ok and "Traceback" not in scr)
        pid = child_pid(t.pane_pid())
        check("연타 뒤 살아 있음", pid is not None)
        t.send("q")
        ok, _, _ = t.wait_for(r"bye")
        check("연타 뒤 q 종료", ok)
    finally:
        t.kill()


def test_cpu_cost():
    """자기 자신이 쓰는 CPU (하위 smi 프로세스 포함, 10초 평균). 실제 smi 일 때만 뜻이 있다."""
    if not REAL:
        print("  (건너뜀: NCTOP_E2E_REAL=1 일 때만 잰다)")
        return
    t = Term(160, 45)
    try:
        t.run(NCTOP)
        t.wait_for(OVERVIEW)
        time.sleep(1.0)
        pid = child_pid(t.pane_pid())

        def ticks():
            with open(f"/proc/{pid}/stat") as f:
                p = f.read().rsplit(")", 1)[1].split()
            return int(p[11]) + int(p[12]), int(p[13]) + int(p[14])    # 자신, 끝난 자식들
        a = ticks(); time.sleep(10.0); b = ticks()
        hz = os.sysconf("SC_CLK_TCK")
        own = (b[0] - a[0]) / hz / 10 * 100
        kids = (b[1] - a[1]) / hz / 10 * 100
        check("자기 CPU 사용 (참고)", own < 25, f"본체 {own:.1f}% + smi 자식 {kids:.1f}% (코어 하나 기준)")
        t.send("q")
        t.wait_for(r"bye")
    finally:
        t.kill()






def fake(mode: str, cmd: str) -> str:
    """가짜 nvidia-smi 를 PATH 앞에 둔 명령줄."""
    return f"FAKE_SMI={mode} PATH={FAKEBIN}:$PATH {cmd}"


def fake_all(cmd: str, gpu: str = "one", npu: str = "ok") -> str:
    """nvidia-smi 와 furiosa-smi 둘 다 가짜로 — 실제 장치를 두드리지 않는다.
    gpu: one|multi|old|down|hang|slowpmon,  npu: ok|hang|none|fail"""
    return f"FAKE_NPU={npu} FAKE_SMI={gpu} PATH={FAKENPU}:{FAKEBIN}:$PATH {cmd}"


def test_smi_hang():
    """nvidia-smi 가 답이 없어도: 첫 화면이 바로 뜨고, NPU 는 계속 갱신되고, 키가 먹고, GPU 칸에 사정이 나온다."""
    t = Term(160, 45)
    try:
        t0 = time.monotonic()
        t.run(fake("hang", NCTOP))
        ok, dt, scr = t.wait_for(OVERVIEW)
        check("[hang] 첫 화면이 2초 안에", ok and dt < 2.0, f"{dt:.2f}s")
        ok, _, scr = t.wait_for(r"nvidia-smi 응답 대기 중")
        check("[hang] GPU 칸에 '응답 대기 중'", ok)
        # 수집이 살아 있는가: 3초 동안 시계가 매초 바뀌고 'NPU 데이터 N초 전' 경고가 없다
        stamps, stale = set(), False
        t1 = time.monotonic()
        while time.monotonic() - t1 < 3.0:
            scr = t.screen()
            m = re.search(r"\d\d:\d\d:\d\d", scr)
            if m:
                stamps.add(m.group(0))
            stale = stale or "초 전" in scr
            time.sleep(0.1)
        check("[hang] 화면이 계속 갱신됨", len(stamps) >= 3 and not stale, f"시각 {len(stamps)}개, stale={stale}")
        ok, dt, _ = t.wait_for(r"nvidia-smi 응답 없음 \(3s 초과\)", timeout=8)
        check("[hang] 3초 뒤 '응답 없음'", ok, f"{dt:.1f}s")
        t.send("Right")
        ok, dt, scr = t.wait_for(DETAIL)
        check("[hang] 멈춘 동안에도 → 응답 0.3초 이내", ok and dt < 0.3, f"{dt*1000:.0f}ms")
        check("[hang] 둘째 화면에도 사정 표시", "nvidia-smi 응답" in scr)
        t.send("q")
        ok, dt, _ = t.wait_for(r"bye")
        check("[hang] q 종료가 바로 됨", ok and dt < 1.0, f"{dt*1000:.0f}ms")
    finally:
        t.kill()


def test_smi_down():
    t = Term(160, 45)
    try:
        t.run(fake("down", NCTOP))
        ok, _, scr = t.wait_for(r"NVIDIA-SMI has failed")
        check("[down] 첫 화면 GPU 칸에 드라이버 오류", ok and OVERVIEW in scr)
        lines = scr.split("\n")
        check("[down] 오류 줄이 폭을 안 넘음", all(len(l) <= 160 for l in lines))
        t.send("Right")
        ok, _, scr = t.wait_for(DETAIL)
        check("[down] 둘째 화면에도 오류", ok and "NVIDIA-SMI has failed" in scr)
        t.send("q")
        t.wait_for(r"bye")
    finally:
        t.kill()


def test_smi_old():
    t = Term(160, 45)
    try:
        t.run(fake("old", NCTOP))
        ok, _, scr = t.wait_for(r"Tesla V100")
        check("[old] 모르는 필드를 빼고 GPU 표가 나옴", ok and "12.0%" in scr)
        t.send("Right")
        ok, _, scr = t.wait_for(r"gpu0  ·  Tesla V100")
        check("[old] 둘째 화면", ok)
        check("[old] 없는 값은 안 보임(jpeg·T.Limit·reserved·throttle)",
              "jpeg" not in scr and "T.Limit" not in scr and "reserved" not in scr and "throttle" not in scr)
        check("[old] 있는 값은 보임", re.search(r"mem I/O\s+5%", scr) is not None and "120.0/600W" in scr and "Gen4 x16" in scr
              and "470.00" in scr)
        check("[old] 옛 pmon 형식의 프로세스", re.search(r"C\s+1\.0G\s+55\s+20\s+-\s+-", scr) is not None)
        t.send("q")
        t.wait_for(r"bye")
    finally:
        t.kill()


def test_smi_multi():
    t = Term(200, 60)
    try:
        t.run(fake("multi", NCTOP))
        ok, _, scr = t.wait_for(r"gpu3")
        check("[multi] 첫 화면에 GPU 4줄", ok and all(f"gpu{i}" in scr for i in range(4)))
        check("[multi] 부하 값", "97.0%" in scr and "87.9/96G" in scr and "88.0°C" in scr and "571W" in scr)
        check("[multi] 프로세스 요약", re.search(r"gpu0 .*78\.1G, .* 4M", scr) is not None)
        check("[multi] 내 smi 자식은 프로세스 패널에 안 나옴", "furiosa-smi status" not in scr and "nvidia-smi" not in scr)
        check("[multi] 프로세스 패널에 GPU 메모리", re.search(r"\d+ \w+\s+[\d.]+%\s+[\d.]+%\s+\S+\s+78\.1G", scr) is not None)
        lines = scr.split("\n")
        check("[multi] 60줄 안에 다 들어감", len([l for l in lines if l.strip()]) <= 60 and "Processes" in scr)
        t.send("Right")
        ok, _, scr = t.wait_for(r"gpu0  ·  NVIDIA")
        check("[multi] 둘째 화면 GPU 상세", ok and "gpu1  ·  NVIDIA" in scr)
        check("[multi] 스로틀·ECC 경고", "throttle sw power cap, hw thermal" in scr and "2 uncorrected" in scr)
        check("[multi] 프로세스별 사용률", re.search(r"C\s+78\.1G\s+87\s+41", scr) is not None)
        t.send("q")
        t.wait_for(r"bye")
    finally:
        t.kill()
    # 작은 터미널에서 GPU 4장
    t = Term(120, 40)
    try:
        t.run(fake("multi", NCTOP))
        ok, _, scr = t.wait_for(r"gpu3")
        check("[multi 120x40] 첫 화면에 GPU 4줄", ok)
        t.send("Right")
        ok, _, scr = t.wait_for(r"gpu0  ·  NVIDIA")
        check("[multi 120x40] 둘째 화면", ok and "Traceback" not in scr)
        t.send("q")
        t.wait_for(r"bye")
    finally:
        t.kill()


def test_smi_slowpmon():
    """pmon 만 멈춰도 GPU 상태는 계속 나오고, 프로세스 칸에 사정이 나온다."""
    t = Term(160, 45)
    try:
        t.run(fake("slowpmon", NCTOP))
        ok, dt, scr = t.wait_for(r"gpu0\s*│RTX PRO 6000")
        check("[slowpmon] GPU 상태는 바로 나옴", ok and dt < 2.0, f"{dt:.2f}s")
        ok, _, scr = t.wait_for(r"nvidia-smi 응답 (대기 중|없음)")
        check("[slowpmon] 프로세스 칸에 사정 표시", ok)
        ok, _, scr = t.wait_for(r"furiosa-llm|furiosa_router|\(none\)", timeout=8)
        check("[slowpmon] ps 패널은 pmon 을 4초만 기다리고 나옴", ok)
        t.send("q")
        t.wait_for(r"bye")
    finally:
        t.kill()


def pstate(pid: int) -> str:
    """프로세스 상태 글자 (T = 멈춤). 없으면 'gone'."""
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0]
    except OSError:
        return "gone"


def wait_state(pid: int, want: str, timeout: float = 3.0) -> bool:
    """want='T' 면 멈출 때까지, 'run' 이면 멈춤이 풀릴 때까지, 'gone' 이면 사라질 때까지."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        st = pstate(pid)
        if want == "gone":
            if st == "gone":
                return True
        elif st != "gone" and (st == "T") == (want == "T"):
            return True
        time.sleep(0.02)
    return False


def children_of(pid: int) -> list[str]:
    out = subprocess.run(["ps", "-o", "pid=,args=", "--ppid", str(pid)], capture_output=True, text=True).stdout
    return [l.strip() for l in out.splitlines() if l.strip()]


def test_jobs():
    """작업 제어: Ctrl+Z 는 원래 화면을 돌려주고 멈춘다. 배경에서는 그리지도 읽지도 않는다. fg 로 돌아오면 다시 된다."""
    t = Term(140, 40)
    try:
        before = stty(t, "before")
        t.run("clear; " + fake_all(NCTOP))
        t.wait_for(OVERVIEW)
        time.sleep(1.0)
        pid = child_pid(t.pane_pid())

        # Ctrl+Z
        t.send("C-z")
        check("Ctrl+Z 로 멈춤", wait_state(pid, "T"))
        ok, _, scr = t.wait_for(r"Stopped")
        check("멈추면 원래 화면(대체 화면 해제)", ok and OVERVIEW not in scr and "GPU Devices" not in scr)
        mid = stty(t, "mid")
        check("멈춘 동안 stty 가 처음과 같음", mid == before)
        t.run("echo SHELL-OK")
        ok, _, _ = t.wait_for(r"PROMPT\$ echo SHELL-OK\nSHELL-OK")
        check("멈춘 동안 셸 입력·에코 정상", ok)

        # bg — 돌기는 하되 그리지 않고, 셸에 타자해도 멈추지 않는다
        t.run("clear; bg")
        check("bg 로 다시 돎", wait_state(pid, "run"))
        time.sleep(2.0)
        scr = t.screen()
        check("배경에서는 화면에 안 그림", OVERVIEW not in scr and "nctop  ·" not in scr)
        t.run("echo TYPED-IN-SHELL")
        ok, _, scr = t.wait_for(r"TYPED-IN-SHELL\n")
        time.sleep(0.8)
        check("배경에서 셸에 타자해도 안 멈춤(SIGTTIN 없음)", pstate(pid) not in ("T", "gone"), pstate(pid))
        kids = children_of(pid)
        time.sleep(1.5)
        check("배경에서는 수집도 쉼", children_of(pid) == [] and kids == [], f"{kids}")

        # fg — 화면과 키가 돌아온다
        t.run("fg")
        ok, dt, _ = t.wait_for(OVERVIEW)
        check("fg 로 화면이 돌아옴", ok, f"{dt*1000:.0f}ms")
        time.sleep(0.5)
        t.send("Right")
        ok, dt, scr = t.wait_for(DETAIL, timeout=3)
        check("fg 뒤 → 가 먹음", ok, f"{dt*1000:.0f}ms")
        check("fg 뒤 키 찌꺼기(^[[C) 없음", "^[[C" not in scr)

        # 되풀이: 멈춘 사이 가짜 시간 초과 오류가 번쩍이지 않는다
        flashes = 0
        for rep_ in range(5):
            t.send("C-z")
            wait_state(pid, "T")
            time.sleep(3.6)
            t.run("fg")
            wait_state(pid, "run")
            t0 = time.monotonic()
            while time.monotonic() - t0 < 1.6:
                scr = t.screen()
                if bool(re.search(DETAIL, scr)) and ("no NPU" in scr or "응답 없음" in scr or "초 전" in scr):
                    flashes += 1
                    break
                time.sleep(0.03)
            time.sleep(0.15 + 0.09 * rep_)
        check("Ctrl+Z→fg 5번: 가짜 오류가 번쩍이지 않음", flashes == 0, f"{flashes}/5")
        t.send("q")
        ok, _, _ = t.wait_for(r"bye\.\nPROMPT\$")
        check("q 종료", ok)
        check("끝난 뒤 stty 동일", stty(t, "after") == before)
    finally:
        t.kill()

    # 배경으로 시작(nctop &) → fg
    t = Term(140, 40)
    try:
        before = stty(t, "before")
        t.run("clear; " + fake_all(NCTOP) + " &")
        time.sleep(2.5)
        pid = child_pid(t.pane_pid())
        scr = t.screen()
        check("nctop &: 배경에서는 안 그림", OVERVIEW not in scr and pid is not None and pstate(pid) != "T", pstate(pid) if pid else "no pid")
        check("nctop &: 셸의 stty 를 안 건드림", stty(t, "bg") == before)
        kids = children_of(pid)
        time.sleep(1.2)
        check("nctop &: 배경에서는 수집도 쉼", kids == [] and children_of(pid) == [], f"{kids}")
        t.run("fg")
        ok, dt, scr = t.wait_for(OVERVIEW)
        check("nctop & → fg: 화면이 뜸", ok, f"{dt*1000:.0f}ms")
        ok, _, scr = t.wait_for(r"←/→: page")
        check("nctop & → fg: 키 안내가 켜짐", ok)
        t.send("Right")
        ok, dt, _ = t.wait_for(DETAIL, timeout=3)
        check("nctop & → fg: → 가 먹음", ok, f"{dt*1000:.0f}ms")
        t.send("q")
        ok, _, _ = t.wait_for(r"bye\.\nPROMPT\$")
        check("nctop & → fg: q 종료", ok)
        check("nctop & → fg: 끝난 뒤 stty 동일", stty(t, "after") == before)

        # 배경에 둔 채 SIGTERM
        t.run("clear; " + fake_all(NCTOP))
        t.wait_for(OVERVIEW)
        time.sleep(0.8)
        pid = child_pid(t.pane_pid())
        t.send("C-z")
        wait_state(pid, "T")
        t.run("bg")
        wait_state(pid, "run")
        time.sleep(0.8)
        os.kill(pid, 15)
        check("배경에서 SIGTERM: 끝남", wait_state(pid, "gone", 3.0), pstate(pid))
        t.send("Enter")
        time.sleep(0.4)
        check("배경에서 SIGTERM: 셸 stty 그대로", stty(t, "after2") == before)

        # 멈춘 채 SIGTERM + SIGCONT (kill %1 이 하는 일)
        t.run("clear; " + fake_all(NCTOP))
        t.wait_for(OVERVIEW)
        time.sleep(0.8)
        pid = child_pid(t.pane_pid())
        t.send("C-z")
        wait_state(pid, "T")
        os.kill(pid, 15)
        os.kill(pid, 18)
        check("멈춘 채 SIGTERM: 끝남", wait_state(pid, "gone", 3.0), pstate(pid))
        t.send("Enter")
        time.sleep(0.4)
        scr = t.screen()
        check("멈춘 채 SIGTERM: 화면을 안 건드림", OVERVIEW not in scr)
        check("멈춘 채 SIGTERM: 셸 stty 그대로", stty(t, "after3") == before)
    finally:
        t.kill()


def test_signals():
    """SIGHUP(터미널이 사라짐)·SIGWINCH·SIGSTOP."""
    # 창을 닫으면(SIGHUP) 프로세스와 하위 smi 가 남지 않는다
    t = Term(140, 40)
    pid = None
    try:
        t.run(fake_all(NCTOP, gpu="hang"))
        t.wait_for(OVERVIEW)
        time.sleep(1.0)
        pid = child_pid(t.pane_pid())
        kids = [int(k.split()[0]) for k in children_of(pid)]
        check("[hup] 멈춘 nvidia-smi 자식이 돌고 있음(전제)", len(kids) >= 1, f"{len(kids)}개")
    finally:
        t.kill()                             # 창을 죽인다 → SIGHUP
    if pid:
        check("[hup] 창을 닫으면 끝남", wait_state(pid, "gone", 4.0), pstate(pid))
        time.sleep(0.5)
        left = [k for k in kids if pstate(k) != "gone"]
        check("[hup] 하위 smi 가 남지 않음", left == [], f"{left}")

    # kill -HUP: 터미널을 되돌리고 같은 시그널로 끝난다 (종료 코드 129)
    t = Term(140, 40)
    try:
        before = stty(t, "before")
        t.run(fake_all(NCTOP) + "; echo RC=$?")
        t.wait_for(OVERVIEW)
        time.sleep(0.8)
        os.kill(child_pid(t.pane_pid()), 1)
        ok, _, scr = t.wait_for(r"RC=\d+\n")
        check("[hup-rc] 종료 코드 129, bye 없음", ok and "RC=129" in scr and "bye" not in scr and OVERVIEW not in scr)
        check("[hup-rc] stty 동일", stty(t, "after") == before)
    finally:
        t.kill()

    # SIGSTOP(잡을 수 없는 멈춤) 뒤 fg
    t = Term(140, 40)
    try:
        t.run(fake_all(NCTOP))
        t.wait_for(OVERVIEW)
        time.sleep(0.8)
        pid = child_pid(t.pane_pid())
        os.kill(pid, 19)
        check("[stop] SIGSTOP 으로 멈춤", wait_state(pid, "T"))
        time.sleep(0.5)
        t.run("fg")
        wait_state(pid, "run")
        time.sleep(1.2)
        t.send("Right")
        ok, dt, scr = t.wait_for(DETAIL, timeout=3)
        check("[stop] fg 뒤 → 가 먹음", ok, f"{dt*1000:.0f}ms")
        check("[stop] fg 뒤 키 찌꺼기 없음", "^[[C" not in scr)
        t.send("q")
        ok, _, _ = t.wait_for(r"bye")
        check("[stop] q 종료", ok)
    finally:
        t.kill()


def test_orphans():
    """끝낼 때 도는 중이던(멈춘) smi 자식을 정리한다."""
    for how in ("q", "ctrl-c"):
        t = Term(140, 40)
        try:
            t.run(fake_all(NCTOP, gpu="hang"))
            t.wait_for(OVERVIEW)
            time.sleep(1.2)
            pid = child_pid(t.pane_pid())
            kids = [int(k.split()[0]) for k in children_of(pid)]
            check(f"[orphans {how}] 멈춘 nvidia-smi 자식이 돌고 있음(전제)", len(kids) >= 1, f"{len(kids)}개")
            t.send("q" if how == "q" else "C-c")
            ok, _, _ = t.wait_for(r"bye")
            time.sleep(0.6)
            left = [k for k in kids if pstate(k) != "gone"]
            check(f"[orphans {how}] 끝난 뒤 smi 자식이 남지 않음", ok and left == [], f"{left}")
        finally:
            t.kill()


def test_tostop():
    """`stty tostop` 셸: 배경 작업이 터미널에 쓰면 멈춘다 — 배경에서 끝나거나 화면을 끌 때 멈춰 남지 않는다."""
    t = Term(140, 40)
    try:
        t.run("stty tostop")
        # 배경으로 띄우고 SIGINT
        t.run("clear; " + fake_all(NCTOP) + " &")
        time.sleep(2.0)
        pid = child_pid(t.pane_pid())
        check("[tostop] nctop &: 도는 중", pid is not None and pstate(pid) not in ("T", "gone"), pstate(pid) if pid else "no pid")
        os.kill(pid, 2)
        check("[tostop] 배경에서 SIGINT: 멈추지 않고 끝남", wait_state(pid, "gone", 3.0), pstate(pid))
        t.send("Enter")
        time.sleep(0.4)
        check("[tostop] 배경에서 끝날 때 bye 를 안 끼워 넣음", "bye" not in t.screen())

        # 화면이 떠 있는 중 SIGSTOP → bg: 그리지 않고 계속 돈다
        t.run("clear; " + fake_all(NCTOP))
        t.wait_for(OVERVIEW)
        time.sleep(0.8)
        pid = child_pid(t.pane_pid())
        os.kill(pid, 19)
        wait_state(pid, "T")
        time.sleep(0.4)
        t.run("bg")
        wait_state(pid, "run")
        time.sleep(2.0)
        check("[tostop] SIGSTOP → bg: 다시 멈추지 않음", pstate(pid) not in ("T", "gone"), pstate(pid))
        t.run("fg")
        ok, _, _ = t.wait_for(OVERVIEW)
        time.sleep(0.6)
        t.send("Right")
        ok2, dt, _ = t.wait_for(DETAIL, timeout=3)
        check("[tostop] fg 뒤 화면·키 정상", ok and ok2, f"{dt*1000:.0f}ms")
        t.send("q")
        ok, _, _ = t.wait_for(r"bye")
        check("[tostop] q 종료", ok)
    finally:
        t.kill()


def test_orphans_npu():
    """furiosa-smi 가 멈춘 상태에서 끝내도 smi 가 남지 않는다 (status 가 죽은 뒤 info 를 새로 띄우지 않는다)."""
    for how in ("q", "sigterm"):
        t = Term(140, 40)
        try:
            t.run(fake_all(NCTOP, npu="hang"))
            ok, _, _ = t.wait_for(OVERVIEW, timeout=8)
            time.sleep(0.8)
            pid = child_pid(t.pane_pid())
            before = [l for l in subprocess.run(["pgrep", "-af", "fakenpu/furiosa-smi"], capture_output=True, text=True).stdout.splitlines()]
            mine = [int(k.split()[0]) for k in children_of(pid)]
            check(f"[orphans-npu {how}] 멈춘 furiosa-smi 자식이 돌고 있음(전제)", ok and len(mine) >= 1, f"{len(mine)}개")
            if how == "q":
                t.send("q")
            else:
                os.kill(pid, 15)
            check(f"[orphans-npu {how}] 끝남", wait_state(pid, "gone", 4.0), pstate(pid))
            time.sleep(1.0)
            # 끝난 뒤 새로 생긴 고아(부모가 1 이 된 가짜 furiosa-smi)가 없어야 한다
            left = [l for l in subprocess.run(["ps", "-eo", "pid=,ppid=,lstart=,args="], capture_output=True, text=True).stdout.splitlines()
                    if "fakenpu/furiosa-smi" in l and l.split()[1] == "1" and int(l.split()[0]) > pid]
            check(f"[orphans-npu {how}] smi 고아가 남지 않음", left == [], f"{[l.split()[0] for l in left]}")
        finally:
            t.kill()


def test_short_wide():
    """가로는 넓고 세로가 짧은 터미널(160x24)에서도 GPU 줄이 보인다."""
    t = Term(160, 24)
    try:
        t.run(fake_all(NCTOP))
        ok, _, scr = t.wait_for(r"gpu0\s*│RTX PRO 6000")
        check("160x24: GPU 줄이 보임", ok)
        check("160x24: NPU 4줄이 다 보임", all(f"npu{i}" in scr for i in range(4)))
        t.send("Right")
        ok, _, scr = t.wait_for(r"gpu0  ·  NVIDIA")
        check("160x24: 둘째 화면에 GPU 상세", ok and "Util" in scr)
        t.send("q")
        t.wait_for(r"bye")
    finally:
        t.kill()


TESTS = {
    "pages": test_pages,
    "quit": test_quit_restores_tty,
    "esc": test_esc_alone,
    "resize": test_resize,
    "small": test_small,
    "variants": test_variants,
    "notty": test_no_tty_stdin,
    "suspend": test_suspend_resume,
    "storm": test_key_storm,
    "cost": test_cpu_cost,
    "hang": test_smi_hang,
    "down": test_smi_down,
    "old": test_smi_old,
    "multi": test_smi_multi,
    "slowpmon": test_smi_slowpmon,
    "jobs": test_jobs,
    "signals": test_signals,
    "orphans": test_orphans,
    "shortwide": test_short_wide,
    "tostop": test_tostop,
    "orphans_npu": test_orphans_npu,
}

if __name__ == "__main__":
    names = sys.argv[1:] or list(TESTS)
    try:
        for name in names:
            print(f"== {name}", flush=True)
            try:
                TESTS[name]()
            except Exception as e:           # 시험 자체가 터져도 다음 시험은 돈다
                check(f"{name}: 시험 실행", False, f"{type(e).__name__}: {e}")
    finally:
        tmux("kill-server", check=False)
    bad = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(bad)}/{len(RESULTS)} 통과" + ("" if not bad else "  — 실패: " + "; ".join(r[0] for r in bad)))
    sys.exit(1 if bad else 0)
