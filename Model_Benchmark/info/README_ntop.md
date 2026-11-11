# ntop / nctop — NPU·CPU·GPU 실시간 모니터

`furiosa-smi` 와 `nvidia-smi` 를 매번 직접 치는 대신 htop처럼 한 화면에서 보여줍니다.

```bash
ntop      # NPU 모니터 (0.5초마다 갱신)
nctop     # ntop + CPU·RAM 요약 + GPU 표, 둘째 화면에 CPU 코어별 사용률과 GPU 상세
```

| 옵션 | 의미 |
|---|---|
| `-i 1` | 갱신 간격 1초 (기본 0.5) |
| `--no-ps` | 프로세스 패널 숨김 |
| `--cpu` / `--no-cpu` | CPU 패널 켜기/끄기 (`nctop` 은 켜진 채로 시작) |
| `--gpu` / `--no-gpu` | GPU 패널 켜기/끄기 (`nctop` 은 `nvidia-smi` 가 있으면 켜진 채로 시작) |
| `-p 2` | 둘째 화면에서 시작 |
| `--raw` | furiosa-smi 원본 JSON 디버그 |

## 화면과 키

```
첫 화면 (1 Overview)                    둘째 화면 (2 Detail)
┌ 요약 한 줄 ──────────────┐            ┌ 요약 한 줄 ──────────────────┐
│ NPU Devices   표         │    →       │ CPU · RAM · SWAP · load      │
│ CPU · RAM · SWAP 한 줄   │  ─────▶    │ 코어별 사용률 (NUMA 노드별)  │
│ GPU Devices   표         │  ◀─────    │ GPU 상세: 사용률·메모리·     │
│ Processes                │    ←       │  전력·온도 막대, 프로세스    │
└──────────────────────────┘            └──────────────────────────────┘
```

| 키 | 동작 |
|---|---|
| `→` / `←` | 다음 / 이전 화면. `l` / `h`, `Tab` / `Shift+Tab`, 숫자 `1` · `2` 도 같다 |
| `q` | 종료. `Ctrl+C` 도 된다 |

- 화면이 둘인 것은 CPU 나 GPU 패널이 켜져 있을 때다. `ntop` 은 첫 화면만 있다.
- GPU 패널이 꺼져 있으면(`--no-gpu`, 또는 `nvidia-smi` 가 없는 서버) 첫 화면이 예전 배치 그대로다: 폭 120칸 이상에서 CPU 패널에 코어별 사용률이 같이 나온다.
- 둘째 화면이 터미널 높이에 다 안 들어가면 코어를 한 칸 막대(`▁▂▃▄▅▆▇█`)로 줄여 GPU 상세 자리를 낸다. 첫 화면은 세로가 모자라면 NPU 표의 행 구분선을 뺀다.
- GPU 상세의 프로세스 표에서 `SM%` 는 연산, `MEM%` 는 GPU 메모리 읽기·쓰기 사용률이다 (`nvidia-smi pmon` 의 `sm`, `mem`).

---

## 갱신 주기

| 대상 | 주기 |
|---|---|
| NPU, CPU·RAM | `-i` 값 (기본 0.5초) |
| GPU 상태 (`nvidia-smi --query-gpu`) | 1초 |
| 프로세스 목록 (`nvidia-smi pmon`, `ps`) | 2초 |

- `-i` 가 위 주기보다 길면 전부 `-i` 를 따른다. 빠르게: `ntop -i 0.2` / 느리게: `ntop -i 2`.
- GPU 와 프로세스를 덜 자주 묻는 까닭: 한 번 부를 때마다 CPU 를 `nvidia-smi --query-gpu` 27 ms, `nvidia-smi pmon` 44 ms, `ps` 31 ms 쓴다. 0.5초마다 전부 부르면 nctop 이 코어 하나의 33% 를 쓰고, 주기를 나누면 18% 다 (2026-11-11 실측, 15초 평균. GPU 패널이 없던 때는 14.5%).
- 수집은 종류마다 따로 돈다 (NPU, CPU·RAM, GPU 상태, GPU 프로세스, `ps`). 키 입력과 창 크기 변경은 수집을 기다리지 않고 바로 반영된다 (→ 키 응답 0.06초, 2026-11-11 tmux 실측).

