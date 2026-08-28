#!/usr/bin/env python3
"""가설 검증: MoE tp8 아티팩트의 쓰레기 출력이 'artifact.json 위장 때 MoE 설정 키가 사라진 탓'인가.

라우터(:8400)를 그대로 쓴다 — 실제 서빙 경로와 같고, 카드 배정도 라우터가 알아서 한다.
한 변형마다 (1) artifact.json 을 바꾸고 (2) 그 모델의 백엔드를 죽여 다시 올라오게 한 뒤
(3) 같은 질문을 던진다. 끝나면 원래 파일로 되돌린다.

  위장본(현재)        model_type=qwen3,      MoE 키 없음   ← 지금 쓰는 것
  원본 qwen3_moe      model_type=qwen3_moe,  MoE 키 있음   ← 게이트가 막을 것으로 예상
  위장 + MoE키 복원   model_type=qwen3,      MoE 키 있음   ← 이게 살아나면 원인 확정
"""
import json, os, shutil, subprocess, sys, time, urllib.request, urllib.error

ART = "/mnt/nvme2n1p1/models/artifacts"
ROUTER = "http://localhost:8400"
HERE = os.path.dirname(os.path.abspath(__file__))
PROMPT = "대한민국의 수도는 어디이고, 그 도시가 수도가 된 역사적 배경을 세 문장으로 설명해줘."
# 아티팩트 폴더 이름 → 라우터 모델 ID
MODEL_OF = {
    "coder-tp8": "Qwen3-Coder-30B-A3B-Instruct-FP8@tp8",
    "a3b-inst-2507-tp8": "Qwen3-30B-A3B-Instruct-2507-FP8@tp8",
    "a3b-think-2507-tp8": "Qwen3-30B-A3B-Thinking-2507-FP8@tp8",
}
MOE_KEYS = ("decoder_sparse_step", "moe_intermediate_size", "num_experts_per_tok",
            "num_local_experts", "norm_topk_prob", "output_router_logits",
            "router_aux_loss_coef", "mlp_only_layers")


def rget(path, timeout=30):
    with urllib.request.urlopen(ROUTER + path, timeout=timeout) as r:
        return json.loads(r.read())


def kill_backend(model):
    """그 모델을 서빙 중인 furiosa-llm 프로세스를 죽인다. 라우터의 _reap_dead 가 카드를 놓는다."""
    st = rget("/router/status").get("running", {})
    if model not in st:
        return "이미 안 떠 있음"
    port = st[model].get("port")
    out = subprocess.run(["ps", "-eo", "pid,args", "--no-headers"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if "furiosa-llm" in line and "serve" in line and (f"--port {port}" in line or f"--port={port}" in line):
            pid = int(line.split()[0])
            subprocess.run(["kill", str(pid)])
            return f"pid {pid} 종료"
    return "프로세스 못 찾음"


def ask(model, budget=1500):
    """라우터에 질문 하나. 준비될 때까지 기다린다."""
    t0 = time.time()
    urllib.request.urlopen(urllib.request.Request(
        ROUTER + "/router/preload", data=json.dumps({"model": model}).encode(),
        headers={"Content-Type": "application/json"}), timeout=60).read()
    err = None
    while time.time() - t0 < budget:
        try:
            st = (rget("/router/status").get("running") or {}).get(model) or {}
            if st.get("state") == "error":
                return None, f"서빙 실패(state=error) — 게이트에 막혔을 수 있다", round(time.time()-t0, 1)
            if st.get("state") == "up":
                body = {"model": model, "messages": [{"role": "user", "content": PROMPT}],
                        "max_tokens": 96, "temperature": 0}
                req = urllib.request.Request(ROUTER + "/v1/chat/completions",
                                             data=json.dumps(body).encode(),
                                             headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=300) as r:
                    d = json.loads(r.read())
                m = d["choices"][0]["message"]
                txt = (m.get("content") or "") + (("  [사고]" + m["reasoning"]) if m.get("reasoning") else "")
                return txt, "ok", round(time.time()-t0, 1)
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
        time.sleep(10)
    return None, f"시간 초과 ({budget}s) {err or ''}", round(time.time()-t0, 1)


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "coder-tp8"
    model = MODEL_OF[name]
    art = os.path.join(ART, name)
    cur, orig = os.path.join(art, "artifact.json"), os.path.join(art, "artifact.json.orig-qwen3_moe")
    backup = os.path.join(HERE, f"{name}.artifact.json.bak")
    shutil.copy2(cur, backup)
    print(f"백업 → {backup}", flush=True)

    # 절충본: 위장(model_type=qwen3)은 유지하고 MoE 키만 원본에서 되살린다
    a = json.load(open(cur)); b = json.load(open(orig))
    ha = a["model"]["model_metadata"]["hf_configs"]; hb = b["model"]["model_metadata"]["hf_configs"]
    restored = [k for k in MOE_KEYS if k in hb]
    for k in restored:
        ha[k] = hb[k]
    mix = os.path.join(HERE, f"{name}.artifact.json.moekeys")
    json.dump(a, open(mix, "w"), ensure_ascii=False)
    print(f"절충본에 되살린 키 {len(restored)}개: {', '.join(restored)}", flush=True)

    res = {}
    try:
        for label, src in [("위장본(현재)", backup), ("원본 qwen3_moe", orig), ("위장 + MoE키 복원", mix)]:
            shutil.copy2(src, cur)
            print(f"\n── {label}  ({os.path.basename(src)})", flush=True)
            print("   " + kill_backend(model), flush=True)
            time.sleep(20)
            txt, note, secs = ask(model)
            res[label] = {"note": note, "seconds": secs, "text": (txt or "")[:800]}
            print(f"   [{secs}s] {note} | {(txt or '')[:110]!r}", flush=True)
    finally:
        shutil.copy2(backup, cur)
        kill_backend(model)   # 원래 파일로 다시 뜨게
        print(f"\n원래 상태로 복구 완료: {cur}", flush=True)
    json.dump(res, open(os.path.join(HERE, f"moe_check_{name}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"→ moe_check_{name}.json")


if __name__ == "__main__":
    main()
