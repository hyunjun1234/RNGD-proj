# Furiosa RNGD Chat — NPU 모델과 대화 + 실시간 성능 대시보드 + RAG

`furiosa-llm serve`(OpenAI 호환 API) 위에 채팅을 얹어, curl 단발 호출 대신
**대화 누적 + 모델 선택 + 스트리밍**으로 NPU 모델과 대화합니다.

> **furiosa-apps 통합(2026-06-15):** [furiosa-ai/furiosa-apps](https://github.com/furiosa-ai/furiosa-apps) 의
> **chat-playground 실시간 성능 대시보드**와 **rag(kotaemon) 의 RAG** 두 기능을 우리 gradio 채팅에 이식하고,
> furiosa 가 만든 인터페이스(순수 검정 + 로고/`Furiosa RNGD Chat`/`DEMO` 헤더, 빨강·시안·보라 강조)로
> 디자인을 바꿨습니다. 기존 디테일(모델 상태 LED, dp/pp 제어, 대화 이력)은 그대로 둔 채 더했습니다.
> - **실시간 대시보드(우측 컬럼)**: TPS·TTFT·TPOT·E2E·Power/card·Temp·NPU util 을 1.8초마다 갱신.
>   토큰 타이밍은 스트리밍 생성에서, 전력/온도/사용률은 `furiosa-smi` 파싱(`npu_metrics.py`).
> - **RAG(사이드바 "📎 문서 검색" 에서 켜면 사용)**: 업로드/URL/붙여넣기 문서에서 근거를 찾아 컨텍스트로
>   주입하고 출처를 각주로 답니다. 기본은 의존성·NPU 0 인 TF-IDF 검색, furiosa 임베딩/리랭커 서버가 있으면
>   그걸 사용(`rag_store.py`, 아래 RAG 절). furiosa 원본은 React+FastAPI 였지만, 우리 기존 기능을 보존하려고
>   **Gradio 앱은 그대로 두고 디자인·기능만 이식**했습니다.

채팅 클라이언트는 두 가지를 지원합니다.

```
[ furiosa-llm serve  (NPU, OpenAI 호환 API) ]   ← 모델마다 포트 1개·카드 1장
            │  /v1/chat/completions (stream)
            ├───────────────┬───────────────────────────────
            ▼               ▼
[ VS Code의 Continue 확장 ]   [ chat_app.py (Gradio 브라우저 UI) ]
  서버 안에서 바로 채팅          대화 누적·모델 드롭다운·스트리밍
```

- **Continue(추천)**: 서버에 접속한 VS Code(code-server) 사이드바에서 바로 채팅. 브라우저 따로 안 띄움.
- **gradio UI**: 브라우저로 접속하는 ChatGPT식 화면. 외부에서 접속하려면 약간의 설정 필요(아래 원격 접속).
- Docker 불필요. gradio 는 furiosa venv 와 충돌하므로 **별도 venv**(`.venv`)에 둡니다.

---

## 1. 실행

### 1-1. 모델 서버 띄우기 (Continue 는 필수 · gradio 는 선택)

**Continue** 로 쓸 거면 먼저 모델을 NPU 카드에 serve 해야 합니다. **gradio UI** 는 안에서
모델을 고르면 자동으로 serve 되므로(아래 (B)) 미리 띄울 필요가 없습니다. 다만 코더 4종을
미리 띄워두면 그 사이 전환은 즉시 됩니다.

```bash
cd ~/RNGD-proj/Model_Benchmark/rngd-npu/chat

./serve_models.sh                    # 기본: tp8 2종(llama31-8b·qwen3-32b)을 빈 카드에 동시 serve
./serve_models.sh 1                  # 기본 세트에서 가벼운 1개만 (테스트용)
./serve_models.sh coder qwen3-32b    # 고른 tp8 모델만 (빈 카드에 자동 배정)
./serve_models.sh hub-gpt-oss-120b   # tp32 프리빌트 1개 (4장 전부 — 단독 serve)
./serve_models.sh list             # 등록된 모델 키 보기
./serve_models.sh stop             # 전부 종료 (NPU 카드 다 비움)

# 준비 확인: 각 포트 로그에 "Uvicorn running" 뜨면 OK
tail -f serve_logs/8007.log
```

- tp8 모델은 카드 1장·포트 1개, tp32 모델은 카드 4장 전부를 씁니다. 어떤 모델이 어느 카드·포트에 뜨는지는 `serve_models.sh` 의 `CAT` 카탈로그가 정합니다(아래 3번). tp32 모델은 4장을 독점해 단독으로만 뜹니다.
- 로딩은 크기에 비례합니다(llama31-8b 15G 는 수십 초, 30~57G 는 수 분). 프리빌트를 처음 쓰면
  HF 다운로드가 먼저 돌아 훨씬 오래 걸릴 수 있습니다.
- `~/furiosa` venv 가 깨졌을 때는 `FURIOSA_LLM_BIN=<다른 venv>/bin/furiosa-llm` 로 우회할 수 있습니다.

### 1-2. 채팅하기 — (A) Continue  또는  (B) gradio UI

#### (A) VS Code의 Continue 확장 (추천)

서버에 접속한 VS Code(code-server) 안에서 바로 채팅합니다.

1. 확장(`Ctrl+Shift+X`)에서 **Continue** 설치
2. `~/.continue/config.yaml` 에 모델 등록 (아래 2번 참고 — model 값은 **아티팩트 절대경로**)
3. `F1` → **Developer: Reload Window** (설정 반영)
4. `F1` → **Focus Continue Chat** → 아래 드롭다운에서 모델 선택 후 대화

#### (B) gradio 브라우저 UI

**처음 한 번만 — 전용 venv 만들기.** gradio 는 furiosa venv 와 충돌하므로 이 폴더의 `.venv` 에 따로 둡니다
(UI 는 NPU 를 직접 만지지 않고 OpenAI 호환 HTTP 로만 말하므로 venv 가 분리돼도 됩니다).

```bash
cd ~/RNGD-proj/Model_Benchmark/rngd-npu/chat
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

> `./run.sh: Permission denied` 가 나면 실행 비트가 빠진 것입니다(홈 복구본 이슈 — `core.fileMode=false`
> 라 `git status` 로도 안 잡힙니다). `chmod +x run.sh serve_models.sh` 로 고치세요.

서버에서 띄우고, 개인 맥북에서 **alpacon tunnel** 로 접속하는 방식을 권장합니다(아래 원격 접속 참고).

```bash
cd ~/RNGD-proj/Model_Benchmark/rngd-npu/chat
./run.sh start      # 7860에 detached 기동(SSH 끊겨도 유지). 실제 PID를 .gradio.pid 에 기록
./run.sh status     # 상태(PID·포트)
./run.sh stop       # 종료
```

- `./run.sh` 없이 `.venv/bin/python chat_app.py` 로 포그라운드 실행해도 되지만, **원격 SSH 세션 포그라운드로 띄우면 세션이 끊길 때 같이 죽고**, 모델 로딩처럼 오래 걸리는 작업 도중 연결이 끊기면 화면에 에러로 보일 수 있습니다. 서버에서 `./run.sh start` 로 분리 기동해 두고 터널로 붙는 편이 안정적입니다.
- 포트는 한 대만 띄우세요. 이미 떠 있으면 `run.sh` 가 막아 줍니다(포트 충돌 방지).

- **모델을 고르면 그 순간 자동으로 serve 됩니다(on-demand).** 드롭다운에서 모델을 고르면 필요한 카드를 비우고 그 모델을 띄웁니다. tp8 모델은 옆에서 **복제(dp)** 로 처리량을 키우거나 **레이어 분할(pp)** 로 한 요청을 여러 장에 나눠 실행할 수 있고(dp×pp ≤ 4장), tp32 모델은 항상 4장 전부를 단독으로 씁니다(dp·pp 비활성). 카드가 모자라면 가장 오래 안 쓴 모델부터 자동으로 내려 자리를 만듭니다(tp32가 떠 있으면 그걸 내리고, tp8 4개가 차 있으면 LRU 하나를 내림).
- 왼쪽 **모델 상태 패널** LED — 🟢 떠 있음 · 🟡 전환중(올라가는·내려가는 중, **이 dot만 깜빡임**) · 🔴 꺼짐/실패. 모델을 고르면 serve 를 바로 시작하고 화면은 즉시 돌아오며(연결을 오래 잡지 않음), **모델을 전환하는 동안에만** 백그라운드 타이머가 켜져 LED 를 🟡→🟢 로 자동 갱신하고, 전환이 끝나면 타이머가 스스로 꺼집니다. **평상시(유휴)엔 타이머가 꺼져 패널을 다시 그리지 않으므로, 모델 상태 패널 전체가 깜빡이는 일이 없습니다**(전환 중 표시는 해당 모델의 🟡 dot 펄스뿐, "도는 네모(스피너)"도 없음). 수동 "🔄 새로고침"은 예비입니다. 드롭다운·패널에 모델이 tp8(dp·pp 선택 가능)인지 tp32(4장 고정, dp·pp 비활성)인지 표시됩니다. 무거운 모델로 바꾸면 가벼운 것들이 🟢→🟡→🔴로 내려가는 게 보입니다.
- **질문 즉시 표시 + 스트리밍**: 입력한 질문은 보내는 즉시 대화창에 뜨고, 답변은 토큰 단위로 흘러나옵니다(ChatGPT처럼). 생성 중에는 전송 버튼(↑)이 **중지(■)** 로 바뀌고, 누르면 생성을 멈춥니다. 답변 말풍선 아래 **↻** 아이콘으로 다시 생성할 수 있습니다.
- **넓은 화면 꽉 채우기(전체 폭)**: 대화창과 입력바가 가운데 좁은 띠로 모이지 않고 창 전체 폭을 채웁니다. 질문은 오른쪽에 컴팩트한 말풍선으로, 답변·코드블록은 채팅 폭 전체를 써서 넓은 모니터에서도 양옆에 빈 공간이 남지 않습니다. (CSS 3곳: ① 최외곽 래퍼 `main.fillable.app` 의 Gradio 기본 `max-width:1536px`·`margin:auto`(양옆 32px)·`padding:32px` 를 `100% / 0 / 0` 으로 덮어 앱을 창 끝까지 펴고 — 이걸 안 풀면 양옆에 64px(@1600)·32px(@1920) 빈 띠가 남음 —, ② `#chatbot`·`#inputwrap` 를 `max-width:100%`(양옆 24px 거터)로, ③ 봇 답변 `.bot-row` 의 Gradio 기본 width 제한(약 600px)을 풀어 `width:100%`.)
- **사고 과정(추론 모델)**: Qwen3·EXAONE 처럼 추론하는 모델은 ChatGPT 처럼, 답변 위에 연한 회색으로 추론 중엔 **"💭 생각하는 중…"**, 끝나면 **"💭 N초 동안 생각함"** 한 줄만 보입니다. 그 줄을 누르면 전체 추론 과정이 펼쳐지고, 다시 누르면 접힙니다(긴 추론을 답변과 분리해 깔끔하게). 추론을 하지 않는 코더 모델은 이 줄이 없습니다. (구현: `chat_app.py` 의 `_stream_reply`/`_think_block`, 챗봇은 `allow_tags=True` 라야 `<details>` 접이식이 렌더됨.)
- **상태 판정은 프로세스(pgrep) 기준**: 모델이 응답하느라 바빠 HTTP 헬스체크가 잠깐 느려도, serve 프로세스가 살아 있으면 🟢를 유지합니다. 예전처럼 잠깐의 프로브 지연으로 🟢가 🔴로 깜빡 꺼졌다가, 그 틈에 멀쩡한 serve 를 죽이고 다시 띄우는 일이 없습니다(모델 전환·대화 중 안정).
- **대화 사이드바**: 왼쪽 "➕ 새 채팅"으로 새 대화를 시작하고, "대화 기록"에서 이전 대화를 골라 이어서 대화합니다. 대화는 **서버 디스크 `conversations/` 에 자동 저장**되어 새로고침·재시작해도 남습니다. 모델을 바꿔도 현재 대화 히스토리는 유지됩니다.
- **max_tokens**는 모델을 고르면 그 모델의 최대치(컨텍스트 한도)로 값·상한이 자동 설정됩니다(예: 16k=16384, qwen3-32b=40960, tp32=131072). 외울 필요 없이, 필요하면 줄여서 쓰면 됩니다.
- serve 준비 최대 대기 시간은 `CHAT_SERVE_TIMEOUT`(기본 900초)로 조절합니다. 그 외 환경변수는 아래 2번 `CHAT_*` 표 참고.

##### 원격 접속 — 개인 맥북에서 alpacon tunnel 로 (권장)

서버 IP 직접 접속(`http://<서버IP>:7860`)이 방화벽으로 막혀 있으면, **개인 맥북 터미널에서 alpacon 터널**로 7860 을 로컬로 끌어옵니다.

```bash
# 1) 서버에서 (한 번): 분리 기동
cd ~/RNGD-proj/Model_Benchmark/rngd-npu/chat && ./run.sh start

# 2) 개인 맥북 터미널에서: 터널 열기
alpacon tunnel furiosa-npu-e6ec40 -l 7860 -r 7860

# 3) 맥북 브라우저에서
#    http://127.0.0.1:7860
```

- 터널이 살아 있는 동안 맥북의 `127.0.0.1:7860` 이 서버의 7860(gradio)으로 연결됩니다. 모델 변경은 화면을 오래 잡지 않게 바뀌어 터널에서도 끊김 없이 됩니다.
- (대안) VS Code(code-server) 포트 프록시로도 열 수 있습니다: `CHAT_ROOT_PATH=/proxy/7860 CHAT_AUTH="rngd:비번" ./run.sh start` 후, VS Code 하단 **PORTS** 탭 → `7860` → **Preview in Editor**. gradio 공개 링크(`CHAT_SHARE=1`)는 외부 7000 포트가 필요해 막힌 환경에선 실패하니 터널/프록시를 쓰세요.

### 1-3. 종료

```bash
./run.sh stop            # UI 만 종료 — 백엔드 serve 는 살려 둠(카드 계속 점유)
./run.sh stop --all      # UI + 백엔드까지 종료 → NPU 카드 반납
./run.sh status          # UI·백엔드·라우터·카드 점유를 한 번에 확인
```

**`./run.sh stop` 이 백엔드를 안 죽이는 건 의도된 동작입니다.** `chat_app.py` 는 `furiosa-llm serve`
를 `start_new_session=True` 로 분리 기동하므로, UI 를 껐다 켜도 이미 올라간 모델에 그대로 다시
붙습니다(`_discover`). 모델 로딩이 수십 분 걸리기 때문에(262K 컨텍스트 pp2 는 50분을 넘긴 적도
있음) 기본값을 "살려 두기"로 둔 것입니다. **카드를 비우려면 `--all` 을 붙이세요.**

> 뭐가 카드를 잡고 있는지 헷갈리면 `./run.sh status` 를 보세요. UI/백엔드/라우터와 카드별
> 메모리 점유가 한 번에 나옵니다.

**furio 라우터(`:8400`)는 별개 서비스라 `run.sh` 가 건드리지 않습니다.** 팀원들이 쓰고 있을 수
있어서 일부러 남깁니다. 내리려면:

```bash
bash ../coding-agent/serve-router.sh stop
```

> ⚠️ **라우터와 chat UI 를 동시에 켜 두지 마세요.** 둘 다 같은 카드 4장을 스스로 스케줄링하는데,
> `chat_app` 은 자기 `CATALOG` 포트의 백엔드만 점유로 인식하므로 라우터 백엔드(`:8410+`)가 쓰는
> 카드를 못 봅니다 → 같은 카드를 이중 배정할 수 있습니다. `run.sh start`/`status` 가 이 상황을
> 감지하면 경고를 띄웁니다.

> Continue 로 계속 쓸 거면 **모델 서버는 켜두세요** — 끄면 Continue 도 답을 못 받습니다.
> (`./serve_models.sh stop` 은 백엔드만 따로 내릴 때 씁니다.)

---

## 2. 나중에 본인 환경에 맞게 수정할 파일

| 파일 / 위치 | 무엇을 바꾸나 | 언제 |
|---|---|---|
| `serve_models.sh` 의 `CAT` 카탈로그 | 모델 키 ↔ 포트·tp(카드 수)·아티팩트·serve 옵션, 모델 추가/제거 | 모델을 추가·교체하거나 카드 배치를 바꿀 때 |
| `~/.continue/config.yaml` 의 `models:` | **Continue** 드롭다운에 뜨는 모델 목록 | Continue 에 모델 추가·제거할 때 |
| `chat_app.py` 의 `CATALOG` 딕셔너리 | **gradio UI** 모델 목록 (키 ↔ 표시이름·포트·아티팩트·파서·pp) | gradio UI 에 모델을 추가·교체할 때 |
| `serve_models.sh` 의 `CAT` 배열 | 백엔드만 손으로 띄울 때의 같은 목록 | **`CATALOG` 과 키·포트·파서를 반드시 맞출 것** |
| `chat_app.py` 실행 시 환경변수 | 포트·접속 방식·비번·RAG 임베딩 서버 (아래 표) | 접속 방식·RAG 백엔드를 바꿀 때 |
| `npu_metrics.py` | 실시간 대시보드(메트릭 카드·`furiosa-smi` 파싱·furiosa 색상) | 대시보드 지표/디자인을 바꿀 때 |
| `rag_store.py` | RAG 검색(청킹·TF-IDF·임베딩/리랭커 백엔드) | RAG 동작을 바꿀 때 |

**gradio 환경변수(`CHAT_*`)**

| 변수 | 기본 | 용도 |
|---|---|---|
| `CHAT_PORT` | `7860` | UI 포트 |
| `CHAT_HOST` | `0.0.0.0` | 바인드 주소(외부 접속 허용) |
| `CHAT_ROOT_PATH` | (없음) | 하위경로 프록시 뒤에서 띄울 때. 예: `/proxy/7860` |
| `CHAT_SHARE` | `0` | `1` 이면 gradio 공개 링크(`*.gradio.live`) — 외부 공개·7000 포트 필요 |
| `CHAT_AUTH` | (없음) | `"아이디:비번"` 형식의 접속 비밀번호 |
| `CHAT_SERVE_TIMEOUT` | `900` | on-demand serve 준비를 기다리는 최대 시간(초). 큰 모델 로딩이 더 길면 늘립니다 |
| `CHAT_EMBED_URL` | (없음) | RAG 의미 임베딩 서버(OpenAI 호환 `/v1`). 예: `http://127.0.0.1:8021/v1`. 없으면 TF-IDF 로컬 검색 |
| `CHAT_EMBED_MODEL` | (자동) | 임베딩 모델 id. 비우면 그 서버의 첫 모델 사용 |
| `CHAT_RERANK_URL` | (없음) | RAG 리랭커 엔드포인트(furiosa TeiFastReranking `/v1/rerank`). 예: `http://127.0.0.1:8022/v1/rerank` |

### UI 설정 — 모델 / dp·pp / temperature / max_tokens

"모델 / 설정" 아코디언 안의 컨트롤입니다.

- **모델**: 고르면 자동으로 serve 됩니다(위 (B) 참고).
- **복제 dp** (1~4, 기본 1, tp8만): 모델 전체를 카드 수만큼 **복제**합니다.
  - dp 는 **동시 요청**의 throughput 을 키웁니다(예: dp4 면 4개 대화를 4장이 병렬 처리). **한 대화(요청)는 한 복제본=한 카드만** 씁니다 — `PrefixAware` 라우팅이 같은 대화를 같은 엔진으로 보내 prefix 캐시를 재사용하기 때문입니다. 그래서 혼자 대화하면 dp4 라도 답변마다 **NPU 1장만** 계산하고, **그 카드의 KV 캐시 사용률(RAM 수치)만** 차오릅니다(나머지 3장은 대기 — 정상이며 버그 아님). serve 로그의 `[Engine 0] ... Running: 1 reqs, RNGD KV cache usage: x%` 가 한 엔진에서만 오르는 것으로 확인됩니다.
- **레이어 분할 pp** (1·2·3·4, tp8만 · 기본값은 모델별 `pp_min`, FXB 프리빌트는 선택 불가): 한 모델의 레이어를 **여러 장에 나눠** 한 요청을 파이프라인으로 처리합니다(예: pp2 면 모델의 앞 절반·뒤 절반을 두 장이 맡음). 복제(dp)가 같은 모델을 통째로 여러 벌 올리는 것과 달리, pp 는 **한 벌을 쪼개 담습니다**. serve 로그에 `Resolve 1 pipeline for 1 DP groups (DP=1, PP=2)` 와 `PP device#0 ... Model weights=6.7 GiB` / `PP device#1 ... 7.5 GiB` 처럼 가중치가 장마다 나뉘어 찍히는 것으로 확인됩니다(2026-06-09 coder7 실측).
  - ⚠️ **dp × pp ≤ 4장**(카드가 4장이라). 그래서 pp 를 키우면 dp 선택지가 자동으로 줄어듭니다(pp2 → dp 는 1~2, pp4 → dp 는 1). 화면이 알아서 막아 주니 잘못된 조합은 못 고릅니다.
  - tp8 아티팩트는 `pipeline_parallel_size=1` 로 빌드돼 있어도 **serve 할 때 `-pp` 로 레이어를 다시 나눠** 띄울 수 있습니다(빌드 단계의 pp 와는 다른 동작 — 빌드 pp 는 2026.2.0 에서 안 되지만 serve pp 는 됩니다, `info/README_build.md` 3절). 내부적으로 `furiosa-llm serve` 의 `-pp`/`-dp`/`-tp` 옵션을 그대로 씁니다(`furiosa-llm serve --help`).
  - ⚠️ **pp 도 단일 대화를 빠르게 하지는 못합니다** (2026-06-10 실측: coder7 단일 요청 1장 50.3 tok/s vs pp2 48.3 tok/s — 한 토큰이 스테이지를 차례로 통과해야 해서 오히려 카드간 전송만큼 살짝 느림). pp 의 가치는 속도가 아니라 **자리**입니다: 1장에 안 들어가는 모델을 나눠 담고, KV 캐시 풀이 장 수만큼 커져(pp2 면 38.8+38.0 GiB) 긴 대화·동시 사용자를 더 받습니다. **한 대화 자체를 빠르게** 받고 싶으면 **tp32 모델**(예: `Qwen3-32B-FP8 tp32`)뿐입니다 — tp 는 한 연산을 4장이 동시에 쪼개 계산하므로(텐서 분할) 단일 요청도 빨라집니다.
- **tp32 모델**(EXAONE·Llama-70B·Qwen3-32B-tp32): 4장을 전부 써서 단독으로 뜨므로 **dp·pp 를 고를 수 없습니다**(두 컨트롤이 비활성·1 고정). 카드를 더/덜 쓸 여지가 없기 때문입니다.

#### dp·pp 가 진짜 적용됐는지 확인하는 법

UI 에서 고른 값이 실제 serve 에 반영됐는지는 다음 네 곳에서 확인할 수 있습니다(위에서 아래로 갈수록 깊은 증거 — 전부 2026-06-09~10 coder7 실측으로 확인된 방법):

1. **왼쪽 "모델 상태" 패널**: 떠 있는 tp8 모델 옆에 `npu:1,npu:2 · dp1·pp2` 처럼 **사용 카드와 dp·pp 가 같이 표시**됩니다. 이 값은 UI 가 기억하는 선택값이 아니라 **실행 중인 serve 프로세스의 명령줄(`--devices`/`-pp`/`-dp`)을 매번 읽어서**(`_discover`) 그리는 것이라, 표시되면 실제로 그렇게 떠 있는 것입니다.
2. **serve 로그** (`serve_logs/<포트>.log`) — 가장 결정적입니다. 기동 직후 이런 줄이 찍힙니다:
   - `Resolve 1 pipeline for 2 DP groups (DP=2, PP=1)` ← **DP·PP 숫자를 런타임이 직접 선언**
   - pp 면 `PP device#0 ... Model weights=6.7 GiB` / `PP device#1 ... 7.5 GiB` 처럼 **가중치가 장마다 쪼개져** 찍히고, dp 면 `PP device#0 ... 14.2 GiB` **한 줄(통째)** 만 찍힙니다(복제라서).
   - dp 면 `DP entry DpId(0) → npu1`, `DpId(1) → npu2` 처럼 복제본별 카드 배정도 나옵니다.
3. **프로세스 명령줄**: `pgrep -af "furiosa-llm serve"` 로 `-pp 2`/`-dp 2` 플래그와 `--devices` 를 직접 봅니다.
4. **대화 중 카드 사용률** (`furiosa-smi status` 를 답변 생성 중에): 동작 차이가 그대로 보입니다.
   - **dp2 + 질문 1개** → npu1 만 76~80%, npu2 는 0% (한 대화는 복제본 1개만 씀 — 정상)
   - **pp2 + 질문 1개** → npu1 26~31% **와** npu2 31~42% **둘 다** 움직임 (레이어 앞/뒤를 두 장이 나눠 처리)

> 참고: `furiosa-smi` 의 **메모리 수치로는 dp/pp 를 구별할 수 없습니다** — 어느 쪽이든 남는 HBM 을 KV 캐시로 다 잡아 카드당 ~45GiB 로 보입니다. 구별은 위 1·2·4번으로 하세요.
- **temperature** (0~2, 기본 0.7): 생성의 무작위성입니다. `0`이면 결정적이라 같은 입력엔 거의 같은 답이 나오고(코딩·정확성엔 0~0.3 권장), 높을수록 다양·창의적이지만 산만해질 수 있습니다.
- **max_tokens**: 한 응답에서 **생성할 출력 토큰 수의 상한**입니다. 모델을 고르면 **값·상한이 그 모델의 최대치(컨텍스트 한도)로 자동 설정**됩니다(모델 바꾸면 따라 바뀜). 외울 필요 없이, 응답을 짧게 받고 싶으면 줄이면 됩니다.

> **max_tokens 와 컨텍스트(버킷)의 관계**: 진짜 하드웨어 한도는 **프롬프트 토큰 + 생성 토큰의 합 ≤ 그 모델 아티팩트의 최대 컨텍스트**(가장 큰 attention/decode 버킷 = `max_model_len`)입니다. `max_tokens` 는 그 예산의 생성 몫일 뿐입니다. 모델별 한도: `Qwen2.5-Coder` 32768, `Qwen3-32B-FP8-tp8` 40960, `-16k` 16384, `EXAONE-4.0-32B`·`Llama-3.3-70B`(tp32) 131072. 예컨대 16k 모델은 프롬프트+출력이 16384를 넘으면 생성 도중 KV가 버킷을 넘어 실패합니다.

### 실시간 성능 대시보드 (우측 컬럼)

화면 오른쪽에 추론하는 동안 갱신되는 성능 카드가 뜹니다(furiosa-apps chat-playground 이식, `npu_metrics.py`).

| 카드 | 뜻 | 출처 |
|---|---|---|
| **TPS** | 초당 생성 토큰(라인+숫자, 점선은 최고치) | 스트리밍 토큰을 1.8초 윈도로 환산 |
| **TPOT** | 토큰당 생성 지연(ms) | (E2E − TTFT) / 생성토큰 |
| **E2E** | 한 응답 전체 시간(s) | 요청 시작~끝 |
| **TTFT** | 첫 토큰까지 지연(ms) | 요청 시작~첫 토큰 |
| **Power / card** | 작업 카드 전력(W, 라인) | `furiosa-smi info` |
| **Temp / NPU util** | 작업 카드 온도(°C)·코어 사용률(%) | `furiosa-smi info`·`status` |

- 토큰 수는 furiosa-llm serve 가 주는 정확한 `usage`(stream_options include_usage)로 확정합니다. 전력은 유휴 ~38W → 추론 ~120W 로 실제 변합니다.
- 1.8초마다 갱신하되 **값이 그대로면 다시 안 그려** 유휴 시 깜빡임이 없습니다. `furiosa_smi_py` 의존성 없이 CLI 파싱이라 chat venv 그대로 동작합니다.

### RAG — 올린 문서에서 근거 찾아 답하기 (선택)

사이드바 **"📎 문서 검색 (RAG)"** 아코디언에서 켭니다(furiosa-apps rag/kotaemon 패턴, `rag_store.py`).

1. **RAG 사용** 체크 → 2. 문서 추가(파일 업로드 `.txt`·`.md`·코드·`.pdf`, 또는 URL, 또는 텍스트 붙여넣기) → 3. 그냥 대화.
- 질문할 때마다 관련 청크 top-k(슬라이더)를 찾아 **질문 직전에 컨텍스트로 주입**하고, 모델이 `[번호]`로 인용하게 합니다. 답변 끝에 **🔎 RAG 참조: 문서명** 각주가 붙습니다.
- **검색 백엔드 2가지(자동 선택)**:
  - 기본 **TF-IDF(로컬)** — numpy 만으로, NPU·다운로드·추가 카드 없이 업로드 문서에서 검색. 항상 동작.
  - **임베딩 서버** — `CHAT_EMBED_URL` 을 furiosa 임베딩 serve(예: `Qwen3-Embedding-8B`, OpenAI 호환 `/v1`)로 지정하면 의미 임베딩으로 검색. `CHAT_RERANK_URL`(furiosa 리랭커 `/v1/rerank`)이 있으면 상위 후보를 리랭킹. (임베딩/리랭커 모델을 카드에 serve 해 두어야 함 — 위 환경변수 표.)
- RAG 를 꺼 두거나 문서가 없으면 일반 채팅과 똑같이 동작합니다(무해). 사이드바 정보 줄에 `N개 문서·M개 청크·검색 백엔드`가 표시됩니다.

> **권장: 기본 TF-IDF 를 그대로 쓰세요.** 임베딩(1장)+리랭커(1장)를 띄우면 **카드 4장 중 2장이 RAG 전용으로 묶여 tp32 모델(EXAONE·Llama-70B·Qwen3-32B-tp32, 4장 필요)이 아예 안 뜨고** tp8 dp/pp 여유도 반토막 납니다. 게다가 여기 문서는 기술 용어·코드·로그가 많아 **키워드 일치(TF-IDF)가 의미 임베딩만큼 잘 찾는** 경우가 많습니다. 의미 임베딩은 ① RAG 가 주력 용도가 되고 ② 질의가 자연어 산문·패러프레이즈 위주이며 ③ 그동안 tp32 를 안 쓰기로 했을 때만 이득입니다. 그때도 **리랭커는 빼고 임베딩만(1장)** 먼저, 또는 RAG 세션에만 띄웠다 내리는 on-demand 가 낫습니다.

> furiosa 원본 RAG([kotaemon](https://github.com/furiosa-ai/kotaemon))은 하이브리드 검색·문서 하이라이트·마인드맵까지 갖춘 별도 대형 플랫폼입니다. 여기서는 그 핵심(임베딩·리랭커·검색→컨텍스트 주입)을 우리 채팅에 가볍게 이식해, 카드·의존성 없이도 바로 쓸 수 있게 했습니다.

### 대화 저장 위치

대화는 **서버 디스크 `chat/conversations/<id>.json` 에 자동 저장**됩니다(맥북이 아니라 chat_app.py 가 도는 서버). 메시지를 보낼 때마다 갱신되고, 새로고침하거나 chat_app.py 를 재시작해도 사이드바 "대화 기록"에 그대로 남아 이어서 대화할 수 있습니다.

### 새 모델을 추가하는 법 (예시)

빈 카드(예: `npu:3`)·빈 포트(예: `8004`)에 올린다고 가정합니다.

**① serve 에 올리기** — `serve_models.sh` 의 `CAT` 에 한 줄 추가 (형식: `포트|카드수|아티팩트|추가인자`):
```bash
declare -A CAT=(
  ...
  [<키>]="8030|1|$ART/<새-아티팩트-폴더>|--enable-auto-tool-choice --tool-call-parser hermes"
)
```
또는 임시로 직접:
```bash
nohup furiosa-llm serve /mnt/nvme2n1p1/models/artifacts/<새-아티팩트-폴더> \
  --devices npu:3 --host 0.0.0.0 --port 8030 --enable-prefix-caching \
  > serve_logs/8030.log 2>&1 &
```

**② 클라이언트에 등록하기**

- Continue → `~/.continue/config.yaml` 의 `models:` 에 추가 후 Reload Window:
  ```yaml
  - name: <보여줄 이름>
    provider: openai
    model: /mnt/nvme2n1p1/models/artifacts/<새-아티팩트-폴더>
    apiBase: http://localhost:8030/v1
    apiKey: dummy
    roles: [chat, edit, apply]
  ```
- gradio → `chat_app.py` 의 `CATALOG` 딕셔너리에 한 줄 (필드 설명은 그 딕셔너리 위 주석 참고):
  `"<키>": dict(name="<보여줄 이름>", port=8030, kind="tp8", src="art", sub="<아티팩트 폴더>", ctx=32768, pp_min=1, tool="hermes", reasoning=None),`
  프리빌트를 등록할 땐 `src="hub", sub="furiosa-ai/<저장소>"` 로 두면 HF 캐시에서 해석됩니다.

> ⚠️ **`model` 값은 아티팩트 절대경로 그대로** 써야 합니다. 서버가 `/v1/models` 로 돌려주는 id 가 그 경로라서, 다른 이름을 쓰면 거부됩니다. 헷갈리면 `curl -s localhost:8004/v1/models` 로 확인하세요.

---

## 3. 등록된 모델 (23종 — 2026-08-04 갱신)

`serve_models.sh` 의 `CAT` 카탈로그와 `chat_app.py` 의 `CATALOG` 는 **키·포트·파서가 같아야 합니다.**
카드가 4장이라 동시에 뜨는 것은 tp8 을 합쳐 4장까지, 또는 tp32 1개(4장 독점)입니다.

> ⚠️ 옛 카탈로그(9종)는 `rngd-npu/artifacts/` 를 가리켰는데 그 폴더엔 `.gitkeep` 만 남아
> **12개 항목이 전부 死경로**였습니다. 지금은 실재하는 두 갈래만 등록합니다.

### 3-1. 로컬 tp8 아티팩트 — `/mnt/nvme2n1p1/models/artifacts` (8종)

2026-07-29 에 `legacy_moe_build/` 로 직접 빌드한 legacy(v2) 아티팩트입니다.
**tp8 로 빌드해 뒀기 때문에 serve 때 `-pp` 로 층을 쪼갤 수 있고, UI 에서 pp 를 고를 수 있는
유일한 갈래입니다** (프리빌트는 대부분 tp32 로 박혀 있어 4장 고정).

값은 전부 `artifact.json` 을 직접 파싱한 실측치입니다.

| 키 | 포트 | 총 컨텍스트 | 프롬프트 최대 | 기본 pp | tool 파서 | reasoning 파서 |
|---|--:|--:|--:|:--:|---|---|
| `coder` (Qwen3-Coder-30B-A3B-Inst-FP8) | 8000 | 262,144 | **65,408** | 2 | — (아래 ⚠️) | — |
| `coder-bf16` (Qwen3-Coder-30B-A3B-Inst bf16) | 8001 | 262,144 | **65,408** | 2 | — (아래 ⚠️) | — |
| `a3b-inst-2507` (Qwen3-30B-A3B-Instruct-2507-FP8) | 8002 | 262,144 | **65,408** | 2 | `hermes` | — |
| `a3b-think-2507` (Qwen3-30B-A3B-Thinking-2507-FP8) | 8003 | 262,144 | **65,408** | 2 | `hermes` | `qwen3` |
| ~~`a3b`~~ (Qwen3-30B-A3B-FP8) | ~~8004~~ | — | — | — | — | ❌ **비활성** — 아래 참고 |
| `qwen3-32b` (Qwen3-32B-FP8) | 8005 | 40,960 | 40,832 | 1 | `hermes` | `qwen3` |
| `exaone4` (EXAONE-4.0-32B-FP8) | 8006 | 131,072 | 130,944 | 2 | `hermes` | `exaone4` |
| `llama31-8b` (Llama-3.1-8B-Instruct) | 8007 | 131,072 | 130,944 | 1 | `llama3_json` | — |

- **pp 는 1·2·3·4 를 고를 수 있습니다.** `pp3` 은 카드 3장만 쓰고 한 장이 남습니다.
  `dp` 는 1 로 고정됩니다(dp×pp ≤ 4). **2026-08-04 에 로드~생성까지 실측했습니다.**

  | 모델 | pp | 장당 가중치 | `max_kv_len` | 생성 |
  |---|:--:|---|--:|:--:|
  | `llama31-8b` | 3 | 5.2 / 4.1 / 5.9 GiB | 870,470 | ✅ |
  | `coder-bf16` | 2 | 27.4 / 29.7 GiB | 299,355 | ✅ |
  | `coder-bf16` | 3 | 18.1 / 18.7 / 20.4 GiB | **753,291** | ✅ |

  `coder-bf16` 은 **pp3 이 pp2 보다 KV 풀이 2.5배**입니다(카드가 하나 더 붙어 여유 메모리가
  KV 로 들어가기 때문). 긴 대화나 동시 사용자가 많으면 pp3 이 더 낫고, 카드를 아껴야 하면
  pp2 를 쓰면 됩니다. 기본값은 pp2 이고 드롭다운에서 바꿀 수 있습니다.
- **기본 pp** 는 "최대 컨텍스트로 쓸 때 카드 1장(47.5 GiB)에 들어가는가"로 정했습니다. 짧게만
  쓰면 pp 를 낮춰도 뜨지만, UI 는 안전하게 이 값 이상만 고르게 합니다.
  `coder-bf16`(bf16 56.9G)은 한동안 pp4 로 강제했으나, **2026-08-04 에 pp2 로 실기동해 정상 확인**
  했습니다 — 장당 가중치 27.4 / 29.7 GiB, KV 는 `max_kv_len` 299,355 토큰 확보, 코드 생성 정상.
  그래서 기본을 **pp2** 로 내렸습니다. 카드를 2장만 쓰므로 다른 모델과 같이 띄울 수 있습니다
  (실측: `coder-bf16`(npu:0,1) + `llama31-8b`(npu:2) 동시 서빙 OK). 최대 컨텍스트로 길게 쓸 때는
  KV 가 장당 12 GiB라 빠듯해질 수 있으니 UI 에서 **pp4** 를 고르면 됩니다(드롭다운에 둘 다 나옵니다).
- ⚠️ **프롬프트 최대**: `kv_heads=4` 인 30B-A3B 계열은 append(chunked prefill) 버킷이 65536 에서
  막혀 총 컨텍스트가 26만이어도 **한 번에 넣을 수 있는 프롬프트는 65,408 토큰**입니다.
  서버는 초과 요청을 200 OK 로 받은 뒤 스케줄러에서 실패시키므로 클라이언트가 잘라야 합니다.
  (근거: `legacy_moe_build/README.md` §0-A·§0.8)

#### ⚠️ qwen3_moe 는 serve 게이트에 막힙니다 — model_type 위장 필요

MoE 로 빌드한 5종(`coder` · `coder-bf16` · `a3b` · `a3b-inst-2507` · `a3b-think-2507`)은
**그대로는 안 뜹니다.** 양자화와 무관합니다 — fp8 도 bf16 도 똑같이 막힙니다.
2026.3.0 런타임도 `(model_type × 양자화)` 화이트리스트를 그대로 들고 있어서 부팅 때 죽습니다
(2026-08-04 실측 — `legacy_moe_build/README.md` §6 의 "미실측" 항목 해소):

```
pyo3_runtime.PanicException: Unsupported model metadata: ModelMetadata {
    model_type: Some(Qwen3Moe), ...
    quantization_config: Some(QuantizationConfig { weight: FP8, ... }) }   # bf16 도 동일
```

연산은 빌드 때 이미 EDF 바이너리로 컴파일돼 있고 **게이트만 메타데이터 문자열을 봅니다.**
그래서 `artifact.json` 의 `model_type` 만 `qwen3` 으로 바꾸면 통과하고, 런타임은 컴파일된
MoE 그래프를 그대로 실행합니다(2026-06-10 에 62.7 tok/s 로 검증된 경로).

```bash
cd ~/RNGD-proj/Model_Benchmark/rngd-npu/chat
bash masquerade_moe.sh           # 대상만 보여주기(변경 없음)
bash masquerade_moe.sh --apply   # 실제 적용
python3 validate_catalog.py      # 지적이 사라지면 완료
```

`masquerade_moe.sh` 는 아티팩트를 직접 훑어 `model_type=qwen3_moe` 인 것만 골라내므로
모델 목록을 손으로 관리할 필요가 없고, 이미 위장된 것은 대상에서 빠져 **여러 번 돌려도 안전**합니다.

- 원본은 `artifact.json.orig-qwen3_moe` 로 자동 백업됩니다(되돌리려면 이 파일을 되돌려 놓으면 됨).
- **KV 차원(`num_hidden_layers`·`num_key_value_heads`·`head_dim`)은 건드리면 안 됩니다** —
  런타임이 이 값으로 캐시 shape 를 잡으므로 컴파일된 그래프와 어긋나면 깨집니다.
- `validate_catalog.py` 가 이 조합을 자동으로 잡아 위 명령까지 찍어 줍니다.

**적용 결과 (2026-08-04 실측)**

| 아티팩트 | serve | 생성 | 비고 |
|---|:--:|:--:|---|
| `coder-tp8` | ✅ | ✅ | pp2, 파이썬 코드 정상 생성 |
| `a3b-inst-2507-tp8` | ✅ | ✅ | pp2, "Paris" 정답 |
| `a3b-think-2507-tp8` | ✅ | ✅ | pp2, "Paris" 정답 |
| `a3b-tp8` | ✅ | ❌ | **0 토큰** — 카탈로그에서 비활성 |
| `coder-bf16-tp8` | — | — | 뒤늦게 대상으로 확인(아래) |

`a3b-tp8` 은 게이트를 통과해 `Uvicorn running` 까지 가고 가중치도 29.0 GiB 정상 로드되는데
**아무것도 생성하지 않습니다**(`/v1/completions` 로 채팅 템플릿을 우회해도 빈 문자열, 0 토큰).
temperature 0 에서는 질문과 무관한 반복 텍스트가 나옵니다. **위장 방식의 문제는 아닙니다** —
같은 처리를 한 나머지 3종은 정상이고, 빌드 로그도 `BUILD SUCCEEDED`(ERROR 0건)이며
`hf_configs` 도 정상 3종과 `max_position_embeddings`(40960) 말고는 전부 같습니다.
→ **이 빌드만의 문제로 보이며 재빌드가 필요합니다.** 그때까지 카탈로그에서 비활성입니다.

> 📌 **정정(2026-08-04 후속)**: 처음엔 "fp8 만 막히고 bf16 은 통과"로 봤으나, `coder-bf16` 을
> 실제로 띄워 보니 **bf16 도 같은 `PanicException` 으로 막혔습니다.** 게이트는 양자화가 아니라
> `model_type` 만 봅니다. `masquerade_moe.sh` 와 `validate_catalog.py` 를 그에 맞게 고쳤고,
> `coder-bf16-tp8` 도 위장 대상입니다.

### 3-2. furiosa-ai 프리빌트 — `HF_HUB_CACHE`(`/mnt/nvme2n1p1/models/hf/hub`) (15종)

`models--furiosa-ai--*` 만 서빙 가능합니다(그 밖의 `models--Qwen--*` 등은 원본 가중치라 빌드가 필요).
tp32 는 4장을 독점하므로 한 번에 하나만 뜹니다. 파서는 라우터 `REGISTRY` 와 같은 값입니다.

| 키 | 포트 | tp(카드) | 컨텍스트 | tool 파서 | reasoning 파서 |
|---|--:|---|--:|---|---|
| `hub-gpt-oss-120b` | 8010 | tp32(4장) | 131,072 | `openai` | — |
| `hub-solar-100b` | 8011 | tp32(4장) | 131,072 | `solar_open` | `solar_open` |
| `hub-llama-70b` | 8012 | tp32(4장) | 131,072 | `llama3_json` | — |
| `hub-qwen3-32b` | 8013 | tp32(4장) | 40,960 | `hermes` | `qwen3` |
| `hub-exaone4` | 8014 | tp32(4장) | 131,072 | `hermes` | `exaone4` |
| `hub-kexaone-236b` | 8015 | tp32(4장) | 262,144 | `hermes` | `deepseek_v3` |
| `hub-a3b-inst-2507` | 8016 | tp32(4장) | 262,144 | `hermes` | — |
| `hub-a3b-think-2507` | 8017 | tp32(4장) | 262,144 | `hermes` | `qwen3` |
| `hub-a3b` | 8018 | tp32(4장) | 40,960 | `hermes` | `qwen3` |
| `hub-coder` | 8019 | tp32(4장) | 262,144 | — (아래 ⚠️) | — |
| `hub-qwen3-vl-32b` | 8020 | tp32(4장) | 262,144 | `hermes` | — |
| `hub-llama31-8b` | 8021 | tp8(1장) | 131,072 | `llama3_json` | — |
| `hub-qwen3-8b` | 8022 | tp8(1장, FXB) | 40,960 | `hermes` | `qwen3` |
| `hub-qwen3-4b` | 8023 | tp8(1장, FXB) | 40,960 | `hermes` | `qwen3` |
| `hub-qwen2.5-0.5b` | 8024 | tp4(카드 일부) | 32,768 | `hermes` | — |

- **FXB 번들은 `-pp` 를 못 씁니다** — 런타임이 `FXB-based artifacts currently does not support
  pipeline parallelism` 으로 거절합니다. 그래서 `hub-qwen3-8b`·`hub-qwen3-4b` 는 카탈로그에
  `no_pp=True` 로 두어 UI 에서 pp 선택을 막습니다. dp(복제)는 됩니다.
- `hub-qwen2.5-0.5b` 는 tp4 라 카드 하나를 통째로 주면 안 되고 앞 4 PE 만 줍니다(`npu:X:0-3`).
- 임베딩/리랭커(`Qwen3-Embedding-8B`·`Qwen3-Reranker-8B`)는 채팅 모델이 아니라 뺐습니다 —
  라우터(:8400)의 `/v1/embeddings`·`/v1/rerank` 로 쓰세요.
- 프리빌트 저장소가 캐시에 없으면 serve 가 알아서 내려받습니다(수십~백 GB). 그래서
  `CHAT_SERVE_TIMEOUT` 기본값을 2400 초로 뒀습니다.

### 3-3. ⚠️ Qwen3-Coder 계열의 tool 파서 (serve 가능 여부와는 별개)

> 위 3-1 의 게이트 문제는 **모델이 뜨느냐**의 이야기고, 여기는 **뜬 모델이 tool call 을
> 파싱할 수 있느냐**의 이야기입니다. 둘은 별개입니다.

`furiosa-llm` 2026.3.0 이 받는 tool 파서는 `furiosa_llm/constants.py` 의 `TOOL_PARSER_NAMES`
에 **하드코딩**된 `{hermes, llama3_json, llama4_json, openai, solar_open}` 뿐입니다(2026-08-04 실측).
Qwen3-Coder 전용 `qwen3_coder` 는 이 목록에 없어 넘기면 serve 가 `invalid choice` 로 즉시 죽습니다.
그래서 `coder`·`coder-bf16`·`hub-coder` 는 **파서 없이(채팅 전용)** 등록했습니다.

`coding-agent/furiosa_patches/` 에 로컬 `qwen3_coder` 파서가 들어 있지만, 그 `install.sh` 는
`tool_parsers/__init__.py` 에 import 만 추가합니다. 2026.3.0 에서는 그것만으로는 부족하고
`constants.py` 의 목록까지 넣어야 CLI 가 받습니다. 패치를 되살렸다면 두 카탈로그의 해당 3종을
`qwen3_coder` 로 바꾸면 됩니다.

### 3-4. 카탈로그 정합성 확인

두 파일이 어긋나면 UI 는 A 모델을 고르고 serve 는 B 를 띄우는 사고가 납니다. 바꾼 뒤에는
아티팩트 실재·`ctx` 실측·파서 유효성·포트 중복을 한 번에 확인하세요.

```bash
python3 validate_catalog.py     # ← 이것만 돌리면 됩니다
./serve_models.sh list          # 등록된 키/포트/카드 눈으로 확인
```

`validate_catalog.py` 가 보는 것:

- 표시이름·포트 중복 (겹치면 드롭다운과 상태패널이 조용히 어긋납니다)
- 로컬 아티팩트 실재 + `ctx`·`pe` 가 `artifact.json` 실측치와 일치하는지
- 프리빌트가 HF 캐시에 있는지, `furiosa-ai/*` 인지
- FXB 번들인지 ↔ `no_pp` 가 맞는지 (FXB 에 `-pp` 를 주면 `PanicException`)
- `tool`·`reasoning` 파서를 **지금 설치된 furiosa-llm CLI 가 실제로 받는지**
- `serve_models.sh` 의 `CAT` 과 포트·파서·카드수·`-pp` 가 일치하는지

gradio 의존성 없이 AST 로만 읽으므로 `chat/.venv` 가 없어도 돕니다.

---

## 참고 — 동작 원리 / 자원

- **대화 누적**: furiosa-llm serve 는 stateless 라, 맥락은 클라이언트가 이전 대화를 매번 함께 보내서 만듭니다. (Continue·gradio 둘 다 자동으로 처리)
- **메모리(중요 — 헷갈리기 쉬움)**: serve 시작할 때 가중치 + KV 캐시 **영역**을 **HBM 에 미리 통째로 예약**합니다. 그래서 `furiosa-smi status` 의 카드 메모리는 켜자마자 거의 꽉 찬 상태(예: 45/47.5 GiB ≈ 94.7%)로 보입니다(dp4 면 4장 모두 ~95%). **그 모델이 처음 추론을 돌리는 순간** 런타임 작업 메모리(활성값·어텐션 스크래치·임시 텐서 풀)가 **한 번 더 ~1GB 할당**되어 **약 46.2/47.5 GiB(≈97.2%)로 오른 뒤 그 수준에서 평평**해집니다(측정 확인). 즉 물리 HBM 은 ①켜면 예약(~45GB) → ②첫 추론 때 작업메모리 추가(~46GB)의 **두 단계로 한 번 오르고 고정**이며, **대화를 더 길게/많이 해도 그 이상 안 늘어납니다.**
  - 반면 serve 가 보고하는 **`RNGD KV cache usage: x%`** 는 그 **예약된 영역 안에서 실제로 채워진 비율**입니다. 대화가 길수록(프롬프트 토큰↑, prefix 캐시에 이전 turn 들이 누적) 이 **% 는 올라갑니다**. 단 KV 풀 전체 용량(=`max_kv_len`, 이 카드가 담을 수 있는 KV 토큰 총량. 예: coder1.5 는 ~157만 토큰 ≈ 42GB. **요청 1개당 컨텍스트 상한 `max_model_len`=32k 과는 다른 값**)을 넘지 못하고, 꽉 차면 오래된 블록부터 교체(eviction)됩니다. 새 채팅을 시작하거나 serve 를 재시작하면 비워집니다. ← 모니터링 대시보드에서 "대화할수록 오르는 수치"는 보통 이 **사용률(%)** 이지, 물리 HBM 이 늘어나는 게 아닙니다.
  - **대화 내용(텍스트)은 서버 디스크 `conversations/*.json` 에 저장**되는 것이고(앱 기록용), NPU 가 대화를 영구 보관하는 게 아닙니다. serve 는 **stateless** 라 매 turn 클라이언트가 전체 대화를 다시 보내고, 서버는 그걸 KV 로 만들되 이전 turn 부분은 **prefix 캐시로 재사용**합니다. 그래서 KV 사용률이 turn 마다 누적되어 보이는 것입니다(디스크 저장과 별개·모순 아님).
  - **예약 45GB 의 정체 / 왜 100% 가 아닌지**: 예약량은 **가중치 + KV 캐시 영역** 입니다. 예) `Qwen2.5-Coder-1.5B` 는 가중치가 3GB 뿐인데도 카드가 45/47.5 GiB(≈95%) 로 보이는데, 이는 furiosa 가 **남는 HBM 대부분(여기선 ~42GB, 157만 토큰분)을 KV 캐시로 미리 확보**하기 때문입니다(모델이 커서가 아님). 남기는 ~5%(약 2.5GB)는 KV 로 안 잡고 비워 두는데, 그 중 일부(~1GB)는 **첫 추론 때 런타임 작업 메모리**(활성값·어텐션 스크래치·tp 코어 간 통신 버퍼)로 실제 할당되어 ~97% 가 되고(위 ②단계), 나머지(~1.3GB)는 단편화·피크 대비 **안전 마진**으로 남습니다 — 100% 를 KV 로 잡으면 계산용 메모리가 없어 OOM 이기 때문. KV 영역이 거대해서, 한 대화(컨텍스트 상한, coder=32768토큰)는 영역의 ~2% 만 채웁니다.
- **빌드 vs serve**: 빌드는 host CPU/RAM, serve 는 NPU HBM 이라 자원이 안 겹칩니다. 빌드 중에도 채팅 serve 가능.
