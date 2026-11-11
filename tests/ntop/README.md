# ntop.py 시험

`ntop.py`(`ntop`, `nctop`)의 단위 시험과 tmux 종단 시험. 기본으로 가짜 smi 만 써서 실제 NPU·GPU 를 두드리지 않는다.

## 실행

```bash
cd ~/RNGD-proj
python3 tests/ntop/test_ntop.py                 # 단위·합성 화면 시험, 약 20초
python3 tests/ntop/e2e.py                       # tmux 종단 시험 전부, 약 2분
python3 tests/ntop/e2e.py pages jobs            # 이름을 주면 그것만
NCTOP_E2E_REAL=1 python3 tests/ntop/e2e.py pages cost   # 실제 smi 로 (이 서버 구성 기준, 장치를 조회한다)
~/furiosa/bin/python3 tests/ntop/test_ntop.py   # 다른 rich 판(venv 의 15.0.0)으로
NTOP_DIR=/다른/폴더 python3 tests/ntop/test_ntop.py     # 다른 곳의 ntop.py 를 시험
```

필요한 것: `rich`, `tmux`(종단 시험만). 종단 시험은 전용 tmux 서버(`tmux -L nctop-e2e-<pid>`)를 띄웠다가 내린다.

## 파일

| 파일 | 내용 |
|---|---|
| `test_ntop.py` | 키 해석, `nvidia-smi` csv·pmon 해석, 하위 프로세스 관리, 수집 스레드, 화면 배치(터미널 크기 12종 × 구성 14종) |
| `e2e.py` | 실제 터미널에서 몰아 본다: 화면 전환, 종료 뒤 `stty`, 창 크기 변경, Ctrl+Z·bg·fg, 시그널과 종료 코드, smi 고장 |
| `fakebin/nvidia-smi` | 가짜 nvidia-smi. `FAKE_SMI=one`(1장 유휴) `multi`(4장 부하) `old`(옛 드라이버) `down`(드라이버 오류) `hang`(무응답) `slowpmon`(pmon 만 무응답) |
| `fakenpu/furiosa-smi` | 가짜 furiosa-smi. `FAKE_NPU=ok` `hang` `none` `fail`. `ok` 는 같은 폴더의 `status.json`·`info.json` 을 그대로 낸다 |

## 종단 시험 이름

| 이름 | 보는 것 |
|---|---|
| `pages` | 첫 화면 구성, `→`/`←`·`l`/`h`·Tab·숫자, application 모드 화살표, 응답 시간 |
| `quit` `esc` | `q`·Ctrl+C·SIGTERM·`ㅂ` 뒤 터미널 설정과 종료 코드, Esc 뒤의 `q` |
| `resize` `small` `shortwide` | 창 크기 변경, 80x24, 160x24 |
| `variants` | `ntop`, `--gpu`, `--no-gpu`, `--no-ps`, `--raw`, `-p` |
| `notty` | stdin 이 터미널이 아닐 때 |
| `suspend` `jobs` `signals` | Ctrl+Z·bg·fg, `nctop &`, SIGTERM·SIGHUP·SIGSTOP |
| `tostop` | `stty tostop` 셸에서 배경 작업이 멈춰 남지 않는지 |
| `storm` | 키 연타 |
| `hang` `down` `old` `multi` `slowpmon` | nvidia-smi 무응답·오류·옛 드라이버·GPU 4장·pmon 무응답 |
| `orphans` `orphans_npu` | 끝낼 때 도는 중이던 smi 정리 (nvidia-smi 무응답, furiosa-smi 무응답) |
| `cost` | nctop 자신의 CPU 비용 (`NCTOP_E2E_REAL=1` 일 때만) |