---

## `ntop` 한 단어로 호출되는 원리

`ntop` 만 쳤을 때 어디서든 화면이 뜨도록 만들려면 **세 가지** 가 맞아야 합니다.

### 1. 파일 첫 줄에 "이 파일은 무슨 인터프리터로 실행할까?" 를 적는다 — **shebang**

`~/RNGD-proj/ntop.py` 의 첫 줄은 다음과 같습니다.

```python
#!/usr/bin/env python3
```

이 줄을 **shebang**(셔뱅) 이라고 부릅니다. 리눅스가 파일을 실행하라고 했을 때 첫 줄이 `#!` 로 시작하면, **그 뒤에 적힌 프로그램으로 이 파일을 열어준다는 약속**입니다.

- `/usr/bin/env python3` 이라고 적으면 → "PATH 에서 `python3` 찾아서 그걸로 이 파일을 실행해라"
- 만약 shebang 이 없으면 → 그냥 텍스트 파일로 취급되어 `./ntop.py` 가 동작하지 않음

bash 스크립트라면 `#!/usr/bin/env bash`, sh 라면 `#!/bin/sh` 식으로 적습니다.

### 2. 파일이 "실행 가능" 으로 표시돼 있어야 한다 — **실행 권한**

리눅스 파일에는 읽기(r) / 쓰기(w) / 실행(x) 세 가지 권한이 있습니다. `.py` 파일은 기본적으로 읽기·쓰기만 켜져 있어서 (`-rw-r--r--`), 그대로는 **명령처럼 실행되지 않습니다**. 다음 한 번으로 실행 권한을 켜줍니다.

```bash
chmod +x ~/RNGD-proj/ntop.py
```

이러면 권한이 `-rwxr-xr-x` 로 바뀌고, `./ntop.py` 처럼 직접 호출했을 때 shebang 덕에 python3 로 실행됩니다.

확인:

```bash
ls -la ~/RNGD-proj/ntop.py
# -rwxr-xr-x  ...  ntop.py     ← x 가 켜져있어야 OK
```

### 3. PATH 에 있는 곳에 심볼릭 링크를 둔다 — **어디서든 호출**

여기까지만 하면 `~/RNGD-proj/ntop.py` 라고 풀 경로를 쳐야 실행됩니다. 그냥 `ntop` 만으로 동작하게 하려면, **PATH 환경변수에 들어있는 디렉토리** 중 하나에 짧은 이름으로 링크를 만들어 둡니다.

`~/.local/bin` 이 PATH 에 들어있어서 (Ubuntu 디폴트, `~/.profile` 에서 처리됨) 거기에 심볼릭 링크 하나 만들면 끝.

```bash
ln -sfn ~/RNGD-proj/ntop.py  ~/.local/bin/ntop
```

확인:

```bash
which ntop
# /home/jun/.local/bin/ntop

readlink -f $(which ntop)
# /home/jun/RNGD-proj/ntop.py
```

### `nctop` 은 어떻게 다른 동작을 하나? — **argv[0] 트릭**

`~/.local/bin/nctop` 도 같은 `ntop.py` 를 가리키는 또 다른 심볼릭 링크입니다.

```bash
ln -sfn ~/RNGD-proj/ntop.py  ~/.local/bin/nctop
```

스크립트 안에서 "내가 어떤 이름으로 호출됐는지" 를 확인해서 동작을 바꿉니다.

```python
# ntop.py 안
import os, sys
invoked_as_nctop = os.path.basename(sys.argv[0]).lower().startswith("nctop")

# argparse 의 --cpu 옵션 default 를 위 변수로 줌
ap.add_argument("--cpu", action="store_true", default=invoked_as_nctop, ...)
```

