#!/usr/bin/env python3
"""prebuilt(furiosa-ai FXB) 대 직접 빌드(v2 tp8 아티팩트) 모델을 같은 입력으로 재는 하네스.

라우터(:8400)의 모델 ID 규약을 그대로 쓴다.
  <이름>        = prebuilt FXB, tp32, 4장
  <이름>@tp8    = /mnt/nvme2n1p1/models/artifacts 의 직접 빌드 아티팩트, tp8, 1~2장

재는 것: 적재 시간, TTFT, 총 지연, 출력 토큰, 디코드 속도, 동시 4요청 총처리량, 답변 원문.
모델 하나가 끝날 때마다 results/<id>.json 을 쓰므로 중간에 끊겨도 이어서 돌릴 수 있다.
"""
import argparse, json, os, sys, time, threading
import urllib.request, urllib.error

ROUTER = os.environ.get("BENCH_ROUTER", "http://localhost:8400")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")

# 같은 조건: 같은 프롬프트, greedy(temperature 0), 같은 max_tokens.
PROMPTS = [
    ("fact",  "대한민국의 수도는 어디이고, 그 도시가 수도가 된 역사적 배경을 세 문장으로 설명해줘."),
    ("code",  "파이썬으로 피보나치 수열의 n번째 항을 반복문으로 구하는 함수를 쓰고, 시간복잡도를 한 줄로 덧붙여줘."),
    ("reason","한 상자에 사과가 12개 들어간다. 사과 100개를 담으려면 상자가 몇 개 필요하고 마지막 상자에는 몇 개가 남는지 계산 과정을 보여줘."),
    ("long",  "트랜스포머의 어텐션이 무엇인지 처음 배우는 사람에게 설명해줘. 비유를 하나 들고, 왜 순환신경망보다 병렬화에 유리한지도 말해줘."),
]
# thinking 모델은 256 으로는 사고만 하다 끝난다(Qwen3-32B 실측: 4프롬프트 전부 thinking 만).
# 최종 답변까지 보려면 예산을 키운다. 디코드 속도는 예산과 무관하므로 속도 비교는 그대로 유효하다.
MAX_TOKENS = 1024
CONC = 4          # 동시 요청 수 (총처리량 측정)


