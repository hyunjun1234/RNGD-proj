# RNGD 서버에서 쓸 수 있는 모델

라우터(:8400)에 등록된 채팅 모델 전종을 **같은 입력, 같은 설정**으로 재고 답변까지 저장한 결과.
측정일 2026-08-29, RNGD 4장 서버, furiosa-llm 2026.3.0.

## 조건

```
프롬프트  네 종류(사실 질문, 코드 작성, 계산 추론, 개념 설명)를 모든 모델에 같은 문장으로
샘플링    temperature 0 (greedy)
길이      max_tokens 1024
지연      스트리밍으로 첫 토큰까지(TTFT)와 답이 끝날 때까지를 따로
처리량    단일 요청의 디코드 속도, 그리고 같은 질문 4개 동시 요청의 합계 속도
적재      serve 로그의 Loading LLM 부터 기동 완료까지
```

프롬프트 원문과 모델별 답변 원문은 `모델별-성능정리.pptx` 2부에 발췌 없이 실려 있고,
기계가 읽을 형태는 `results/<모델>.json` 에 있다.

## 표

| 모델 | 카드 | 적재 | TTFT | tok/s | 동시4 tok/s | 첫응답 | 답변 |
|---|---|---|---|---|---|---|---|
| gpt-oss 120B | 4 | 1491s | 4.88 | 2 | 40 | 207.5s | 정상 |
| Solar-Open 100B * | 4 | 278s | 0.31 | 59 | 113 | 3.6s | 정상 |
| K-EXAONE 236B * | 4 | 2306s | 0.45 | 43 | 112 | 23.4s | 정상 |
| Llama 3.3 70B | 4 | 174s | 0.20 | 26 | 66 | 2.7s | 정상 |
| Qwen3 32B * | 4 | 211s | 0.42 | 55 | 189 | 9.0s | 정상 |
| EXAONE 4.0 32B * | 4 | 66s | 0.23 | 33 | 113 | 3.8s | 정상 |
| Qwen3-VL 32B | 4 | 77s | 0.18 | 39 | 38 | 1.9s | 정상 |
| Qwen3-Coder 30B | 4 | 938s | 0.14 | 71 | 139 | 1.4s | 정상 |
| A3B Instruct 2507 | 4 | 272s | 0.09 | 72 | 142 | 1.0s | 정상 |
| A3B Thinking 2507 * | 4 | 43s | 0.19 | 71 | 142 | 14.5s | 정상 |
| A3B 30B | 4 | 못 뜸 | - | - | - | - | 배포 FXB 결함 |
| Llama 3.1 8B | 1 | 10s | 0.04 | 50 | 195 | 2.5s | 정상 |
| Qwen3 8B | 1 | 13s | 0.17 | 66 | 248 | 6.9s | 정상 |
| Qwen3 4B | 1 | 9s | 0.20 | 83 | 297 | 5.7s | 정상 |
| Qwen2.5 0.5B | 1 | 3s | 0.03 | 88 | 308 | 2.9s | 정상 |

별표는 사고(thinking)하는 모델. 첫응답은 가장 짧은 프롬프트가 끝날 때까지.

## 읽는 법

1. **TTFT 는 모델을 안 가린다.** 0.03~0.42초로 전부 비슷하다(gpt-oss-120b 4.9초만 예외).
   체감 차이는 첫 글자가 아니라 **답이 끝날 때까지**에서 난다.
2. **사고하는 모델은 짧은 질문에도 오래 걸린다.** 같은 30B 인데 A3B Instruct 1.0초, A3B Thinking 14.5초다.
   어려운 추론을 맡길 때만 고르고, 짧게 묻고 짧게 받을 일에는 사고 없는 모델을 쓴다.
3. **작은 모델이 동시 처리에서 앞선다.** 카드 한 장짜리 0.5B 가 309 tok/s 로,
   카드 넉 장을 쓰는 30B(139~143)보다 두 배 이상이다. 여럿이 붙는 서비스라면 이 숫자를 본다.
4. **모델을 바꾸면 기다린다.** 카드 넉 장짜리는 43초에서 25분까지 걸리고, 한 장짜리는 3~13초다.
   자주 바꿔 쓸 환경이면 한 장짜리가 유리하다(넷까지 같이 떠 있을 수 있다).
5. **gpt-oss-120b 는 유난히 느리다.** 답변은 정상인데 1024토큰에 341초(3 tok/s), 적재 25분이다.
   동시 4요청에서 40 tok/s 로 열 배 이상 좋아지는 걸 보면 단일 스트림의 스텝당 고정 비용이 크다.

## 못 잰 것

`Qwen3-30B-A3B-FP8` 은 **배포된 FXB 번들 자체가 고장**이라 뜨지 못한다. 캐시는 정상이고(32G,
형제 모델 33G, 미완성 파일 없음) 다운로드 문제가 아니다. 가중치 30.2 GiB 를 다 읽은 뒤 죽는다:

```
pyo3_runtime.PanicException: assertion `left == right` failed:
  element size mismatch for weight "model.embed_tokens.weight":
  safetensor dtype F32 is 4 bytes but EDF element type Bfloat16 is 2 bytes
```

50회 재현했다. 같은 계열의 `Qwen3-30B-A3B-Instruct-2507-FP8` 과 `Thinking-2507-FP8` 은 정상이다.

## 다시 돌리는 법

```bash
cd ~/RNGD-proj/Model_Benchmark/rngd-npu/bench_prebuilt_vs_custom
python3 bench.py <모델ID> …        # results/<모델>.json 에 저장, 이미 있으면 건너뜀
python3 analyze.py                 # summary.json 생성
python3 report.py                  # 표를 화면에 출력
cd _ppt_src && python3 gen_all.py && ~/.cache/diagram-deck/venv/bin/python build_all.py
```

## 부록

`README-부록-prebuilt대custom.md` — 배포판과 직접 빌드한 tp8 아티팩트를 비교한 별도 조사.
MoE 모델을 카탈로그에서 뺀 근거다(`prebuilt-vs-custom.pptx`).