즉 **한 파일에 두 명령**이 사는 셈입니다. `ntop` 으로 부르면 NPU 만, `nctop` 으로 부르면 CPU 패널과 GPU 패널(`--gpu` 의 default 도 같은 변수, 단 `nvidia-smi` 가 있을 때만)까지 자동으로 켜짐.

---

## 만약 `~/.local/bin` 이 PATH 에 없다면

대부분의 Ubuntu/Debian 은 자동으로 들어있지만, 아니면 한 줄 추가:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

또는 `~/bin/` 디렉토리를 만들고 거기에 심볼릭 링크를 둬도 됩니다 (Ubuntu 가 다음 로그인부터 자동으로 PATH 에 추가).

---

## 데이터 출처

ntop 가 어디서 정보를 가져오는지:

- `furiosa-smi status --format json` — `pe_utilizations[]`, `memory` (2026.4.0 부터 `memory.DRAM` 단계가 없다)
- `furiosa-smi info --format json` — `temperature`, `power`, `firmware`
- `/sys/class/rngd_mgmt/rngd!npuNmgmt/device_state`, `heartbeat` — NPU Status (2026.4.0 부터 status JSON 에 `liveness` 가 없다)
- `furiosa-smi ps` — `--raw` 화면에만
- `nvidia-smi --query-gpu=... --format=csv,noheader,nounits` — GPU 사용률·메모리·온도·전력·클럭·PCIe·ECC. 드라이버가 모르는 필드는 빼고 다시 묻는다
- `nvidia-smi pmon -c 1 -s um` — GPU 를 쓰는 프로세스와 프로세스별 사용률·메모리. 사용자와 명령줄은 `/proc/<pid>` 에서 읽는다
- `/proc/stat` (delta) — CPU 코어별 사용률
- `/sys/devices/system/node/node*/cpulist` — 코어를 NUMA 노드별로 묶기
- `/proc/meminfo` — 호스트 RAM
- `/proc/loadavg`, `ps -eo`

JSON 파싱이 깨지면 `ntop --raw` 로 원본 확인.

## 주의

- ★ `nvidia-smi` 가 응답하지 않아도 NPU·CPU 패널과 키는 제 속도로 돈다. GPU 표에는 `nvidia-smi 응답 대기 중` 이, 3초 뒤에는 `nvidia-smi 응답 없음 (3s 초과)` 이 나온다 (2026-11-11, 60초 동안 답이 없는 가짜 `nvidia-smi` 로 시험: 첫 화면 0.75초, → 키 응답 0.05초).
- ★ `furiosa-smi` 가 멈추면 요약 줄에 `NPU 데이터 N초 전` 이 빨갛게 뜬다.
- stdin 이 터미널이 아니면(`nctop < /dev/null`) 키를 읽지 않는다. 화면 전환이 안 되니 `-p 2` 로 시작 화면을 고른다.
- GPU 가 여러 장이라 둘째 화면에 다 안 들어가면 GPU 세부 값(클럭·PCIe·드라이버·UUID)을 빼고 막대와 프로세스만 남긴다. 그래도 넘치는 아래쪽은 잘린다 (160x50 에서 4장까지 확인).

---

## 파일 위치 정리

| 경로 | 무엇 |
|---|---|
| `~/RNGD-proj/ntop.py` | 본 코드 (Python + rich) |
| `~/RNGD-proj/ntop.sh` | bash + watch 버전 (rich 없이 원본 표 색칠) |
| `~/.local/bin/ntop` | `ntop.py` 심볼릭 링크 |
| `~/.local/bin/nctop` | `ntop.py` 심볼릭 링크 (argv[0] 으로 CPU 모드) |

의존성: `rich` (PyPI). 시스템 `/usr/bin/python3` 와 venv `~/furiosa/bin/python3` 양쪽에 이미 설치돼 있음.
