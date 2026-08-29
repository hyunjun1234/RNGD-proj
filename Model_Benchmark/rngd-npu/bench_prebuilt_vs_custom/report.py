#!/usr/bin/env python3
"""쓸 수 있는 채팅 모델 전체의 처리량·지연·답변을 표로 정리한다.

summary.json(= analyze.py 결과)에서 라우터의 기본 구성 모델만 골라 낸다.
@tp8 같은 변형과 embedding/reranker 는 제외한다.
"""
import json, os, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROUTER = "http://localhost:8400"


def chat_models():
    """라우터가 말하는 기본 구성 채팅 모델 → [(id, 카드수)]. 표시 순서 그대로.

    응답이 리스트일 수도 {"data": [...]} 일 수도 있어 둘 다 받는다(실측에서 한 번 물렸다)."""
    with urllib.request.urlopen(ROUTER + "/router/models", timeout=30) as r:
        d = json.loads(r.read())
    rows = d if isinstance(d, list) else (d.get("data") or d.get("models") or [])
    out = []
    for m in rows:
        if not isinstance(m, dict):
            continue
        if m.get("id") != m.get("base") or m.get("kind", "chat") != "chat":
            continue
        out.append((m["id"], m.get("cards")))
    return out


def load():
    return {d["model"]: d for d in json.load(open(os.path.join(HERE, "summary.json"), encoding="utf-8"))}


def fmt(v, digits=0, dash="-"):
    return dash if v is None else (f"{v:.{digits}f}" if isinstance(v, (int, float)) else str(v))


def main():
    S = load()
    order = chat_models()
    rows = [(mid, cards, S.get(mid) if (S.get(mid) or {}).get("runs") else None)
            for mid, cards in order]

    print(f"{'모델':34s} {'카드':>3s} {'적재s':>6s} {'TTFT':>6s} {'디코드':>7s} {'동시4':>7s} {'첫응답':>7s} {'답변'}")
    print("-" * 104)
    for mid, cards, d in rows:
        if d is None:
            print(f"{mid:34s} {(cards or 0):>3d} {'측정 중':>6s}"); continue
        c = d.get("concurrent") or {}
        first = min((r["total"] for r in d["runs"] if r.get("total")), default=None)
        state = "정상" if d.get("ok_runs") == d.get("n_runs") else f"{d.get('garbage',0)}개 깨짐"
        print(f"{mid:34s} {(cards or 0):>3d} {fmt(d.get('serve_load_s')):>6s} {fmt(d.get('ttft_med'),2):>6s} "
              f"{fmt(d.get('decode_tps_med'),1):>7s} {fmt(c.get('agg_tps'),1):>7s} {fmt(first,1):>7s} {state}")
    done = sum(1 for _, _, d in rows if d)
    print(f"\n{done}/{len(rows)} 측정 완료")


if __name__ == "__main__":
    main()
