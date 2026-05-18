# RNGD-proj

Furiosa RNGD NPU 관련 프로젝트 모음.

## 프로젝트

| 폴더 | 내용 |
|---|---|
| `Model_Benchmark/` | RNGD NPU·NVIDIA GPU 모델 벤치마크 자동화 (속도·동시성·SWE-bench·임베딩) |

새 작업은 최상위에 프로젝트 폴더를 추가한다. 아래 글로벌 환경은 폴더 위치와 무관하게 동작한다.

## 글로벌 환경 (저장소 밖, 머신 공용)

이 저장소 코드는 아래 글로벌 리소스에 의존한다. 용량이 크거나(venv·모델) 외부 저장소라 git에 포함하지 않는다. 어느 프로젝트 폴더에서 실행하든 동일하게 접근된다.

| 리소스 | 위치 | 용도 |
|---|---|---|
| furiosa-llm venv | `~/furiosa` | RNGD NPU 실행. 사용 전 `source ~/furiosa/bin/activate` |
| SWE-bench harness | `~/SWE-bench` | SWE-bench 채점 (venv에 editable install) |
| 모델·데이터셋 캐시 | `~/.cache/huggingface` | HF/furiosa-llm가 실행 위치 무관 자동 인식 |

새 머신 셋업 시: furiosa SDK venv 구성 → `~/SWE-bench` 클론·설치 → 필요 모델 `hf download`.