def post(path, payload, timeout=None):
    req = urllib.request.Request(ROUTER + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def get(path, timeout=30):
    with urllib.request.urlopen(ROUTER + path, timeout=timeout) as r:
        return json.loads(r.read())


def stream_once(model, prompt, max_tokens=MAX_TOKENS, timeout=1800):
    """스트리밍 1회. (ttft, total, 출력토큰, 프롬프트토큰, 본문) 반환."""
    body = {"model": model, "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens, "temperature": 0, "stream": True,
            "stream_options": {"include_usage": True}}
    req = urllib.request.Request(ROUTER + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter(); ttft = None; text = []; think = []; usage = None; chunks = 0
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                ev = json.loads(data)
            except Exception:
                continue
            if ev.get("usage"):
                usage = ev["usage"]
            for ch in ev.get("choices", []):
                d = ch.get("delta") or {}
                # 답변 본문과 사고 과정(thinking)은 따로 모은다. 어느 쪽이든 첫 조각이 TTFT 다.
                # 필드 이름이 모델·파서마다 reasoning / reasoning_content 로 갈린다.
                body = d.get("content") or ""
                rz = d.get("reasoning_content") or d.get("reasoning") or ""
                if body or rz:
                    if ttft is None:
                        ttft = time.perf_counter() - t0
                    chunks += 1
                if body:
                    text.append(body)
                if rz:
                    think.append(rz)
    total = time.perf_counter() - t0
    out_tok = (usage or {}).get("completion_tokens") or chunks
    in_tok = (usage or {}).get("prompt_tokens")
    return dict(ttft=ttft, total=total, out_tokens=out_tok, in_tokens=in_tok,
                decode_tps=(out_tok - 1) / (total - ttft) if (ttft and total > ttft and out_tok > 1) else None,
                text="".join(text), thinking="".join(think), chunks=chunks)


# 아주 큰 모델은 1시간으로 모자란다(K-EXAONE 236B 는 262144 컨텍스트, 가중치 142G).
BIG_BUDGET = {"K-EXAONE-236B-A23B-NVFP4A16": 9000}


def wait_ready(model, budget=None):
    budget = budget or BIG_BUDGET.get(model, 3600)
    """preload 를 걸고 준비될 때까지 기다린다. 걸린 시간을 반환."""
    t0 = time.perf_counter()
    post("/router/preload", {"model": model}, timeout=60)
    last = ""
    st_now = None
    while time.perf_counter() - t0 < budget:
        try:
            st = get("/router/status")
            run = st.get("running") or {}
            s = json.dumps(run, ensure_ascii=False)
            if s != last:
                print(f"    [{time.perf_counter()-t0:6.0f}s] {s[:150]}", flush=True); last = s
            # 상태 사전의 키가 곧 모델 ID 다. state 가 'up' 이 되기 전에는 아직 적재 중이므로
            # 워밍업을 걸면 안 된다 — 걸면 타임아웃까지 통째로 버린다(실측 600s 낭비).
            st_now = (run.get(model) or {}).get("state") if isinstance(run, dict) else None
            ready = st_now == "up"
            if ready:
                # 상태가 '떴다'고 해도 실제 생성이 되는지 짧게 확인
                try:
                    r = stream_once(model, "안녕", max_tokens=8, timeout=180)
                    if r["out_tokens"]:
                        return time.perf_counter() - t0
                    print("    떴지만 워밍업이 0토큰 — 그대로 측정한다", flush=True)
                    return time.perf_counter() - t0
                except Exception as e:
                    print(f"    warmup 실패, 재시도: {e}", flush=True)
        except Exception as e:
            print(f"    status 오류: {e}", flush=True)
            st_now = None
        # ★ 이 판정은 try 밖에 둔다. 안에 두면 바로 아래 except 가 삼켜서 빠져나오지 못하고
        #   같은 메시지를 타임아웃까지 반복한다(실측: Solar 가 3600s 헛돌았다).
        if st_now == "error":
            raise RuntimeError(f"{model}: 라우터가 error 로 표시 — serve 가 뜨지 못했다")
        time.sleep(10)
    raise TimeoutError(f"{model} 준비 실패 ({budget}s)")


def bench_model(model):
    print(f"\n=== {model}", flush=True)
    rec = {"model": model, "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    t0 = time.perf_counter()
    rec["load_s"] = round(wait_ready(model), 1)
    print(f"    적재 {rec['load_s']}s", flush=True)

    # 단일 요청 지연·답변
    runs = []
    for name, p in PROMPTS:
        r = stream_once(model, p)
        r["prompt"] = name
        runs.append(r)
        print(f"    {name:7s} ttft {('%.2f' % r['ttft']) if r['ttft'] else '  --'}s  총 {r['total']:.2f}s  "
              f"{r['out_tokens']}tok  {(r['decode_tps'] or 0):.1f} tok/s"
              f"{'  [출력 없음]' if not r['out_tokens'] else ''}"
              f"{'  [thinking만]' if (r['thinking'] and not r['text']) else ''}", flush=True)
    rec["runs"] = runs

    # 동시 요청 총처리량 (같은 long 프롬프트 4개)
    res = [None] * CONC
    def work(i):
        try:
            res[i] = stream_once(model, PROMPTS[3][1])
        except Exception as e:
            res[i] = {"error": str(e)}
    ts = [threading.Thread(target=work, args=(i,)) for i in range(CONC)]
    tc0 = time.perf_counter()
    [t.start() for t in ts]; [t.join() for t in ts]
    wall = time.perf_counter() - tc0
    ok = [r for r in res if r and not r.get("error")]
    tot_out = sum(r["out_tokens"] or 0 for r in ok)
    rec["concurrent"] = {"n": CONC, "wall_s": round(wall, 2), "out_tokens": tot_out,
                         "agg_tps": round(tot_out / wall, 1) if wall else None,
                         "per_req_total_s": [round(r["total"], 2) for r in ok],
                         "errors": [r.get("error") for r in res if r and r.get("error")]}
    print(f"    동시 {CONC}개: {wall:.1f}s, 합계 {tot_out}tok, {rec['concurrent']['agg_tps']} tok/s", flush=True)
    rec["elapsed_s"] = round(time.perf_counter() - t0, 1)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="+")
    ap.add_argument("--force", action="store_true", help="이미 있는 결과도 다시 잰다")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    for m in a.models:
        f = os.path.join(OUT, m.replace("/", "_") + ".json")
        if os.path.exists(f) and not a.force:
            print(f"건너뜀(결과 있음): {m}", flush=True); continue
        try:
            rec = bench_model(m)
        except Exception as e:
            rec = {"model": m, "error": f"{type(e).__name__}: {e}", "started": time.strftime("%Y-%m-%d %H:%M:%S")}
            print(f"    실패: {rec['error']}", flush=True)
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(rec, fh, ensure_ascii=False, indent=2)
        print(f"    → {f}", flush=True)


if __name__ == "__main__":
    main()
