#!/usr/bin/env python3
"""results/*.json 과 serve 로그를 읽어 prebuilt 대 custom 표를 만든다.

bench.py 의 load_s 는 '모델 전환에 걸린 시간'(내리는 시간 포함)이라 앞서 무엇이 떠 있었는지에
좌우된다. 순수 적재 시간은 serve 로그의 'Loading LLM' → 'Uvicorn running' 간격으로 따로 뽑는다.
"""
import json, glob, os, re, sys, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
LOGDIR = "/home/jun/RNGD-proj/Model_Benchmark/rngd-npu/chat/serve_logs"
TS = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\.(\d+)\+09:00")


def serve_load_seconds(model_id):
    """serve 로그에서 순수 적재 시간(초)과 아티팩트 종류.

    ★ 로그는 서빙할 때마다 이어 붙는다. 파일 전체의 첫 줄과 마지막 줄을 쓰면 예전 서빙까지
    합쳐져 적재 시간이 부풀어 오른다(실측: 전환 시간보다 큰 값이 나와 발각). 마지막
    'Loading LLM:' 이후 구간만 본다."""
    f = os.path.join(LOGDIR, "router-" + model_id.replace("@", "_") + ".log")
    if not os.path.exists(f):
        return None, None
    txt = open(f, encoding="utf-8", errors="replace").read()
    i = txt.rfind("Loading LLM:")
    if i > 0:
        txt = txt[i:]
    # 끝은 '서버 기동 완료' 로 자른다. 안 자르면 뜬 뒤에 쌓인 요청 로그까지 적재 시간에 들어간다
    # (실측: Coder FXB 가 994s 로 나왔는데 실제 전환 시간은 202s 였다).
    for mark in ("Uvicorn running", "Application startup complete"):
        j = txt.find(mark)
        if j > 0:
            txt = txt[:j]
            break
    stamps = [datetime.datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S")
              + datetime.timedelta(seconds=int(m.group(2)[:6]) / 1e6) for m in TS.finditer(txt)]
    if len(stamps) < 2:
        return None, None
    # prebuilt 도 두 종류다: 캐시된 FXB 번들과 HF 허브의 v2 아티팩트.
    kind = ("FXB" if "Using FXB:" in txt else
            ("v2-artifact" if "Loading artifact from path" in txt else "?"))
    return round((stamps[-1] - stamps[0]).total_seconds(), 1), kind


def looks_broken(text, thinking=""):
    """답변 상태 판정. 세 가지를 구분한다.
      깨짐      같은 문자/조각만 반복 — 아티팩트가 고장난 것
      사고만    답변은 비었지만 사고(thinking)는 나옴 — 토큰 예산이 모자란 것이지 고장이 아니다
      빈 출력   둘 다 없음
    """
    t = (text or "").strip()
    th = (thinking or "").strip()
    # ★ 사고(thinking) 안의 쓰레기도 잡아야 한다. 답변이 비었다고 무조건 '예산 부족' 으로 넘기면
    #   사고 칸에 '!' 만 채운 고장 모델이 정상으로 집계된다(실측: A3B-Thinking@tp8).
    g = _garbage(th)
    if g:
        return "깨짐(사고): " + g
    if th and not t:
        return "사고만(예산 부족)"
    if not t:
        return "빈 출력"
    return _garbage(t)


def _garbage(t):
    """같은 문자나 짧은 조각만 반복하면 그 사유를 돌려준다. 아니면 None."""
    t = (t or "").strip()
    if not t:
        return None
    uniq = set(t.replace(" ", "").replace("\n", ""))
    if len(uniq) <= 2 and len(t) > 40:
        return f"같은 문자 반복({''.join(sorted(uniq))[:4]})"
    for n in (1, 2, 3):
        if len(t) > 60 and t[:n] * (len(t) // n) == t[:len(t) // n * n]:
            return "같은 조각 반복"
    return None


def load_all():
    out = []
    for f in sorted(glob.glob(os.path.join(RES, "*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        mid = d["model"]
        d["is_custom"] = "@tp8" in mid or mid in ("Llama-3.1-8B-Instruct", "Qwen3-Coder-30B-A3B-Instruct")
        d["base"] = mid.split("@")[0]
        d["serve_load_s"], d["build_kind"] = serve_load_seconds(mid)
        if "runs" in d:
            for r in d["runs"]:
                r["broken"] = looks_broken(r.get("text"), r.get("thinking"))
            # '사고만' 은 고장이 아니므로 정상 쪽으로 센다(별도로 표시).
            ok = [r for r in d["runs"] if not r["broken"] or r["broken"].startswith("사고만")]
            # '깨짐(사고)' 는 위에서 이미 broken 이라 ok 에서 빠진다.
            d["thinking_only"] = sum(1 for r in d["runs"] if (r["broken"] or "").startswith("사고만"))
            d["garbage"] = sum(1 for r in d["runs"] if r["broken"] and not r["broken"].startswith("사고만"))
            d["ok_runs"] = len(ok)
            d["n_runs"] = len(d["runs"])
            vals = [r["decode_tps"] for r in d["runs"] if r.get("decode_tps")]
            d["decode_tps_med"] = round(sorted(vals)[len(vals) // 2], 1) if vals else None
            tt = [r["ttft"] for r in d["runs"] if r.get("ttft")]
            d["ttft_med"] = round(sorted(tt)[len(tt) // 2], 3) if tt else None
        out.append(d)
    return out


def main():
    rows = load_all()
    print(f"{'모델':46s} {'갈래':12s} {'전환s':>7s} {'적재s':>7s} {'TTFT':>6s} {'tok/s':>6s} {'동시tok/s':>9s} {'정상':>6s}")
    print("-" * 112)
    for d in rows:
        if "error" in d and "runs" not in d:
            print(f"{d['model']:46s} {'custom' if d['is_custom'] else 'prebuilt':12s} {'실패':>7s}  {d['error'][:40]}")
            continue
        c = d.get("concurrent") or {}
        print(f"{d['model']:46s} {(d['build_kind'] or '?'):12s} {d.get('load_s',0):7.0f} "
              f"{(d['serve_load_s'] or 0):7.0f} {(d.get('ttft_med') or 0):6.2f} "
              f"{(d.get('decode_tps_med') or 0):6.1f} {(c.get('agg_tps') or 0):9.1f} "
              f"{d.get('ok_runs',0)}/{d.get('n_runs',0):>4}")
    json.dump(rows, open(os.path.join(HERE, "summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\n→ summary.json ({len(rows)}개)")


if __name__ == "__main__":
    main()
