#!/usr/bin/env python3
"""라우터 축출 정책 테스트 — NPU 없이 돈다.

여기서 지키려는 성질(전부 실제로 겪은 사고다):
  · 처리 중인 요청이 있는 백엔드는 축출하지 않는다.
    → 90초짜리 턴을 스트리밍하던 백엔드가 last_used(요청 '시작' 시각) 때문에 가장
      오래 논 것처럼 보여, 다른 모델 요청 하나에 턴이 통째로 끊겼다.
  · 막 올라온 백엔드에는 최소 상주 시간을 준다.
    → K-EXAONE 이 7분 걸려 ready 된 그 초에 축출돼, 카드만 왕복하고 아무도 전진하지 못했다.
  · 그래도 아무도 안 놓아주면 EVICT_WAIT 뒤에 강제로 내린다(교착 금지).
  · 로딩 중(ready=False) 백엔드로는 프록시하지 않는다.
    → _start 는 _wait_ready 前에 running 에 넣으므로, alive() 만 보면 아직 듣지도 않는
      포트로 붙어 ConnectError(→500) 가 났다.

실행:  python3 test_furiosa_router.py
"""
import os
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import furiosa_router as R


class FakeProc:
    """subprocess.Popen 대역 — 살아있음/종료만 흉내낸다."""

    def __init__(self):
        self._alive = True

    def poll(self):
        return None if self._alive else 0

    def terminate(self):
        self._alive = False

    def kill(self):
        self._alive = False

    def wait(self, timeout=None):
        return 0


def make_backend(router, model_id, cards, *, ready=True, inflight=0, last_used=None, ready_at=None):
    b = R.Backend(model_id, 8410 + len(router.running), FakeProc(), cards)
    b.ready = ready
    # 기본은 '충분히 오래전에 올라옴' — grace 를 시험하는 테스트만 ready_at 을 준다.
    b.ready_at = ready_at if ready_at is not None else time.time() - 10_000
    b.inflight = inflight
    b.last_used = last_used if last_used is not None else time.time()
    router.running[model_id] = b
    return b


class EvictionPolicy(unittest.TestCase):
    def setUp(self):
        self.router = R.Router()
        self.stopped = []
        # 실제 종료 대신 기록만 — 카드 해제 대기(furiosa-smi)를 타지 않게 한다.
        orig_stop = self.router._stop

        def fake_stop(b):
            self.stopped.append(b.model_id)
            with self.router.ilock:
                b.evicting = True
                b.ready = False
            b.proc.terminate()
            self.router.running.pop(b.model_id, None)

        self.router._stop = fake_stop
        self.orig_stop = orig_stop
        # 카드 4장 중 running 이 점유한 것을 뺀 나머지가 free.
        self.router._free_cards = lambda: [
            c for c in R.ALL_CARDS
            if c not in {x for b in self.router.running.values() for x in b.cards}
        ]

    def test_idle_lru_is_the_victim(self):
        make_backend(self.router, "old", [0], last_used=time.time() - 100)
        make_backend(self.router, "new", [1], last_used=time.time())
        self.router._evict_until(1)
        self.assertEqual(self.stopped, [], "빈 카드가 이미 2장이면 아무도 내리지 않는다")

        self.router._evict_until(3)
        self.assertEqual(self.stopped, ["old"], "가장 오래 논 백엔드가 먼저 내려간다")

    def test_busy_backend_survives_even_though_it_is_lru(self):
        # 진행 중인 턴: last_used 는 요청 시작 시각이라 가장 오래된 것처럼 보인다.
        make_backend(self.router, "streaming", [0, 1], inflight=1, last_used=time.time() - 300)
        make_backend(self.router, "idle", [2], last_used=time.time())
        self.router._evict_until(2)
        self.assertEqual(self.stopped, ["idle"], "일하는 백엔드 대신 한가한 쪽이 내려가야 한다")

    def test_busy_backend_is_waited_for_not_killed(self):
        busy = make_backend(self.router, "busy", R.ALL_CARDS, inflight=1)

        def finish_later():
            time.sleep(1.5)
            with self.router.ilock:
                busy.inflight = 0

        threading.Thread(target=finish_later, daemon=True).start()
        t0 = time.time()
        self.router._evict_until(4)
        elapsed = time.time() - t0
        self.assertEqual(self.stopped, ["busy"])
        self.assertGreaterEqual(elapsed, 1.0, "요청이 끝날 때까지 기다렸어야 한다")

    def test_forced_eviction_after_evict_wait(self):
        make_backend(self.router, "stuck", R.ALL_CARDS, inflight=1)
        saved = R.EVICT_WAIT
        R.EVICT_WAIT = 0          # 교착 금지: 기다림이 끝나면 강제로 내린다
        try:
            self.router._evict_until(4)
        finally:
            R.EVICT_WAIT = saved
        self.assertEqual(self.stopped, ["stuck"])

    def test_freshly_ready_backend_gets_a_grace_period(self):
        # 방금 ready 된 백엔드(첫 요청도 못 받음)와, 오래전에 올라온 한가한 백엔드.
        make_backend(self.router, "just-ready", [0], ready_at=time.time())
        make_backend(self.router, "long-idle", [1], last_used=time.time() - 500)
        self.router._evict_until(3)
        self.assertEqual(self.stopped, ["long-idle"], "막 올라온 쪽은 건드리지 않는다")

    def test_evict_stops_when_nothing_is_running(self):
        self.router._evict_until(4)   # 빈 라우터 — 무한루프에 빠지지 않아야 한다
        self.assertEqual(self.stopped, [])


