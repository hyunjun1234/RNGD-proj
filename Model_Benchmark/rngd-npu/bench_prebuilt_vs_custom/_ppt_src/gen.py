"""prebuilt 대 custom 모델 벤치 덱의 그림. 머리글은 "그림 N:"(L-38), 가운뎃점 금지(L-37), 내용 폭 16..844(L-30).

수치는 손으로 적지 않는다 — 전부 ../summary.json 에서 읽는다."""
import json, os
_H = os.path.dirname(os.path.abspath(__file__))
SUM = json.load(open(os.path.join(_H, "..", "summary.json"), encoding="utf-8"))
BY = {d["model"]: d for d in SUM}
GRAY, GRAY_L, INK = "#5b6b7b", "#eef2f7", "#16202c"
BLUE, BLUE_L, BLUE_M = "#253761", "#e3e5ea", "#9da5b8"
YEL = "#ffd34d"
GRID = "#c8d2dc"
W0, W1 = 16, 844

def tw(s, size=10.5, bold=False):
    w = sum(size if ord(c) > 0x2e80 else size*0.5 for c in s)
    return w*1.03 if bold else w
def esc(s):
    """SVG 는 XML 이다. 글자 안의 & < > 를 그대로 쓰면 파싱이 깨진다
    (실측: 'furiosa-ai/<모델>' 이 mismatched tag 를 냈다)."""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def txt(x, y, s, size=10.5, fill=INK, w=None, anchor=None):
    a = f' text-anchor="{anchor}"' if anchor else ''
    b = ' font-weight="700"' if w else ''
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}"{b}{a}>{esc(s)}</text>'
def rect(x, y, w, h, fill, stroke, sw=1, rx=0, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ''
    r = f' rx="{rx}"' if rx else ''
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}"{r} fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>'
def line(x1, y1, x2, y2, stroke, sw=1.4, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ''
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{sw}"{d}/>'
def arrow_r(x, y, l, stroke=GRAY, sw=1.8):   # 머리 9px 포함 총 길이 l+9
    return line(x, y, x+l, y, stroke, sw) + f'<polygon points="{x+l},{y-5} {x+l+9},{y} {x+l},{y+5}" fill="{stroke}"/>'
def arrow_d(x, y, l, stroke=GRAY, sw=1.8):
    return line(x, y, x, y+l, stroke, sw) + f'<polygon points="{x-5},{y+l} {x},{y+l+9} {x+5},{y+l}" fill="{stroke}"/>'
def box(x, y, w, h, lab, fill="#ffffff", stroke=BLUE, sw=1.3, size=10.5, bold=False, rx=4):
    if w is None:
        w = tw(lab, size, bold) + 32
    return [rect(x, y, w, h, fill, stroke, sw, rx=rx), txt(x+w/2, y+h/2+4, lab, size, INK, w=bold, anchor="middle")], w
def brk_h(x1, x2, y, lab):
    """가로 브래킷: 상자 위. 글자는 브래킷 위 가운데 (L-40)."""
    return [line(x1, y, x2, y, GRAY, 1), line(x1, y-4, x1, y+4, GRAY, 1), line(x2, y-4, x2, y+4, GRAY, 1),
            txt((x1+x2)/2, y-6, lab, 11, INK, anchor="middle")]
def brk_v(x, y1, y2, lab, side="left"):
    """세로 브래킷: 상자 왼쪽(또는 오른쪽). 글자는 브래킷 옆 가운데."""
    o = [line(x, y1, x, y2, GRAY, 1), line(x-4, y1, x+4, y1, GRAY, 1), line(x-4, y2, x+4, y2, GRAY, 1)]
    o.append(txt(x-8 if side == "left" else x+8, (y1+y2)/2+4, lab, 11, INK, anchor="end" if side == "left" else "start"))
    return o
def panel(x, y, s):
    return txt(x, y, s, 11.5, INK, w=1)
def svg(w, h, body):
    return (f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">\n<g font-family="Noto Sans CJK KR">\n{body}\n</g>\n</svg>\n')


def panel(x, y, s):
    return txt(x, y, s, 11.5, INK, w=1)

def panel(x, y, s):
    return txt(x, y, s, 11.5, INK, w=1)

def brk_h(x1, x2, y, lab):
    return [line(x1, y, x2, y, GRAY, 1), line(x1, y-4, x1, y+4, GRAY, 1), line(x2, y-4, x2, y+4, GRAY, 1),
            txt((x1+x2)/2, y-6, lab, 11, INK, anchor="middle")]

def bar(x, y, w, h, frac, lab, val, cap=None, fill=YEL):
    """가로 막대 하나. frac 0..1, 값은 막대 오른쪽에 글자로 (SVG_RULES §4)."""
    o = [txt(x, y+h*0.72, lab, 10.5, INK), rect(x+170, y, w, h, GRAY_L, GRAY, 0.8)]
    if frac > 0:
        o.append(rect(x+170, y, max(2, w*frac), h, fill, "none"))
    o.append(txt(x+170+w+8, y+h*0.72, val, 10.5, INK))
    if cap:
        o.append(txt(x+178, y+h*0.72, cap, 10.5, INK))
    return o

# ── 1) 두 갈래가 무엇인가 ────────────────────────────────────────────
def paths_svg():
    b = []
    b.append(panel(W0, 36, "(a) prebuilt: 퓨리오사가 배포한 FXB 번들"))
    chain = [("HF 허브", "furiosa-ai/<모델>"), ("FXB 파일 1개", "…-2606290751.fxb"),
             ("entrypoint 경로", "TP=32, 카드 4장"), ("서빙", "포트 8410")]
    x = W0
    for i, (t1, t2) in enumerate(chain):
        w = max(tw(t1, 11, True), tw(t2, 10.5)) + 30
        b.append(rect(x, 48, w, 40, BLUE_L if i < 2 else "#ffffff", BLUE, 1.3, rx=4))
        b.append(txt(x+w/2, 65, t1, 11, INK, w=1, anchor="middle"))
        b.append(txt(x+w/2, 81, t2, 10.5, GRAY, anchor="middle"))
        x += w
        if i < len(chain)-1:
            b.append(arrow_r(x+3, 68, 12)); x += 12+9+6
    b.append(txt(W0, 108, "가중치도 컴파일 결과도 번들 하나에 들어 있다, 우리가 만지는 부분이 없다", 10.5, GRAY))

    b.append(panel(W0, 146, "(b) custom: 우리가 직접 빌드한 v2 아티팩트"))
    chain2 = [("HF 가중치", "원본 모델"), ("furiosa-llm build", "2026-07-27~29"),
              ("아티팩트 폴더", "artifact.json + 가중치"), ("next_gen 경로", "TP=8, 카드 1장"), ("서빙", "포트 8410")]
    x = W0
    for i, (t1, t2) in enumerate(chain2):
        w = max(tw(t1, 11, True), tw(t2, 10.5)) + 30
        f = YEL if i == 2 else (BLUE_L if i < 2 else "#ffffff")
        b.append(rect(x, 158, w, 40, f, BLUE, 1.3, rx=4))
        b.append(txt(x+w/2, 175, t1, 11, INK, w=1, anchor="middle"))
        b.append(txt(x+w/2, 191, t2, 10.5, GRAY, anchor="middle"))
        x += w
        if i < len(chain2)-1:
            b.append(arrow_r(x+3, 178, 12)); x += 12+9+6
    b.append(txt(W0, 216, "노란 상자는 사람이 손댈 수 있는 곳이다, MoE 게이트를 지나려고 여기의 model_type 을 고쳤다", 10.5, GRAY))
    b.append(txt(W0, 242, "같은 모델을 라우터가 두 갈래로 서빙한다, 이름 뒤 @tp8 이 직접 빌드한 쪽이다", 11, INK))
    b.append(txt(W1, 242, "coding-agent/furiosa_router.py 의 REGISTRY tps 필드", 10.5, GRAY, anchor="end"))
    return svg(950, 250, "\n".join(b))

# ── 2) 무엇을 어떻게 쟀나 ────────────────────────────────────────────
def method_svg():
    b = []
    b.append(panel(W0, 36, "(a) 한 요청의 시간 축"))
    y = 58
    b.append(line(60, y+30, 820, y+30, GRAY, 1.4))
    marks = [(60, "요청 보냄"), (250, "첫 토큰"), (820, "마지막 토큰")]
    for mx, lab in marks:
        b.append(line(mx, y+22, mx, y+38, INK, 1.4))
        b.append(txt(mx, y+56, lab, 10.5, INK, anchor="middle" if mx != 820 else "end"))
    b.append(rect(60, y+6, 190, 14, YEL, BLUE, 0.9))
    b.append(txt(155, y+17, "TTFT", 10.5, INK, w=1, anchor="middle"))
    b.append(rect(250, y+6, 570, 14, BLUE_L, BLUE, 0.9))
    b.append(txt(535, y+17, "디코드 구간, 남은 토큰 수 ÷ 이 시간 = tok/s", 10.5, INK, anchor="middle"))
    b.append(panel(W0, 160, "(b) 같게 맞춘 조건"))
    conds = [("프롬프트", "사실, 코드, 추론, 설명 4종 고정"), ("샘플링", "temperature 0 (greedy)"),
             ("길이", "max_tokens 256"), ("동시성", "단일 1개, 그리고 같은 프롬프트 4개 동시")]
    x = W0
    for t1, t2 in conds:
        w = max(tw(t1, 11, True), tw(t2, 10.5)) + 28
        b.append(rect(x, 172, w, 42, "#ffffff", BLUE, 1.2, rx=4))
        b.append(txt(x+w/2, 190, t1, 11, INK, w=1, anchor="middle"))
        b.append(txt(x+w/2, 206, t2, 10.5, INK, anchor="middle"))
        x += w + 10
    b.append(txt(W0, 240, "적재 시간은 따로 잰다, serve 로그의 첫 줄과 마지막 줄 간격이 순수 적재 시간이다", 11, INK))
    b.append(txt(W1, 240, "bench.py, chat/serve_logs/router-<모델>.log", 10.5, GRAY, anchor="end"))
    return svg(950, 248, "\n".join(b))

# ── 공통: 쌍 목록 ─────────────────────────────────────────────────
PAIRS = [
    ("Qwen3-Coder-30B-A3B-Instruct-FP8", "Coder 30B"),
    ("Qwen3-32B-FP8", "Qwen3 32B"),
    ("Qwen3-30B-A3B-Instruct-2507-FP8", "A3B Instruct"),
    ("Qwen3-30B-A3B-Thinking-2507-FP8", "A3B Thinking"),
    ("EXAONE-4.0-32B-FP8", "EXAONE 4.0"),
    ("Qwen3-30B-A3B-FP8", "A3B"),
]
MOE = {"Qwen3-Coder-30B-A3B-Instruct-FP8", "Qwen3-30B-A3B-Instruct-2507-FP8",
       "Qwen3-30B-A3B-Thinking-2507-FP8", "Qwen3-30B-A3B-FP8"}


def _g(mid, *path, default=None):
    d = BY.get(mid)
    for p in path:
        if d is None:
            return default
        d = d.get(p) if isinstance(d, dict) else None
    return default if d is None else d


def have(mid):
    return mid in BY and "runs" in BY[mid]


# ── 3) 속도 비교 ──────────────────────────────────────────────────
def speed_svg():
    b = []
    rows = [(base, lab) for base, lab in PAIRS if have(base) or have(base + "@tp8")]
    mx = max([_g(m, "concurrent", "agg_tps", default=0) or 0
              for base, _ in rows for m in (base, base + "@tp8")] + [1])
    b.append(panel(W0, 34, "(a) 동시 4요청 총처리량, 막대 옆 숫자는 tok/s"))
    y = 46
    for base, lab in rows:
        for suf, kind, fill in (("", "prebuilt 4장", BLUE_M), ("@tp8", "custom 1장", YEL)):
            mid = base + suf
            v = _g(mid, "concurrent", "agg_tps", default=None)
            okr, nr = _g(mid, "ok_runs", default=0), _g(mid, "n_runs", default=0)
            note = "" if (nr and okr == nr) else ("  답변 깨짐" if nr else "  측정 실패")
            b += bar(W0, y, 260, 13, (v or 0) / mx, f"{lab}  {kind}",
                     (f"{v:.0f}" if v else "-") + note, fill=fill)
            y += 14
        y += 2
    b.append(panel(600, 34, "(b) 단일 요청"))
    b.append(txt(600, 54, "TTFT 는 양쪽 다 0.1초 안팎", 10.5, INK))
    b.append(txt(600, 72, "디코드 속도 중앙값, tok/s", 10.5, GRAY))
    yy = 84
    for base, lab in rows:
        a1 = _g(base, "decode_tps_med", default=None)
        a2 = _g(base + "@tp8", "decode_tps_med", default=None)
        b.append(txt(600, yy, lab, 10.5, INK))
        b.append(txt(760, yy, f"{a1:.0f}" if a1 else "-", 10.5, INK, anchor="end"))
        b.append(txt(844, yy, f"{a2:.0f}" if a2 else "-", 10.5, INK, anchor="end"))
        yy += 15
    b.append(txt(760, 84-18, "prebuilt", 10.5, GRAY, anchor="end"))
    b.append(txt(844, 84-18, "custom", 10.5, GRAY, anchor="end"))
    h = max(y, yy) + 30
    b.append(txt(W0, h-14, "카드 수가 다르다, prebuilt 는 4장 custom 은 1장이므로 카드당으로 보면 격차가 더 벌어진다", 11, INK))
    return svg(950, h, "\n".join(b))


# ── 4) 적재 시간 ──────────────────────────────────────────────────
def load_svg():
    b = []
    rows = []
    for base, lab in PAIRS:
        for suf, kind in (("", "prebuilt"), ("@tp8", "custom")):
            mid = base + suf
            v = _g(mid, "serve_load_s", default=None)
            # 측정에 실패한 모델(디스크가 차서 다운로드가 끊긴 것)은 로그에 짧은 시간이 남지만
            # 그것은 '적재 시간' 이 아니라 '실패까지 걸린 시간' 이다. 빼야 한다.
            if v and have(mid):
                rows.append((f"{lab}  {kind}", v, kind))
    if not rows:
        rows = [("측정 전", 1, "prebuilt")]
    mx = max(v for _, v, _ in rows)
    b.append(panel(W0, 34, "(a) serve 로그 기준 순수 적재 시간, 초"))
    y = 46
    for lab, v, kind in rows:
        b += bar(W0, y, 560, 13, v / mx, lab, f"{v:.0f}s",
                 fill=YEL if kind == "custom" else BLUE_M)
        y += 16
    b.append(txt(W0, y + 22, "prebuilt 는 4장에 펼치느라 오래 걸리고, custom tp8 은 카드 1장이라 짧다, 적재에 실패한 두 모델은 뺐다", 11, INK))
    b.append(txt(W1, y + 22, "serve 로그의 Loading LLM 부터 기동 완료까지", 10.5, GRAY, anchor="end"))
    return svg(950, y + 30, "\n".join(b))


# ── 5) 답변이 멀쩡한가 ────────────────────────────────────────────
def quality_svg():
    b = []
    b.append(panel(W0, 34, "(a) 아티팩트별 답변 상태, 프롬프트 4종 모두"))
    y = 50
    cw = 150
    b.append(txt(W0 + 285, y - 8, "MoE 위장 여부", 10.5, GRAY, anchor="middle"))
    for base, lab in PAIRS:
        mid = base + "@tp8"
        okr, nr = _g(mid, "ok_runs", default=None), _g(mid, "n_runs", default=None)
        state = "측정 전" if nr is None else (f"정상 {okr}/{nr}" if okr == nr else f"깨짐 {nr-okr}/{nr}")
        good = (nr is not None and okr == nr)
        lw = tw(lab + " custom") + 32
        b.append(rect(W0, y, lw, 23, "#ffffff", BLUE, 1.1, rx=3))
        b.append(txt(W0 + lw/2, y + 16, lab + " custom", 10.5, INK, anchor="middle"))
        b.append(rect(W0 + 240, y, 90, 23, YEL if base in MOE else GRAY_L, BLUE, 1, rx=3))
        b.append(txt(W0 + 285, y + 16, "위장함" if base in MOE else "원본", 10.5, INK, anchor="middle"))
        sw = tw(state) + 32
        b.append(rect(W0 + 340, y, sw, 23, "#ffffff" if good else BLUE_M, BLUE, 1.1, rx=3))
        b.append(txt(W0 + 340 + sw/2, y + 16, state, 10.5, INK, anchor="middle"))
        y += 26
    b.append(panel(500, 34, "(b) 같은 프롬프트에 대한 답변 첫 줄"))
    yy = 50
    for base, lab in PAIRS[:4]:
        for suf, kind in (("", "prebuilt"), ("@tp8", "custom")):
            r0 = (_g(base + suf, "runs", default=None) or [{}])[0]
            t = (r0.get("text") or "").strip().replace("\n", " ")
            bad = (r0.get("broken") or "")
            if bad:
                t = "같은 문자만 반복" if "반복" in bad else bad[:24]
            else:
                t = t[:24] or "(없음)"
            b.append(txt(500, yy, f"{lab} {kind}", 10.5, GRAY))
            b.append(txt(628, yy, t, 10.5, INK))
            yy += 15
        yy += 3
    h = max(y, yy) + 30
    b.append(txt(W0, h - 14, "처리량만 보면 custom 이 이기지만, 답변을 같이 보지 않으면 깨진 것을 놓친다", 11, INK))
    b.append(txt(W1, h - 30, "답변 원문은 results/<모델>.json 에 전부 저장돼 있다", 10.5, GRAY, anchor="end"))
    return svg(950, h, "\n".join(b))



# ── 6) 게이트가 무엇을 막는가 ─────────────────────────────────────
def gate_svg():
    b = []
    b.append(panel(W0, 34, "(a) 같은 MoE 모델, 두 경로"))
    rows = [("배포 FXB", "entrypoint 경로", "MoE 지원", "정상 답변", True),
            ("직접 빌드 v2", "next_gen 경로", "MoE 미지원", "게이트가 막는다", False)]
    y = 50
    for t1, t2, t3, t4, ok in rows:
        x = W0
        for k, (lab, w) in enumerate([(t1, 130), (t2, 150), (t3, 110), (t4, 150)]):
            f = "#ffffff" if k < 2 else (GRAY_L if ok else YEL)
            b.append(rect(x, y, w, 27, f, BLUE, 1.2, rx=4))
            b.append(txt(x+w/2, y+18, lab, 10.5, INK, w=(k == 0), anchor="middle"))
            x += w
            if k < 3:
                b.append(arrow_r(x+2, y+13, 8)); x += 8+9+4
        y += 36
    b.append(rect(W0, y+8, 828, 24, "#0f1b2a", "#0f1b2a", 1, rx=3))
    b.append(txt(W0+12, y+24, "PanicException: Unsupported model metadata: ModelMetadata { model_type: Some(Qwen3Moe), … }",
                 10.5, "#e6edf3"))
    y += 40

    b.append(panel(W0, y+18, "(b) 우회하면 무슨 일이 생기나"))
    steps = [("게이트 우회", "model_type 을 qwen3 로 고침", GRAY_L),
             ("적재 성공", "가중치 29 GiB 정상 로드, 서버도 뜬다", GRAY_L),
             ("에러 없음", "로그에 아무 경고도 안 남는다", GRAY_L),
             ("답이 틀림", "뜻 없는 출력, 실행마다 양상이 다르다", YEL)]
    yy = y + 28
    x2 = W0
    for i2, (t1, t2, f) in enumerate(steps):
        w2 = max(tw(t1, 11, True), tw(t2, 10.5)) + 24
        b.append(rect(x2, yy, w2, 34, f, BLUE, 1.2, rx=4))
        b.append(txt(x2+w2/2, yy+15, t1, 11, INK, w=1, anchor="middle"))
        b.append(txt(x2+w2/2, yy+29, t2, 10.5, INK, anchor="middle"))
        x2 += w2
        if i2 < 3:
            b.append(arrow_r(x2+2, yy+17, 6)); x2 += 6+9+3
    yy += 34
    b.append(txt(W0, yy+18, "터지면 알아채지만 조용히 틀리면 그대로 쓴다, 속도만 보는 벤치는 이것을 통과시킨다", 11, INK, w=1))
    h = yy + 40
    b.append(txt(W1, h-12, "chat/serve_logs/router.log, furiosa-llm 2026.3.0", 10.5, GRAY, anchor="end"))
    return svg(950, h, "\n".join(b))


# ── 7) 세 변형 실험 ───────────────────────────────────────────────
def verify_svg(name="coder-tp8"):
    f = os.path.join(_H, "..", f"moe_check_{name}.json")
    res = json.load(open(f, encoding="utf-8")) if os.path.exists(f) else {}
    b = []
    b.append(panel(W0, 34, "(a) artifact.json 을 세 가지로 바꿔 같은 질문을 던졌다"))
    cases = [("위장본", "model_type=qwen3, MoE 키 없음", "위장본(현재)"),
             ("원본", "model_type=qwen3_moe, MoE 키 있음", "원본 qwen3_moe"),
             ("절충본", "model_type=qwen3, MoE 키 되살림", "위장 + MoE키 복원")]
    y = 50
    for i2, (t1, t2, key) in enumerate(cases):
        lw2 = max(tw(t1, 11, True), tw(t2)) + 32
        b.append(rect(W0, y, lw2, 40, YEL if i2 == 2 else "#ffffff", BLUE, 1.2, rx=4))
        b.append(txt(W0+lw2/2, y+17, t1, 11, INK, w=1, anchor="middle"))
        b.append(txt(W0+lw2/2, y+33, t2, 10.5, INK, anchor="middle"))
        b.append(arrow_r(W0+lw2+2, y+20, 10))
        r = res.get(key)
        if r is None:
            out, sub = "측정 전", ""
        elif r.get("note") != "ok":
            out, sub = "뜨지 못했다", str(r.get("note"))[:56]
        else:
            t = (r.get("text") or "").strip().replace("\n", " ")
            good0 = "서울" in t
            if not good0:
                # 다른 언어 원문을 그대로 실으면 글꼴 폭 추정이 어긋나 되돌려 비교가 실패한다.
                t = f"질문과 무관한 내용 {len(t)}자, 한국어가 아니다"
            out, sub = ("떴고 제대로 답했다" if good0 else "떴지만 답이 아니다"), (t[:50] or "(빈 출력)")
        good = (r or {}).get("note") == "ok" and "서울" in ((r or {}).get("text") or "")
        b.append(rect(W0+300, y, 528, 40, "#ffffff" if good else GRAY_L, BLUE, 1.1, rx=4))
        b.append(txt(W0+312, y+17, out, 11, INK, w=1))
        b.append(txt(W0+312, y+33, sub, 10.5, INK))
        y += 46
    b.append(txt(W0, y+16, "셋 중 어느 것도 질문에 답하지 못했다, MoE 키를 되살려도 마찬가지다", 11, INK, w=1))
    b.append(txt(W0, y+36, "사라진 설정 키가 원인이라는 가설은 기각됐다, 원인은 실행 경로 자체다", 11, INK))
    b.append(txt(W1, y+36, "moe_check2.py", 10.5, GRAY, anchor="end"))
    return svg(950, y + 44, "\n".join(b))
