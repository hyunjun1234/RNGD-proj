# HF 모델 컴파일해서 RNGD에서 실행 — 자가 수행 가이드

출처:
- 모델 준비: https://developer.furiosa.ai/latest/en/furiosa_llm/model-preparation.html
- 병렬화: https://developer.furiosa.ai/latest/en/furiosa_llm/model-parallelism.html
- 지원 모델: https://developer.furiosa.ai/latest/en/overview/supported_models.html

워크플로: `HF 모델` → `[선택] FP8 양자화` → `furiosa-llm build` → `아티팩트` → `furiosa-llm serve`

각 단계에 **확인** = 성공 판정, **실패 시** = 증상별 조치.

---

## 지원 아키텍처

`furiosa-llm build`가 받는 model_type (SDK 2026.2.0 코드 기준):
`llama` `qwen2` `qwen3` `qwen3_moe` `exaone4` `gpt2` `gpt_oss`

| 용도 | model_type / 아키텍처 | 공식 상태 |
|---|---|---|
| text-gen (decoder) | `llama` `qwen2` `qwen3` `exaone4` | 검증·prebuilt 제공 |
| 임베딩 | `qwen3` / `Qwen3Model` | 검증·prebuilt 제공 |
| 리랭킹 | `qwen3` / `Qwen3ForSequenceClassification` | 검증·prebuilt 제공 |
| 미검증 | `qwen3_moe` `gpt2` `gpt_oss` | 공식 "planned". SDK 코드엔 존재(`qwen3_moe`는 버킷 프리셋도) — 빌드 시도는 되나 성공·정확도 미보장 |

- 임베딩/리랭킹은 pooling task — 빌드·서빙 옵션이 아래 decoder 흐름(1~6절)과 다름.
- 자동 버킷 프리셋 보유 model_type (`furiosa_llm/artifact/presets.py`): `qwen2` `exaone4` `llama` `qwen3` `qwen3_moe`. 프리셋과 `(model_type, hidden_size, intermediate_size)`가 일치하면 버킷 자동, 아니면 `-pb`/`-db` 수동.

```bash
python3 -c "
from huggingface_hub import hf_hub_download; import json
print(json.load(open(hf_hub_download('Qwen/Qwen2.5-1.5B-Instruct','config.json')))['model_type'])"
```
**확인**: 출력이 위 목록에 있어야 함. 없으면 빌드 불가.

## PE / 메모리 예산

- RNGD 1장 = 8 PE. 이 머신 = 2장 = **16 PE**. 빌드 시 `tp×pp ≤ 16`.
- 1장 HBM ≈ 48GB (관측: 8B bf16 weight+KV로 1장 ~43GB 사용).
- weight 메모리 ≈ 파라미터수 × (bf16: 2 byte / FP8: 1 byte).
- 서빙 시 HBM = weight + KV cache. 둘 합이 `tp` PE 분량 HBM 안에 들어가야 함.

| 모델 | dtype | weight | 권장 tp | 카드 |
|---|---|--:|--:|--:|
| ~1.5B | bf16 | ~3GB | 4–8 | ≤1 |
| ~8B | bf16 | ~16GB | 8 | 1 |
| ~32B | bf16 | ~64GB | 16 | 2 |
| ~32B | FP8 | ~32GB | 8–16 | 1–2 |

---

## 0. 환경

```bash
source ~/furiosa/bin/activate
```

## 1. 모델 다운로드

```bash
pip install --upgrade huggingface_hub
hf auth login --token $HF_TOKEN          # gated 모델만 필요
hf download "Qwen/Qwen2.5-1.5B-Instruct"
```
**확인**: `~/.cache/huggingface/hub/models--Qwen--Qwen2.5-1.5B-Instruct/` 에 `*.safetensors` 존재.
**실패 시**: gated 모델 403 → HF 사이트에서 라이선스 동의 + 토큰 재확인.

## 2. (선택) FP8 양자화