class UsableGate(unittest.TestCase):
    """ensure()/acquire() 는 '살아있음'이 아니라 '쓸 수 있음'으로 판정해야 한다."""

    def setUp(self):
        self.router = R.Router()

    def test_loading_backend_is_not_usable(self):
        b = make_backend(self.router, "loading", [0], ready=False)
        self.assertFalse(b.usable(), "_wait_ready 통과 전에는 프록시 대상이 아니다")
        b.ready = True
        self.assertTrue(b.usable())

    def test_evicting_backend_is_not_usable(self):
        b = make_backend(self.router, "going-down", [0])
        b.evicting = True
        self.assertFalse(b.usable(), "내려가는 중인 백엔드를 새 요청이 붙잡으면 안 된다")

    def test_dead_backend_is_not_usable(self):
        b = make_backend(self.router, "dead", [0])
        b.proc.terminate()
        self.assertFalse(b.usable())


class AcquireRelease(unittest.TestCase):
    def setUp(self):
        self.router = R.Router()

    def test_acquire_marks_inflight_and_release_clears_it(self):
        b = make_backend(self.router, "m", [0])
        self.router.ensure = lambda mid: self.router.running[mid].port

        port = self.router.acquire("m")
        self.assertEqual(port, b.port)
        self.assertEqual(b.inflight, 1)

        self.router.release("m")
        self.assertEqual(b.inflight, 0)

    def test_concurrent_requests_stack_and_unstack(self):
        b = make_backend(self.router, "m", [0])
        self.router.ensure = lambda mid: self.router.running[mid].port

        for _ in range(3):
            self.router.acquire("m")
        self.assertEqual(b.inflight, 3)
        for _ in range(3):
            self.router.release("m")
        self.assertEqual(b.inflight, 0)

    def test_release_never_goes_negative(self):
        b = make_backend(self.router, "m", [0])
        self.router.release("m")
        self.assertEqual(b.inflight, 0, "짝이 안 맞아도 음수가 되면 축출 판정이 망가진다")

    def test_release_updates_last_used_to_the_end_of_the_turn(self):
        b = make_backend(self.router, "m", [0], last_used=time.time() - 500)
        self.router.ensure = lambda mid: self.router.running[mid].port
        self.router.acquire("m")
        time.sleep(0.05)
        self.router.release("m")
        self.assertLess(time.time() - b.last_used, 1.0,
                        "긴 스트리밍이 LRU 상 '가장 오래 논' 것으로 보이면 안 된다")

    def test_release_of_an_unknown_model_is_a_no_op(self):
        self.router.release("nope")   # 예외 없이 지나가야 한다


if __name__ == "__main__":
    unittest.main(verbosity=2)
