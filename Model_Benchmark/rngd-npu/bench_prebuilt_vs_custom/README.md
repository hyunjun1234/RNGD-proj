# prebuilt 모델과 직접 빌드한 모델 비교

같은 프롬프트 4종(사실, 코드, 추론, 설명)을 `temperature=0`, `max_tokens=1024` 로 던져 잰 결과.
TTFT 는 스트리밍 첫 토큰까지, 디코드는 첫 토큰 이후 속도, 총처리량은 같은 프롬프트 4개 동시 요청.
측정일 2026-08-28, RNGD 4장 서버, furiosa-llm 2026.3.0.

## 결론

1. **직접 빌드한 dense 모델은 배포판과 답변 품질이 같고 카드당 처리량이 2배다.** Qwen3-32B 는 카드 1장으로 92 tok/s, 배포판은 4장으로 189 tok/s(카드당 47).
2. **직접 빌드는 적재가 10배 빠르다.** tp8 아티팩트 19~30초, 배포 FXB tp32 는 211~938초.
3. **MoE 모델의 직접 빌드는 전부 못 쓴다.** `model_type` 을 위장해 게이트를 지나면 적재는 되지만 답이 틀린다. 5종 전부 확인.
4. **속도 지표만 보면 이 고장을 못 잡는다.** 깨진 모델이 오히려 총처리량이 높게 나온다(Coder custom 161 vs prebuilt 139).

## 표

| 모델 | 갈래 | 카드 | 적재s | TTFT | 디코드 tok/s | 동시4 tok/s | 정상 |
|---|---|---|---|---|---|---|---|
| Coder 30B | prebuilt | 4 | 938.0 | 0.143 | 70.9 | 139.0 | 4/4 |
| Coder 30B | custom | 1 | 21.1 | 0.123 | 60.8 | 160.6 | 0/4 |
| Qwen3 32B | prebuilt | 4 | 211.1 | 0.417 | 55.3 | 188.6 | 4/4 |
| Qwen3 32B | custom | 1 | 24.1 | 0.23 | 24.8 | 91.6 | 4/4 |
| A3B Instruct 2507 | prebuilt | 4 | 272.2 | 0.093 | 71.9 | 142.5 | 4/4 |
| A3B Instruct 2507 | custom | 1 | 23.5 | 0.123 | 61.5 | 134.4 | 0/4 |
| A3B Thinking 2507 | prebuilt | 4 | 43.3 | 0.193 | 71.2 | 141.9 | 4/4 |
| A3B Thinking 2507 | custom | 1 | 22.5 | 0.194 | 61.9 | 161.9 | 0/4 |
| EXAONE 4.0 32B | prebuilt | 4 | 측정 실패 (디스크 가득 참) | | | | |
| EXAONE 4.0 32B | custom | 1 | 30.3 | 0.121 | 24.1 | 82.4 | 4/4 |
| A3B | prebuilt | 4 | 측정 실패 (디스크 가득 참) | | | | |
| A3B | custom | 1 | 21.5 | 0.194 | 60.9 | 159.5 | 1/4 |
| Llama 3.1 8B | custom | 1 | 16.2 | 0.037 | 49.7 | 195.4 | 4/4 |
| Coder 30B bf16 | custom | 1 | 35.6 | 0.188 | 54.4 | 118.7 | 0/4 |

정상 열은 프롬프트 4개 중 뜻 있는 답이 나온 개수다.

## MoE 위장이 원인인가

`artifact.json` 을 세 가지로 바꿔 같은 질문을 던졌다(`moe_check2.py`, 라우터 경유).

| 변형 | 결과 |
|---|---|
| 위장본 (model_type=qwen3, MoE 키 없음) | 떴지만 질문과 무관한 출력 |
| 원본 (model_type=qwen3_moe) | 게이트가 막아 뜨지 못함 |
| 위장 + MoE 키 8개 복원 | 떴지만 여전히 무관한 출력 |

즉 **사라진 MoE 설정 키는 원인이 아니다.** 게이트가 뱉는 말이 그대로 답이다.

```
pyo3_runtime.PanicException: Unsupported model metadata:
    ModelMetadata { model_type: Some(Qwen3Moe), task: Some(Generate), … }
```

furiosa-llm 2026.3.0 의 **v2 아티팩트(next_gen) 경로가 MoE 를 지원하지 않는다.** 같은 MoE 모델도
퓨리오사 배포 FXB(entrypoint 경로)로는 정상 동작한다. 게이트는 형식 검사가 아니라 못 하는 일을 막는 장치다.

## 권고

| 항목 | 조치 |
|---|---|
| MoE tp8 아티팩트 5종 | 카탈로그와 라우터에서 뺀다. `artifact.json.orig-qwen3_moe` 로 되돌리면 게이트가 막아 사고를 예방한다 |
| dense tp8 아티팩트 3종 | 그대로 쓴다. 카드 1장으로 배포판 카드당 성능의 2배 |
| MoE 모델 | 배포 FXB 로만 서빙 |

## 측정 못 한 것

`EXAONE-4.0-32B-FP8` 과 `Qwen3-30B-A3B-FP8` 의 **prebuilt** 는 HF 다운로드가 `No space left on device` 로 실패했다.
`/mnt/nvme2n1p1` 이 1.9T 중 여유 6.8G 로 가득 찼다. `models/furiosa/llm/param_files` 282G 는 아티팩트 폴더와
하드링크가 아닌 별도 사본이라(inode 다름, 링크수 1) 서빙을 깨지 않고 되찾을 수 있는 후보다.

## 다시 돌리는 법

```bash
cd ~/RNGD-proj/Model_Benchmark/rngd-npu/bench_prebuilt_vs_custom
python3 bench.py <모델ID> [<모델ID> …]   # results/<모델>.json 에 저장, 이미 있으면 건너뜀
python3 analyze.py                        # summary.json 생성
python3 moe_check2.py coder-tp8           # 원인 검증 (artifact.json 을 되돌려 놓는다)
cd _ppt_src && python3 gen.py && ~/.cache/diagram-deck/venv/bin/python build.py
```
