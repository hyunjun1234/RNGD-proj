"""모델별 종합 비교 리포트 (Markdown) 생성.

results/ 아래 모든 task JSON을 모아 다음을 자동 산출한다:
  1. TL;DR 핵심 지표
  2. 단일 요청 토큰 생성 속도 (tps)
  3. 배치/동시성 스케일링 + 효율/포화/감소 지점 (sweep)
  4. memsweep — serve 옵션(KV cache/batch)별 효과
  5. SWE-bench resolved %
  6. Embedding / Reranker 처리량
  7. NPU 요구량 & 동시 접속자별 권장 서빙 설정
  8. 종합 결론 — 코드 생성에 가장 적합한 모델 (투명한 가중 점수)

부분 실행 상태(일부 task만 완료)에서도 안전하게 동작한다.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
RESULTS_ROOT = REPO_ROOT / "results"
CONFIG_PATH = REPO_ROOT / "configs" / "models.yaml"

# 동시성 스케일링 분석 기준
SLA_TTFT_P95_S = 10.0      # 이 TTFT(p95)를 넘으면 "감소 구간"으로 간주
EFFICIENT_FRAC = 0.90      # peak 처리량의 이 비율에 처음 도달하는 동시성 = 효율 배치
SWEEP_PROMPT_LEN = 1024    # 배치 스케일링 표에 쓰는 기준 prompt 길이


def _read_json(p: Path):
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _load_config() -> dict:
    try:
        import yaml
        return yaml.safe_load(CONFIG_PATH.read_text())
    except Exception:
        return {}


def _load() -> dict:
    by_model: dict = defaultdict(lambda: defaultdict(list))
    if not RESULTS_ROOT.exists():
        return by_model
    for model_dir in RESULTS_ROOT.iterdir():
        if not model_dir.is_dir() or model_dir.name.startswith("_"):
            continue
        model = model_dir.name.replace("__", "/")
        for task_dir in model_dir.iterdir():
            if not task_dir.is_dir():
                continue
            for f in sorted(task_dir.glob("*.json")):
                obj = _read_json(f)
                if obj is not None:
                    by_model[model][task_dir.name].append(obj)
    return by_model


# ---------- task별 추출 ----------

def _tps_summary(tasks: dict) -> dict:
    for o in tasks.get("tps", []):
        s = o.get("summary")
        if s and "error" not in s:
            return s
    return {}


def _sweep_rows(tasks: dict, prompt_len: int | None = None) -> list[dict]:
    rows: list[dict] = []
    for o in tasks.get("sweep", []):
        rows.extend(o.get("sweep", []))
    if prompt_len is not None:
        rows = [r for r in rows if r.get("prompt_tokens_target") == prompt_len]
    # concurrency별 최신 1건만 (중복 실행 대비)
    by_c: dict = {}
    for r in rows:
        by_c[r.get("concurrency")] = r
    return [by_c[c] for c in sorted(by_c, key=lambda x: (x is None, x))]


def _ok(row: dict) -> bool:
    return ("error" not in row and row.get("failures", 1) == 0
            and row.get("aggregate_output_tps") is not None)


def analyze_scaling(rows: list[dict]) -> dict:
    """sweep rows(동일 prompt_len, concurrency 오름차순)에서 스케일링 지표 도출."""
    ok = [r for r in rows if _ok(r)]
    if not ok:
        return {}
    peak = max(ok, key=lambda r: r["aggregate_output_tps"])
    peak_tps = peak["aggregate_output_tps"]
    # 효율 배치: peak의 EFFICIENT_FRAC 이상 처리량에 처음 도달하는 동시성
    efficient = next(
        (r for r in ok if r["aggregate_output_tps"] >= EFFICIENT_FRAC * peak_tps),
        peak,
    )
    # 감소 시작: 실패 발생 / 처리량 하락 / TTFT SLA 초과 중 가장 먼저
    degrade_c = None
    prev = None
    for r in rows:
        bad = ("error" in r or r.get("failures", 0) > 0
               or (r.get("ttft_s_p95") or 0) > SLA_TTFT_P95_S
               or (prev is not None and _ok(r) and _ok(prev)
                   and r["aggregate_output_tps"] < prev["aggregate_output_tps"]))
        if bad:
            degrade_c = r.get("concurrency")
            break
        prev = r
    return {
        "peak_c": peak["concurrency"],
        "peak_tps": peak_tps,
        "efficient_c": efficient["concurrency"],
        "efficient_tps": efficient["aggregate_output_tps"],
        "max_no_degrade_c": ok[-1]["concurrency"],
        "degrade_c": degrade_c,
    }


def _best_memsweep(mem_objs: list) -> dict | None:
    # results/<model>/memsweep/ 에는 개별 memsweep_NNN.json 과 전체를 묶은
    # memsweep_summary.json(리스트)이 함께 있어 같은 combo가 중복 수집된다.
    # combo 기준으로 한 번만 집계한다.
    flat: list = []
    for o in mem_objs:
        if isinstance(o, list):
            flat.extend(o)
        elif isinstance(o, dict):
            flat.append(o)
    scored = []
    seen: set = set()
    for r in flat:
        bench = r.get("bench") or r.get("summary")
        if not bench or bench.get("aggregate_output_tps") is None:
            continue
        combo = r.get("combo")
        key = json.dumps(combo, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        scored.append((bench["aggregate_output_tps"], combo, bench))
    if not scored:
        return None
    scored.sort(reverse=True, key=lambda x: x[0])
    tps, combo, bench = scored[0]
    return {"combo": combo, "summary": bench, "all": scored}


def _swebench(model_dir: Path) -> dict | None:
    f = model_dir / "swebench" / "eval_result.json"
    if not f.exists():
        return None
    obj = _read_json(f) or {}
    return obj.get("report")


def _swebench_pred_summary(tasks: dict) -> dict:
    for o in tasks.get("swebench", []):
        if isinstance(o, dict) and "n_instances" in o:
            return o
    return {}


def _num(x, default=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


# ---------- 렌더링 ----------

def render(by_model: dict) -> str:
    cfg = _load_config()
    devices_default = cfg.get("devices", "npu:0")
    model_meta = {m["id"]: m for m in cfg.get("models", [])}

    L: list[str] = []
    L.append("# Furiosa RNGD — 코드 생성 모델 벤치마크 리포트")
    L.append("")
    L.append(f"- 결과 데이터: `{RESULTS_ROOT}`")
    L.append("- 측정 축: 단일 토큰 속도(tps) / 동시성 스케일링(sweep) / "
             "serve 옵션(memsweep) / SWE-bench / Embedding·Reranker")
    L.append(f"- 스케일링 분석 기준: prompt_len={SWEEP_PROMPT_LEN}, "
             f"효율배치=peak의 {int(EFFICIENT_FRAC*100)}% 도달 동시성, "
             f"감소판정=실패발생·처리량하락·TTFT_p95>{SLA_TTFT_P95_S}s")
    L.append("")

    models = sorted(by_model)

    # --- 1. TL;DR ---
    L.append("## 1. TL;DR — 모델별 핵심 지표")
    L.append("")
    L.append("| 모델 | NPU | TTFT p50(s) | 단일 TPS | peak 합산 TPS@c | 효율 배치 | "
             "SWE-bench resolved |")
    L.append("|---|---|--:|--:|--:|--:|--:|")
    for model in models:
        tasks = by_model[model]
        tps = _tps_summary(tasks)
        scl = analyze_scaling(_sweep_rows(tasks, SWEEP_PROMPT_LEN))
        meta = model_meta.get(model, {})
        devs = "—"
        for a in (meta.get("serve_args") or []):
            pass
        sa = meta.get("serve_args") or []
        if "--devices" in sa:
            devs = sa[sa.index("--devices") + 1]
        elif meta:
            devs = devices_default
        sb = _swebench(RESULTS_ROOT / model.replace("/", "__"))
        sb_txt = "—"
        if sb:
            tot = sb.get("total_instances") or 0
            res = sb.get("resolved_instances") or 0
            sb_txt = f"{res}/{tot} ({100*res/tot:.1f}%)" if tot else "—"
        peak = (f"{scl['peak_tps']:.0f}@c{scl['peak_c']}"
                if scl else "—")
        eff = f"c{scl['efficient_c']}" if scl else "—"
        L.append(f"| `{model}` | {devs} | "
                 f"{tps.get('ttft_s_p50','—')} | "
                 f"{tps.get('output_tps_per_request_p50','—')} | "
                 f"{peak} | {eff} | {sb_txt} |")
    L.append("")

    # --- 2. 단일 요청 속도 ---
    L.append("## 2. 단일 요청 토큰 생성 속도 (concurrency=1)")
    L.append("")
    L.append("| 모델 | TTFT p50(s) | TTFT p95(s) | ITL p50(s) | "
             "출력 TPS p50 | 합산 TPS |")
    L.append("|---|--:|--:|--:|--:|--:|")
    for model in models:
        tps = _tps_summary(by_model[model])
        if not tps:
            continue
        L.append(f"| `{model}` | {tps.get('ttft_s_p50','—')} | "
                 f"{tps.get('ttft_s_p95','—')} | {tps.get('itl_s_p50','—')} | "
                 f"{tps.get('output_tps_per_request_p50','—')} | "
                 f"{tps.get('aggregate_output_tps','—')} |")
    L.append("")

    # --- 3. 배치/동시성 스케일링 ---
    L.append("## 3. 배치/동시성 스케일링 (prompt_len="
             f"{SWEEP_PROMPT_LEN})")
    L.append("")
    L.append("동시 접속자 수(=concurrency)를 늘릴 때 합산 처리량과 지연이 어떻게 변하는지. "
             "**효율 배치**=가성비 정점, **무감소 최대**=실패·지연열화 없는 최대 동시성, "
             "**감소 시작**=이 동시성부터 성능 저하.")
    L.append("")
    for model in models:
        rows = _sweep_rows(by_model[model], SWEEP_PROMPT_LEN)
        if not rows:
            continue
        L.append(f"### {model}")
        L.append("")
        L.append("| 동시성 | 합산 TPS | 요청당 TPS p50 | TTFT p95(s) | "
                 "ITL p50(s) | 실패 |")
        L.append("|--:|--:|--:|--:|--:|--:|")
        for r in rows:
            if "error" in r and "aggregate_output_tps" not in r:
                L.append(f"| {r.get('concurrency','?')} | — | — | — | — | "
                         f"ERR |")
                continue
            L.append(f"| {r.get('concurrency','?')} | "
                     f"{r.get('aggregate_output_tps','—')} | "
                     f"{r.get('output_tps_per_request_p50','—')} | "
                     f"{r.get('ttft_s_p95','—')} | {r.get('itl_s_p50','—')} | "
                     f"{r.get('failures','—')} |")
        scl = analyze_scaling(rows)
        if scl:
            deg = scl["degrade_c"] if scl["degrade_c"] is not None else "관측 안 됨"
            L.append("")
            L.append(f"- **효율 배치**: 동시성 {scl['efficient_c']} "
                     f"(합산 {scl['efficient_tps']:.0f} TPS, "
                     f"peak {scl['peak_tps']:.0f} TPS@c{scl['peak_c']}의 "
                     f"{100*scl['efficient_tps']/scl['peak_tps']:.0f}%)")
            L.append(f"- **무감소 최대 동시성**: {scl['max_no_degrade_c']}")
            L.append(f"- **성능 감소 시작 동시성**: {deg}")
        L.append("")

    # --- 4. memsweep ---
    L.append("## 4. serve 옵션 스윕 (memsweep) — KV cache / batch 설정 효과")
    L.append("")
    L.append("baseline(furiosa-llm 기본값)에서 한 축씩만 바꿔 측정. 합산 TPS 기준 정렬.")
    L.append("")
    for model in models:
        mem = _best_memsweep(by_model[model].get("memsweep", []))
        if not mem:
            continue
        L.append(f"### {model}")
        L.append("")
        L.append("| serve 옵션 조합 | 합산 TPS | 실패 |")
        L.append("|---|--:|--:|")
        for tps, combo, bench in mem["all"]:
            combo_txt = "baseline" if not combo else json.dumps(
                combo, ensure_ascii=False)
            L.append(f"| `{combo_txt}` | {tps:.0f} | "
                     f"{bench.get('failures','—')} |")
        L.append("")
        L.append(f"- **최적 조합**: `{json.dumps(mem['combo'], ensure_ascii=False)}` "
                 f"→ {mem['summary'].get('aggregate_output_tps','—')} TPS")
        L.append("")

    # --- 5. SWE-bench ---
    L.append("## 5. SWE-bench (코드 수정 정확도)")
    L.append("")
    L.append("SWE-bench Lite oracle, single-shot diff 생성. "
             "**resolved**=테스트 통과, **unresolved**=패치 적용됐으나 미해결, "
             "**적용실패**=malformed diff 등으로 patch 적용 불가(harness error), "
             "**추론오류**=서버 응답 실패(context 초과 등).")
    L.append("")
    L.append("| 모델 | resolved | unresolved | 적용실패 | 빈 패치 | 추론오류 | total | resolved % |")
    L.append("|---|--:|--:|--:|--:|--:|--:|--:|")
    high_err = []
    for model in models:
        sb = _swebench(RESULTS_ROOT / model.replace("/", "__"))
        pred = _swebench_pred_summary(by_model[model])
        if not sb and not pred:
            continue
        if sb:
            tot = sb.get("total_instances") or 0
            res = sb.get("resolved_instances") or 0
            unres = sb.get("unresolved_instances") or 0
            err = sb.get("error_instances") or 0
            empty = sb.get("empty_patch_instances") or 0
            pct = f"{100*res/tot:.1f}%" if tot else "—"
            L.append(f"| `{model}` | {res} | {unres} | {err} | {empty} | "
                     f"{pred.get('n_error','—')} | {tot} | {pct} |")
            if tot and err / tot >= 0.2:
                high_err.append((model, err, tot))
        else:
            L.append(f"| `{model}` | (미채점) | — | — | — | "
                     f"{pred.get('n_error','—')} | — | — |")
    L.append("")
    for model, err, tot in high_err:
        L.append(f"> ⚠ `{model}`: {err}/{tot} 가 **적용실패** — 모델이 정확한 "
                 "unified diff를 못 만든 비율이 높음. resolved %가 실제 코드 수정 "
                 "능력보다 낮게 나올 수 있음 (diff 포맷 한계 + 모델 역량 혼재).")
    L.append("")

    # --- 6. Embedding / Reranker ---
    L.append("## 6. Embedding / Reranker 처리량")
    L.append("")
    L.append("| 모델 | 종류 | batch=1 | batch=16 | batch=64 |")
    L.append("|---|---|--:|--:|--:|")
    for model in models:
        tasks = by_model[model]
        for kind in ("embed", "rerank"):
            objs = tasks.get(kind) or []
            if not objs:
                continue
            row = {1: "—", 16: "—", 64: "—"}
            for o in objs:
                for r in o.get("results", []):
                    s = r.get("summary") or {}
                    bs = s.get("batch_size")
                    if bs in row:
                        row[bs] = s.get("throughput_inputs_per_s", "—")
                s = o.get("summary") or {}
                if "throughput_pairs_per_s" in s:
                    row[1] = s["throughput_pairs_per_s"]
            L.append(f"| `{model}` | {kind} | {row[1]} | {row[16]} | {row[64]} |")
    L.append("")

    # --- 7. NPU 요구량 & 동시 접속자별 권장 설정 ---
    L.append("## 7. NPU 요구량 & 동시 접속자별 권장 서빙 설정")
    L.append("")
    L.append("| 모델 | NPU 카드 | 권장 동시성(효율) | 무감소 한계 | 권장 serve 옵션 |")
    L.append("|---|---|--:|--:|---|")
    for model in models:
        tasks = by_model[model]
        meta = model_meta.get(model, {})
        sa = meta.get("serve_args") or []
        devs = sa[sa.index("--devices") + 1] if "--devices" in sa else devices_default
        ncard = len(set(devs.split(","))) if devs else 1
        scl = analyze_scaling(_sweep_rows(tasks, SWEEP_PROMPT_LEN))
        mem = _best_memsweep(tasks.get("memsweep", []))
        eff = f"{scl['efficient_c']}" if scl else "—"
        mx = f"{scl['max_no_degrade_c']}" if scl else "—"
        combo = (json.dumps(mem["combo"], ensure_ascii=False)
                 if mem and mem["combo"] else ("baseline" if mem else "—"))
        L.append(f"| `{model}` | {ncard} ({devs}) | {eff} | {mx} | `{combo}` |")
    L.append("")

    # --- 8. 종합 결론 ---
    L.append("## 8. 종합 — 코드 생성 적합도 점수")
    L.append("")
    L.append("코드 생성 모델 선정은 **정확도(SWE-bench) > 처리량 > 지연** 우선순위로 평가. "
             "각 지표를 측정된 모델 중 최대값 대비 0~1로 정규화 후 가중합 "
             "(SWE-bench 0.5, peak 합산 TPS 0.3, 단일 TPS 0.2). "
             "embedding/reranker(생성 모델 아님)와 smoke 역할(파이프라인 검증용 0.5B)은 제외.")
    L.append("")
    gen_scores = []
    sb_max = tps_max = peak_max = 0.0
    raw = {}
    for model in models:
        meta = model_meta.get(model, {})
        if not meta.get("gen", True) or meta.get("role") == "smoke":
            continue
        tasks = by_model[model]
        tps = _tps_summary(tasks)
        scl = analyze_scaling(_sweep_rows(tasks, SWEEP_PROMPT_LEN))
        sb = _swebench(RESULTS_ROOT / model.replace("/", "__"))
        sb_pct = 0.0
        if sb and sb.get("total_instances"):
            sb_pct = 100 * (sb.get("resolved_instances") or 0) / sb["total_instances"]
        single = _num(tps.get("output_tps_per_request_p50"), 0.0) or 0.0
        peak = scl["peak_tps"] if scl else 0.0
        raw[model] = (sb_pct, single, peak)
        sb_max = max(sb_max, sb_pct)
        tps_max = max(tps_max, single)
        peak_max = max(peak_max, peak)
    for model, (sb_pct, single, peak) in raw.items():
        score = (0.5 * (sb_pct / sb_max if sb_max else 0)
                 + 0.2 * (single / tps_max if tps_max else 0)
                 + 0.3 * (peak / peak_max if peak_max else 0))
        gen_scores.append((score, model, sb_pct, single, peak))
    gen_scores.sort(reverse=True)
    if len(gen_scores) >= 2:
        L.append("| 순위 | 모델 | 종합점수 | SWE-bench % | 단일 TPS | peak 합산 TPS |")
        L.append("|--:|---|--:|--:|--:|--:|")
        for i, (score, model, sb_pct, single, peak) in enumerate(gen_scores, 1):
            L.append(f"| {i} | `{model}` | {score:.3f} | {sb_pct:.1f} | "
                     f"{single:.1f} | {peak:.0f} |")
        L.append("")
        best = gen_scores[0]
        L.append(f"> **1위: `{best[1]}`** (종합점수 {best[0]:.3f}).")
    elif len(gen_scores) == 1:
        _, model, sb_pct, single, peak = gen_scores[0]
        L.append(f"측정 가능한 코드 생성 모델은 **`{model}`** 단독이다 "
                 f"(SWE-bench {sb_pct:.1f}%, 단일 {single:.0f} TPS, "
                 f"peak 합산 {peak:.0f} TPS). 코드 생성 강력 후보인 32B/70B는 "
                 "하드웨어 제약으로 제외돼 **모델 간 순위 비교는 성립하지 않는다** — "
                 "이 머신에서의 결론은 사실상 가용 모델 단독 선택이다.")
    else:
        L.append("_(생성 모델 결과 부족)_")
    L.append("")

    # 측정 제외 모델 (하드웨어 제약) 명시
    disabled = [m["id"] for m in cfg.get("models", []) if not m.get("enabled", True)]
    if disabled:
        L.append("### 측정 제외 모델 (하드웨어 제약)")
        L.append("")
        L.append("아래 모델은 prebuilt 아티팩트가 `tensor_parallel=32` (RNGD 4장 = 32 PE)로 "
                 "컴파일돼 있어 현재 2장(16 PE) 머신에서 서빙 불가 → 평가 제외:")
        L.append("")
        for d in disabled:
            L.append(f"- `{d}`")
        L.append("")
        L.append("> RNGD 4장 이상 머신에서 `configs/models.yaml`의 `enabled: true`로 "
                 "바꾸면 코드 수정 없이 동일 파이프라인으로 측정된다. 32B/70B는 통상 "
                 "SWE-bench 정확도가 8B보다 높으므로, 정확도 우선이라면 4장 환경 측정 권장.")
        L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "REPORT.md")
    args = ap.parse_args()
    by_model = _load()
    text = render(by_model)
    args.out.write_text(text)
    print(text)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
