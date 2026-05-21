"""모델별 종합 비교 리포트 (Markdown) 생성 — Furiosa RNGD / furiosa-llm.

results/ 아래 task JSON을 모아 자동 산출:
  1. TL;DR  2. 단일 요청 속도  3. 배치/동시성 스케일링  4. memsweep
  5. SWE-bench  6. Embedding/Reranker  7. 동시 접속자별 권장 설정  8. 종합 결론
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
RESULTS_ROOT = REPO_ROOT / "results"
CONFIG_PATH = REPO_ROOT / "configs" / "models.yaml"

SLA_TTFT_P95_S = 10.0
EFFICIENT_FRAC = 0.90
SWEEP_PROMPT_LEN = 1024


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
                if isinstance(obj, dict):
                    obj["_result_file"] = str(f)
                    obj["_result_mtime"] = f.stat().st_mtime
                if obj is not None:
                    by_model[model][task_dir.name].append(obj)
    return by_model


def _mtime(o) -> float:
    return float(o.get("_result_mtime", 0.0)) if isinstance(o, dict) else 0.0


def _latest_dict(objs: list) -> dict:
    dicts = [o for o in objs if isinstance(o, dict)]
    return max(dicts, key=_mtime) if dicts else {}


def _tps_summary(tasks: dict) -> dict:
    latest = _latest_dict(tasks.get("tps", []))
    s = latest.get("summary") if latest else None
    return s if s and "error" not in s else {}


def _sweep_rows(tasks: dict, prompt_len=None) -> list[dict]:
    latest = _latest_dict(tasks.get("sweep", []))
    rows: list[dict] = list(latest.get("sweep", [])) if latest else []
    if prompt_len is not None:
        rows = [r for r in rows if r.get("prompt_tokens_target") == prompt_len]
    by_c: dict = {}
    for r in rows:
        by_c[r.get("concurrency")] = r
    return [by_c[c] for c in sorted(by_c, key=lambda x: (x is None, x))]


def _ok(row: dict) -> bool:
    return ("error" not in row and row.get("failures", 1) == 0
            and row.get("aggregate_output_tps") is not None)


def analyze_scaling(rows: list[dict]) -> dict:
    ok = [r for r in rows if _ok(r)]
    if not ok:
        return {}
    peak = max(ok, key=lambda r: r["aggregate_output_tps"])
    peak_tps = peak["aggregate_output_tps"]
    efficient = next(
        (r for r in ok if r["aggregate_output_tps"] >= EFFICIENT_FRAC * peak_tps), peak)
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
        "peak_c": peak["concurrency"], "peak_tps": peak_tps,
        "efficient_c": efficient["concurrency"], "efficient_tps": efficient["aggregate_output_tps"],
        "max_no_degrade_c": ok[-1]["concurrency"], "degrade_c": degrade_c,
    }


def _best_memsweep(mem_objs: list) -> dict | None:
    summaries = [o for o in mem_objs if isinstance(o, list)]
    if summaries:
        flat = max(summaries, key=lambda rows: max((_mtime(r) for r in rows if isinstance(r, dict)), default=0.0))
    else:
        flat = [o for o in mem_objs if isinstance(o, dict)]
    scored, seen = [], set()
    for r in flat:
        if not isinstance(r, dict) or r.get("status") == "error":
            continue
        bench = r.get("bench") or r.get("summary")
        if not bench or bench.get("aggregate_output_tps") is None or bench.get("failures", 0):
            continue
        server_models = _server_model_ids(r.get("server_info") or {})
        if server_models and bench.get("model") not in server_models:
            continue
        combo = r.get("combo") or {}
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


def _server_model_ids(server_info: dict) -> set[str]:
    data = ((server_info.get("/models") or {}).get("data") or [])
    ids: set[str] = set()
    for item in data:
        for key in ("id", "root"):
            if item.get(key):
                ids.add(item[key])
    return ids


def _swebench(model_dir: Path) -> dict | None:
    f = model_dir / "swebench" / "eval_result.json"
    if not f.exists():
        return None
    obj = _read_json(f) or {}
    return obj.get("report")


def _swebench_pred_summary(tasks: dict) -> dict:
    objs = [o for o in tasks.get("swebench", [])
            if isinstance(o, dict) and "n_instances" in o]
    return max(objs, key=_mtime) if objs else {}


def _num(x, default=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _model_devices(meta: dict, default_devices: str) -> str:
    sa = meta.get("serve_args") or []
    if "--devices" in sa:
        return sa[sa.index("--devices") + 1]
    return default_devices


def render(by_model: dict) -> str:
    cfg = _load_config()
    devices_default = str(cfg.get("devices", "npu:0"))
    model_meta = {m["id"]: m for m in cfg.get("models", [])}

    L: list[str] = []
    L.append("# Furiosa RNGD (furiosa-llm) — 코드 생성 모델 벤치마크 리포트")
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
    L.append("| 모델 | NPU | TTFT p50(s) | 단일 TPS | peak 합산 TPS@c | 효율 배치 | SWE-bench resolved |")
    L.append("|---|---|--:|--:|--:|--:|--:|")
    for model in models:
        tasks = by_model[model]
        tps = _tps_summary(tasks)
        scl = analyze_scaling(_sweep_rows(tasks, SWEEP_PROMPT_LEN))
        devs = _model_devices(model_meta.get(model, {}), devices_default)
        sb = _swebench(RESULTS_ROOT / model.replace("/", "__"))
        sb_txt = "—"
        if sb:
            tot = sb.get("total_instances") or 0
            res = sb.get("resolved_instances") or 0
            sb_txt = f"{res}/{tot} ({100*res/tot:.1f}%)" if tot else "—"
        peak = f"{scl['peak_tps']:.0f}@c{scl['peak_c']}" if scl else "—"
        eff = f"c{scl['efficient_c']}" if scl else "—"
        L.append(f"| `{model}` | {devs} | {tps.get('ttft_s_p50','—')} | "
                 f"{tps.get('output_tps_per_request_p50','—')} | {peak} | {eff} | {sb_txt} |")
    L.append("")

    # --- 2. 단일 요청 속도 ---
    L.append("## 2. 단일 요청 토큰 생성 속도 (concurrency=1)")
    L.append("")
    L.append("| 모델 | TTFT p50(s) | TTFT p95(s) | ITL p50(s) | 출력 TPS p50 | 합산 TPS |")
    L.append("|---|--:|--:|--:|--:|--:|")
    for model in models:
        tps = _tps_summary(by_model[model])
        if not tps:
            continue
        L.append(f"| `{model}` | {tps.get('ttft_s_p50','—')} | {tps.get('ttft_s_p95','—')} | "
                 f"{tps.get('itl_s_p50','—')} | {tps.get('output_tps_per_request_p50','—')} | "
                 f"{tps.get('aggregate_output_tps','—')} |")
    L.append("")

    # --- 3. 배치/동시성 스케일링 ---
    L.append(f"## 3. 배치/동시성 스케일링 (prompt_len={SWEEP_PROMPT_LEN})")
    L.append("")
    for model in models:
        rows = _sweep_rows(by_model[model], SWEEP_PROMPT_LEN)
        if not rows:
            continue
        L.append(f"### {model}")
        L.append("")
        L.append("| 동시성 | 합산 TPS | 요청당 TPS p50 | TTFT p95(s) | ITL p50(s) | 실패 |")
        L.append("|--:|--:|--:|--:|--:|--:|")
        for r in rows:
            if "error" in r and "aggregate_output_tps" not in r:
                L.append(f"| {r.get('concurrency','?')} | — | — | — | — | ERR |")
                continue
            L.append(f"| {r.get('concurrency','?')} | {r.get('aggregate_output_tps','—')} | "
                     f"{r.get('output_tps_per_request_p50','—')} | {r.get('ttft_s_p95','—')} | "
                     f"{r.get('itl_s_p50','—')} | {r.get('failures','—')} |")
        scl = analyze_scaling(rows)
        if scl:
            deg = scl["degrade_c"] if scl["degrade_c"] is not None else "관측 안 됨"
            L.append("")
            L.append(f"- **효율 배치**: 동시성 {scl['efficient_c']} "
                     f"(합산 {scl['efficient_tps']:.0f} TPS, peak {scl['peak_tps']:.0f} "
                     f"TPS@c{scl['peak_c']})")
            L.append(f"- **무감소 최대 동시성**: {scl['max_no_degrade_c']} · "
                     f"**성능 감소 시작**: {deg}")
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
            combo_txt = "baseline" if not combo else json.dumps(combo, ensure_ascii=False)
            L.append(f"| `{combo_txt}` | {tps:.0f} | {bench.get('failures','—')} |")
        L.append("")
        L.append(f"- **최적 조합**: `{json.dumps(mem['combo'], ensure_ascii=False)}` "
                 f"→ {mem['summary'].get('aggregate_output_tps','—')} TPS")
        L.append("")

    # --- 5. SWE-bench ---
    L.append("## 5. SWE-bench (코드 수정 정확도)")
    L.append("")
    L.append("SWE-bench Lite oracle, single-shot. resolved=테스트 통과, "
             "unresolved=적용됐으나 미해결, 적용실패=malformed diff, "
             "컨텍스트제외=서버 context 한계를 넘어 사전 제외.")
    L.append("")
    L.append("| 모델 | resolved | unresolved | 적용실패 | 빈 패치 | 추론오류 | 컨텍스트제외 | 형식의심 | total | resolved % |")
    L.append("|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|")
    high_err = []
    for model in models:
        sb = _swebench(RESULTS_ROOT / model.replace("/", "__"))
        pred = _swebench_pred_summary(by_model[model])
        if not sb and not pred:
            continue
        if sb:
            tot = sb.get("total_instances") or 0
            res = sb.get("resolved_instances") or 0
            err = sb.get("error_instances") or 0
            pct = f"{100*res/tot:.1f}%" if tot else "—"
            L.append(f"| `{model}` | {res} | {sb.get('unresolved_instances',0)} | "
                     f"{err} | {sb.get('empty_patch_instances',0)} | "
                     f"{pred.get('n_error','—')} | {pred.get('n_filtered_context',0)} | "
                     f"{pred.get('n_invalid_patch','—')} | {tot} | {pct} |")
            if tot and err / tot >= 0.2:
                high_err.append((model, err, tot))
        else:
            L.append(f"| `{model}` | (미채점) | — | — | — | {pred.get('n_error','—')} | "
                     f"{pred.get('n_filtered_context',0)} | {pred.get('n_invalid_patch','—')} | — | — |")
    L.append("")
    for model, err, tot in high_err:
        L.append(f"> ⚠ `{model}`: {err}/{tot} 가 **적용실패** — 모델이 정확한 unified diff를 "
                 "못 만든 비율이 높음. resolved %가 실제 코드 수정 능력보다 낮게 나올 수 있음 "
                 "(diff 포맷 한계 + 모델 역량 혼재).")
    if high_err:
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
                    if s.get("batch_size") in row:
                        row[s["batch_size"]] = s.get("throughput_inputs_per_s", "—")
                s = o.get("summary") or {}
                if "throughput_pairs_per_s" in s:
                    row[1] = s["throughput_pairs_per_s"]
            L.append(f"| `{model}` | {kind} | {row[1]} | {row[16]} | {row[64]} |")
    L.append("")

    # --- 7. 동시 접속자별 권장 ---
    L.append("## 7. NPU 요구량 & 동시 접속자별 권장 서빙 설정")
    L.append("")
    L.append("| 모델 | NPU 카드 | 권장 동시성(효율) | 무감소 한계 | 권장 serve 옵션 |")
    L.append("|---|---|--:|--:|---|")
    for model in models:
        tasks = by_model[model]
        meta = model_meta.get(model, {})
        devs = _model_devices(meta, devices_default)
        ncard = len(set(devs.split(","))) if devs else 1
        scl = analyze_scaling(_sweep_rows(tasks, SWEEP_PROMPT_LEN))
        mem = _best_memsweep(tasks.get("memsweep", []))
        eff = f"{scl['efficient_c']}" if scl else "—"
        mx = f"{scl['max_no_degrade_c']}" if scl else "—"
        combo = (json.dumps(mem["combo"], ensure_ascii=False)
                 if mem and mem["combo"] else ("baseline" if mem else "—"))
        L.append(f"| `{model}` | {ncard} ({devs}) | {eff} | {mx} | `{combo}` |")
    L.append("")

    # --- 8. 종합 ---
    L.append("## 8. 종합 — 코드 생성 적합도 점수")
    L.append("")
    L.append("정확도(SWE-bench 0.5) + peak 합산 TPS(0.3) + 단일 TPS(0.2) 가중합 "
             "(각 지표는 측정 모델 중 최대값 대비 정규화). embedding/reranker·smoke 제외.")
    L.append("")
    raw, sb_max, tps_max, peak_max = {}, 0.0, 0.0, 0.0
    for model in models:
        meta = model_meta.get(model, {})
        if not meta.get("gen", True) or meta.get("role") == "smoke":
            continue
        tasks = by_model[model]
        tps = _tps_summary(tasks)
        scl = analyze_scaling(_sweep_rows(tasks, SWEEP_PROMPT_LEN))
        sb = _swebench(RESULTS_ROOT / model.replace("/", "__"))
        sb_pct = 100 * (sb.get("resolved_instances") or 0) / sb["total_instances"] \
            if sb and sb.get("total_instances") else 0.0
        single = _num(tps.get("output_tps_per_request_p50"), 0.0) or 0.0
        peak = scl["peak_tps"] if scl else 0.0
        raw[model] = (sb_pct, single, peak)
        sb_max, tps_max, peak_max = max(sb_max, sb_pct), max(tps_max, single), max(peak_max, peak)
    scores = []
    for model, (sb_pct, single, peak) in raw.items():
        score = (0.5 * (sb_pct / sb_max if sb_max else 0)
                 + 0.2 * (single / tps_max if tps_max else 0)
                 + 0.3 * (peak / peak_max if peak_max else 0))
        scores.append((score, model, sb_pct, single, peak))
    scores.sort(reverse=True)
    if len(scores) >= 2:
        L.append("| 순위 | 모델 | 종합점수 | SWE-bench % | 단일 TPS | peak 합산 TPS |")
        L.append("|--:|---|--:|--:|--:|--:|")
        for i, (score, model, sb_pct, single, peak) in enumerate(scores, 1):
            L.append(f"| {i} | `{model}` | {score:.3f} | {sb_pct:.1f} | {single:.1f} | {peak:.0f} |")
        L.append("")
        L.append(f"> **종합 1위: `{scores[0][1]}`** (종합점수 {scores[0][0]:.3f}).")
    elif len(scores) == 1:
        _, model, sb_pct, single, peak = scores[0]
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
                 "컴파일돼 있어 현재 머신 PE 예산 안에서 서빙 불가 → 평가 제외:")
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
    text = render(_load())
    args.out.write_text(text)
    print(text)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