bf16으로 쓸 거면 건너뜀 → 3절로. FP8 = HBM 절반·속도↑ (prebuilt 방식).

```python
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, FineGrainedFP8Config

model_id  = "Qwen/Qwen2.5-1.5B-Instruct"
save_path = "./qwen2.5-1.5b-fp8"

quantization_config = FineGrainedFP8Config(
    activation_scheme="dynamic",
    weight_block_size=(128, 128),
)
model = AutoModelForCausalLM.from_pretrained(
    model_id, device_map="auto",
    quantization_config=quantization_config, torch_dtype=torch.bfloat16,
)
tokenizer = AutoTokenizer.from_pretrained(model_id)
model.save_pretrained(save_path)
tokenizer.save_pretrained(save_path)
```
- furiosa 지원 = fine-grained FP8 **dynamic**. HF의 임의 FP8 repo는 양자화 방식이 다를 수 있음 → 위 방식으로 직접 양자화 권장.
- `device_map="auto"`: GPU 없으면 CPU(느림). host RAM에 모델 bf16 전체가 올라가야 함.

**확인**: `save_path`에 `*.safetensors` + `config.json` 생성, `config.json`에 `quantization_config` 포함.
**실패 시**: host RAM 부족 → bf16으로 진행(2절 생략) 또는 더 작은 모델.

## 3. 아티팩트 빌드

입력 = HF id (bf16) 또는 2절 양자화 결과 로컬 경로.

### 3a. CLI

```bash
furiosa-llm build \
    Qwen/Qwen2.5-1.5B-Instruct \          # 또는 ./qwen2.5-1.5b-fp8
    ~/RNGD-proj/Model_Benchmark/rngd-npu/artifacts/qwen2.5-1.5b \      # 출력 경로
    -tp 8 \
    --max-model-len 4096 \
    --num-compile-workers 4
```

### 3b. Python API

```python
from furiosa_llm.artifact import ArtifactBuilder, ModelConfig, ParallelConfig

builder = ArtifactBuilder(
    model_id_or_path="Qwen/Qwen2.5-1.5B-Instruct",
    model_config=ModelConfig(max_model_len=4096),
    parallel_config=ParallelConfig(tensor_parallel_size=8, pipeline_parallel_size=1),
)
builder.build("/home/jun/RNGD-proj/Model_Benchmark/rngd-npu/artifacts/qwen2.5-1.5b")
```

| CLI | Python | 의미 |
|---|---|---|
| `-tp N` | `ParallelConfig(tensor_parallel_size=N)` | PE 수 (기본 8) |
| `-pp N` | `ParallelConfig(pipeline_parallel_size=N)` | pipeline 단수 (기본 1) |
| `--max-model-len N` | `ModelConfig(max_model_len=N)` | 최대 context |
| `-pb b,c` / `-db b,c` | `BucketConfig(prefill_buckets=[(b,c)], decode_buckets=[(b,c)])` | 버킷 (미지정 시 2026.2+ 자동 preset) |
| `--num-compile-workers N` | — | 컴파일 병렬도 |
| `--trust-remote-code` | `ModelConfig(trust_remote_code=True)` | HF 커스텀 코드 |
| `--cache-dir DIR` | — | 빌드 캐시 (기본 `~/.cache/furiosa/llm`) |

**확인**:
- 출력 경로에 `artifact.json` + `binary_bundle.zip` + `config.json` + 토크나이저 생성.
- tp 값 확인:
  ```bash
  python3 -c "import json;print(json.load(open('$HOME/RNGD-proj/Model_Benchmark/rngd-npu/artifacts/qwen2.5-1.5b/artifact.json'))['model']['parallel_config'])"
  ```
- build는 host(CPU/RAM) AOT 컴파일 — NPU 불필요. 빌드 중 다른 터미널에서 `furiosa-smi info` 시 Power/Temp 변화 없어야 함.

