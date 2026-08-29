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
    (실측: 'furiosa-ai/<모델>' 이 mismatched tag 를 냈다). 모델 출력처럼 내용을
    내가 정하지 못하는 글을 넣을 때 특히 위험하다."""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


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


# 라우터 카탈로그 순서와 표시 이름. 카드 수는 라우터 값.
MODELS = [
    ("gpt-oss-120b", "gpt-oss 120B", 4),
    ("Solar-Open-100B-NVFP4A16", "Solar-Open 100B", 4),
    ("K-EXAONE-236B-A23B-NVFP4A16", "K-EXAONE 236B", 4),
    ("Llama-3.3-70B-Instruct", "Llama 3.3 70B", 4),
    ("Qwen3-32B-FP8", "Qwen3 32B", 4),
    ("EXAONE-4.0-32B-FP8", "EXAONE 4.0 32B", 4),
    ("Qwen3-VL-32B-Instruct", "Qwen3-VL 32B", 4),
    ("Qwen3-Coder-30B-A3B-Instruct-FP8", "Qwen3-Coder 30B", 4),
    ("Qwen3-30B-A3B-Instruct-2507-FP8", "A3B Instruct 2507", 4),
    ("Qwen3-30B-A3B-Thinking-2507-FP8", "A3B Thinking 2507", 4),
    ("Qwen3-30B-A3B-FP8", "A3B 30B", 4),
    ("Llama-3.1-8B-Instruct", "Llama 3.1 8B", 1),
    ("Qwen3-8B-FP8", "Qwen3 8B", 1),
    ("Qwen3-4B-FP8", "Qwen3 4B", 1),
    ("Qwen2.5-0.5B-Instruct", "Qwen2.5 0.5B", 1),
]
THINK = {"Qwen3-32B-FP8", "Qwen3-30B-A3B-Thinking-2507-FP8", "Qwen3-30B-A3B-FP8",
         "EXAONE-4.0-32B-FP8", "K-EXAONE-236B-A23B-NVFP4A16", "Solar-Open-100B-NVFP4A16"}


def G(mid, *path, default=None):
    d = BY.get(mid)
    for p in path:
        if not isinstance(d, dict):
            return default
        d = d.get(p)
    return default if d is None else d


def first_total(mid):
    """가장 짧은 프롬프트의 총 소요 = 사용자가 체감하는 '한 번 물어보고 답 받기'."""
    rs = G(mid, "runs", default=None) or []
    v = [r["total"] for r in rs if r.get("total")]
    return min(v) if v else None


def hbars(b, rows, x, y, w, h, mx, gap=3, unit="", lw=118, vw=40, digits=0):
    """이름 + 막대 + 값. rows = [(라벨, 값, 채움색)]. lw 는 이름 칸, vw 는 값 칸 폭."""
    for lab, v, fill in rows:
        b.append(txt(x, y + h - 3, lab, 10.5, INK))
        b.append(rect(x + lw, y, w, h, GRAY_L, GRAY, 0.7))
        if v:
            b.append(rect(x + lw, y, max(2, w * v / mx), h, fill, "none"))
        b.append(txt(x + lw + w + 5, y + h - 3, ("-" if not v else f"{v:.{digits}f}{unit}"), 10.5, INK))
        y += h + gap
    return y


def two_col(b, rows, y0, w=228, h=13, mx=None, unit=""):
    """15줄을 두 단으로. 반환값은 아래쪽 y."""
    mx = mx or max([v for _, v, _ in rows if v] + [1])
    half = (len(rows) + 1) // 2
    y1 = hbars(b, rows[:half], W0, y0, w, h, mx, unit=unit)
    y2 = hbars(b, rows[half:], 452, y0, w, h, mx, unit=unit)
    return max(y1, y2)


def three_col(b, rows, y0, w=118, h=13, mx=None, unit="", digits=0):
    """15줄을 세 단으로. 두 단으로는 세로가 길어 슬라이드에서 글자가 작아진다."""
    mx = mx or max([v for _, v, _ in rows if v] + [1])
    n = (len(rows) + 2) // 3
    ys = []
    for k, x in enumerate((W0, 296, 576)):
        chunk = rows[k * n:(k + 1) * n]
        if chunk:
            ys.append(hbars(b, chunk, x, y0, w, h, mx, unit=unit, lw=112, vw=34, digits=digits))
    return max(ys)


# ── 1) 어떤 모델이 있나 ────────────────────────────────────────────
def cards_icon(x, y, used, size=9, gap=2):
    """카드 4장을 네모 4개로. used 개만 채운다 — 점유가 모양으로 보이게(L-24)."""
    return [rect(x + i * (size + gap), y, size, size,
                 (YEL if used == 1 else BLUE_M) if i < used else "#ffffff", BLUE, 0.9)
            for i in range(4)]


def lineup_svg():
    b = []
    b.append(panel(W0, 32, "(a) 카드 4장을 다 쓰는 모델, 한 번에 하나만 뜬다"))
    big = [m for m in MODELS if m[2] == 4]
    x, y = W0, 44
    for mid, lab, _ in big:
        w = tw(lab, 11, True) + 34 + 46
        if x + w > W1:
            x, y = W0, y + 31
        done = mid in BY and "runs" in BY[mid]
        b.append(rect(x, y, w, 25, BLUE_L if done else "#ffffff", BLUE, 1.2, rx=4))
        b += cards_icon(x + 8, y + 8, 4)
        b.append(txt(x + 54, y + 17, lab, 11, INK, w=1))
        x += w + 8
    y += 31
    b.append(txt(W0, y + 11, "네모 넷이 카드 넉 장이다, 다 칠해져 있으면 그 모델 하나가 서버를 독차지한다", 10.5, GRAY))
    y += 26
    b.append(panel(W0, y + 11, "(b) 카드 한 장이면 되는 모델, 넷까지 같이 뜬다"))
    y += 20
    x = W0
    for mid, lab, _ in [m for m in MODELS if m[2] == 1]:
        w = tw(lab, 11, True) + 34 + 46
        done = mid in BY and "runs" in BY[mid]
        b.append(rect(x, y, w, 25, YEL if done else "#ffffff", BLUE, 1.2, rx=4))
        b += cards_icon(x + 8, y + 8, 1)
        b.append(txt(x + 54, y + 17, lab, 11, INK, w=1))
        x += w + 8
    y += 31
    b.append(txt(W0, y + 11, "한 칸만 칠해져 있으니 넷을 나란히 올릴 수 있다, 여럿이 각자 다른 모델을 쓸 때 유리하다", 10.5, GRAY))
    y += 24
    b.append(txt(W0, y + 11, "채팅 모델 15종이다, 이 밖에 임베딩과 리랭커가 하나씩 더 있다", 11, INK))
    b.append(txt(W1, y + 11, "라우터 :8400 의 /router/models", 10.5, GRAY, anchor="end"))
    return svg(950, y + 20, "\n".join(b))


# ── 2) 지연 ────────────────────────────────────────────────────────
def latency_svg():
    b = []
    b.append(panel(W0, 32, "(a) 첫 토큰까지 걸린 시간(TTFT), 초"))
    rows = [(lab, G(mid, "ttft_med"), YEL if cards == 1 else BLUE_M) for mid, lab, cards in MODELS]
    y = three_col(b, rows, 42, h=11, digits=2)
    b.append(txt(W0, y + 10, "전부 0.5초 안쪽이라 사람이 느끼는 첫 반응은 모델을 안 가린다", 10.5, GRAY))
    b.append(panel(W0, y + 32, "(b) 짧은 질문 하나에 답이 다 나올 때까지, 초. 별표는 사고하는 모델"))
    rows2 = [(lab + (" *" if mid in THINK else ""), first_total(mid),
              YEL if cards == 1 else BLUE_M) for mid, lab, cards in MODELS]
    y2 = three_col(b, rows2, y + 42, h=11, unit="s", digits=1)
    b.append(txt(W0, y2 + 14, "사고하는 모델은 첫 토큰은 빨라도 답이 끝나기까지 열 배 넘게 걸린다", 11, INK))
    b.append(txt(W1, y2 + 14, "프롬프트 4종 중 가장 짧은 것 기준", 10.5, GRAY, anchor="end"))
    return svg(950, y2 + 22, "\n".join(b))


# ── 3) 처리량 ──────────────────────────────────────────────────────
def tput_svg():
    b = []
    b.append(panel(W0, 32, "(a) 요청 하나를 처리하는 속도, tok/s"))
    rows = [(lab, G(mid, "decode_tps_med"), YEL if c == 1 else BLUE_M) for mid, lab, c in MODELS]
    y = three_col(b, rows, 44, h=12)
    b.append(panel(W0, y + 24, "(b) 같은 질문 4개를 동시에 던졌을 때 전체 속도, tok/s"))
    rows2 = [(lab, G(mid, "concurrent", "agg_tps"), YEL if c == 1 else BLUE_M) for mid, lab, c in MODELS]
    y2 = three_col(b, rows2, y + 36, h=12)
    b.append(txt(W0, y2 + 16, "노란 막대는 카드 한 장짜리다, 작은 모델이 동시 처리에서 오히려 앞선다", 11, INK))
    b.append(txt(W1, y2 + 16, "동시 4요청 합계 토큰 ÷ 전부 끝난 시간", 10.5, GRAY, anchor="end"))
    return svg(950, y2 + 26, "\n".join(b))


# ── 4) 적재 ────────────────────────────────────────────────────────
def loading_svg():
    b = []
    b.append(panel(W0, 32, "모델을 올리는 데 걸린 시간, 초"))
    rows = [(lab, G(mid, "serve_load_s"), YEL if c == 1 else BLUE_M) for mid, lab, c in MODELS]
    y = three_col(b, rows, 46, h=14, unit="s")
    b.append(txt(W0, y + 18, "라우터는 안 쓰는 모델을 내리고 새로 올린다, 그래서 모델을 바꾸면 이만큼 기다린다", 11, INK))
    b.append(txt(W0, y + 38, "카드 한 장짜리는 십 초 안팎이라 갈아 끼우는 부담이 거의 없다", 10.5, GRAY))
    b.append(txt(W1, y + 38, "serve 로그의 Loading LLM 부터 기동 완료까지", 10.5, GRAY, anchor="end"))
    return svg(950, y + 48, "\n".join(b))


# ── 5) 같은 질문에 대한 답변 ───────────────────────────────────────
def answers_svg():
    b = []
    b.append(panel(W0, 32, "질문: 대한민국의 수도는 어디이고, 그 도시가 수도가 된 역사적 배경을 세 문장으로"))
    y = 48
    for mid, lab, cards in MODELS:
        rs = G(mid, "runs", default=None)
        if not rs:
            continue
        r = rs[0]
        t = (r.get("text") or "").strip().replace("\n", " ")
        # 모델 출력에 가운뎃점이 섞여 들어온다. PPT 에는 쓰지 않는다(L-37).
        for ch in ("·", "ㆍ", "‧"):
            t = t.replace(ch, ", ")
        bad = r.get("broken")
        if bad:
            t = "같은 문자만 반복" if "반복" in str(bad) else str(bad)
        elif not t:
            t = "사고만 하고 답까지 못 감"
        b.append(txt(W0, y + 10, lab, 10.5, GRAY))
        if mid in THINK:
            b.append(txt(W0 + 112, y + 10, "*", 10.5, GRAY))
        # 긴 한국어 문장은 pptx 대체 글꼴과 폭이 어긋나 되돌려 비교가 실패한다(L-17).
        # 발췌를 짧게 유지하고, 원문은 results 폴더로 안내한다.
        b.append(txt(W0 + 132, y + 10, t[:30], 10.5, INK))
        n = r.get("out_tokens")
        b.append(txt(W1, y + 10, f"{n}tok" if n else "-", 10.5, GRAY, anchor="end"))
        y += 16
    b.append(txt(W0, y + 16, "모두 같은 문장을 같은 설정으로 물었다, 별표는 사고하는 모델이다", 11, INK))
    b.append(txt(W1, y + 16, "답변 원문 전체는 results 폴더에", 10.5, GRAY, anchor="end"))
    return svg(950, y + 26, "\n".join(b))
