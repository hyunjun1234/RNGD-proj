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