**실패 시**:
- host RAM OOM → `--num-compile-workers`, `--num-pipeline-builder-workers` 를 1로.
- 컴파일 에러 → `tp` 또는 `--max-model-len` 조정 후 재시도.

## 4. 서빙

```bash
furiosa-llm serve ~/RNGD-proj/Model_Benchmark/rngd-npu/artifacts/qwen2.5-1.5b \
    --devices npu:0 --host 0.0.0.0 --port 8000
```
**확인**: 로그에 `Uvicorn running on http://0.0.0.0:8000`.
**실패 시**:
- `Required PEs: N, Actual: M` → 빌드 tp ≠ `--devices` PE 수. `--devices`를 늘리거나 작은 tp로 재빌드.
- HBM OOM → `--max-model-len` 축소, 또는 FP8로 재빌드.

## 5. 테스트

```bash
curl -s http://127.0.0.1:8000/v1/models | python3 -m json.tool
curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen2.5-1.5b","messages":[{"role":"user","content":"Write a Python function to reverse a string."}],"max_tokens":128}' \
  | python3 -m json.tool
```
**확인**: `/v1/models`에 모델 표시, `/v1/chat/completions`가 코드 포함 응답 반환.

## 6. 벤치마크 프레임워크에 등록

`configs/models.yaml`의 `models:`에 추가 (`id` = 로컬 아티팩트 절대경로):

```yaml
  - id: /home/jun/RNGD-proj/Model_Benchmark/rngd-npu/artifacts/qwen2.5-1.5b
    revision: null
    role: main
    gen: true
    enabled: true
    serve_args: []
```
```bash
python orchestrator.py configs/models.yaml --tasks tps,sweep --models qwen2.5-1.5b
```

---

## 7. prebuilt 32B/70B를 더 적은 카드로 재빌드 시도

prebuilt 아티팩트(`furiosa-ai/Qwen3-32B-FP8` 등)는 `binary_bundle.zip`이 **tp=32(4장)로
컴파일**돼 있음. `artifact.json`의 숫자만 바꾸는 건 불가 — 메타데이터일 뿐 binary는
그대로 32 PE용. 또한 prebuilt repo엔 `binary_bundle.zip`만 있고 재빌드용 safetensors
weight가 **없음** → 원본 HF weight에서 다시 시작해야 함.

**실측 (2026-05-18 · `artifacts/qwen3-32b-fp8-tphack/`):** prebuilt `furiosa-ai/Qwen3-32B-FP8`의
`binary_bundle.zip`을 symlink하고 `artifact.json` 메타만 2장용으로 고친 artifact를 2장에 serve →
패닉 (`tphack_serve.log`):

```
panicked at itertools .../zip_eq_impl.rs: .zip_eq() reached end of one iterator before the other
```

→ 메타데이터 해킹은 불가로 **확인됨**. 아래 풀 재빌드만 유효.

### 절차 (Qwen3-32B를 2장=tp16으로)

```bash
source ~/furiosa/bin/activate

# 1) 원본 weight 다운로드 (bf16)
hf download Qwen/Qwen3-32B

# 2) 빌드 — 경로 A(bf16, 간단) 또는 B(FP8, HBM 절약) 중 택1

# A) bf16 그대로: 32B bf16 weight ~64GB → tp16(2장 HBM 합산 ~96GB)에 빠듯
furiosa-llm build Qwen/Qwen3-32B ~/RNGD-proj/Model_Benchmark/rngd-npu/artifacts/qwen3-32b-tp16 \
    -tp 16 --max-model-len 4096 --num-compile-workers 4

# B) FP8 후 빌드: 2절 FineGrainedFP8Config로 양자화(host RAM ~64GB+ 필요) → save_path
#    그 결과로 빌드
furiosa-llm build ./qwen3-32b-fp8 ~/RNGD-proj/Model_Benchmark/rngd-npu/artifacts/qwen3-32b-tp16 \
    -tp 16 --max-model-len 4096 --num-compile-workers 4

# 3) 서빙 (2장)
furiosa-llm serve ~/RNGD-proj/Model_Benchmark/rngd-npu/artifacts/qwen3-32b-tp16 --devices npu:0,npu:1
```

`-tp 8`(1장)로도 시도 가능하나 32B는 1장 HBM에 안 들어갈 가능성 높음 → tp16 우선.

### 확인 포인트 / 분기

| 단계 | 성공 | 실패 시그니처 → 조치 |
|---|---|---|
| build | `artifact.json`+`binary_bundle.zip` 생성, `parallel_config.tensor_parallel_size=16` | host RAM OOM → `--num-compile-workers 1 --num-pipeline-builder-workers 1` |
| build | 〃 | 컴파일 에러(tp16 버킷 미지원 등) → `--max-model-len` 축소, `-pb`/`-db` 수동 지정 |
| serve | `Uvicorn running` | `Required PEs: 16, Actual: N` → `--devices`를 npu:0,npu:1로 |
| serve | 〃 | HBM OOM → 경로 B(FP8)로 재빌드, `--max-model-len` 축소. 그래도 안 되면 **2장으론 불가** |
| 추론 | 5절 curl 정상 응답 | 응답 깨짐 → tp 변경으로 정확도 손상 가능, 다른 tp/버킷 재시도 |

### 주의

- furiosa가 prebuilt를 tp=32로 낸 데엔 이유(컴파일 버킷 제약·성능)가 있을 수 있음 → tp16 빌드/서빙 성공은 보장 안 됨. **해봐야 앎.**
- `-tp 16`을 SDK가 거부하면 `-tp 8 -pp 2`로 분해(8×2 = 16 PE = 2장) 후 재시도.
- 직접 빌드는 bf16/자가 FP8 → prebuilt FP8보다 성능 낮을 수 있음.
- 32B bf16 빌드는 host RAM을 크게 씀. RAM 부족 시 경로 B(FP8) 또는 swap 확보.

---

## 배포 (다른 머신으로)

```bash
tar czf qwen2.5-1.5b.tar.gz -C ~/RNGD-proj/Model_Benchmark/rngd-npu/artifacts qwen2.5-1.5b
# 대상 호스트에서:
tar xzf qwen2.5-1.5b.tar.gz
furiosa-llm serve ./qwen2.5-1.5b --devices npu:0
```

## 제약 / 트러블슈팅

| 증상 / 한계 | 조치 |
|---|---|
| `model_type` 미지원 | 지원 아키텍처 외는 빌드 불가 (SDK 2026.2.0) |
| FP8 외 양자화 | fine-grained FP8 dynamic만 지원 |
| gated 모델 다운로드 실패 | `hf auth login --token $HF_TOKEN` + HF 라이선스 동의 |
| build host OOM | `--num-compile-workers` / `--num-pipeline-builder-workers` 축소 |
| serve `Required PEs: N` | 빌드 tp ≠ 가용 PE → 작은 tp 재빌드 또는 `--devices` 조정 |
| serve HBM OOM | `--max-model-len` 축소, FP8 재빌드 |
| 커스텀 코드 모델 | `--trust-remote-code` |

## 자가 검증 체크리스트

```
[ ] 0  source ~/furiosa/bin/activate
[ ] 1  모델 다운로드 → *.safetensors 확인
[ ] 2  (선택) FP8 양자화 → save_path에 *.safetensors+config.json
[ ] 3  furiosa-llm build → artifact.json+binary_bundle.zip, parallel_config 값 확인
[ ] 3  빌드 중 furiosa-smi → NPU 점유 없음(host 컴파일) 확인
[ ] 4  furiosa-llm serve → "Uvicorn running" 확인
[ ] 5  curl /v1/chat/completions → 정상 응답 확인
[ ] 6  models.yaml 등록 → orchestrator.py 측정 확인
[ ] 7  (선택) 32B tp16 재빌드 → build/serve 성공 여부로 2장 가능성 판정
```
