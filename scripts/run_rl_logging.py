# Stackelberg RL 환경을 다른 로컬 머신에서 토큰 0으로 무한 롤아웃하며 스텝마다 CSV로 스트리밍 저장하는 독립 러너
"""다른 컴퓨터에서 그냥 띄워놓고 데이터를 무한 수집하기 위한 standalone 러너.

설계 원칙.
- LLM/네트워크 호출 0. 순수 로컬 CPU 시뮬레이션만 돈다(토큰 무관).
- 스텝마다 CSV에 append + flush -> 도중에 죽어도 그때까지 데이터는 보존된다.
- 콘솔 출력은 heartbeat 한 줄만(나중에 사후분석은 CSV/JSONL을 뜯어본다).
- policy-pluggable: 지금은 random/scripted. 학습된 정책이 생기면 _pick_actions만 갈아끼우면 된다.

사용 예.
  python -B scripts/run_rl_logging.py --scenario peak_demand --episodes -1 \
      --output-dir outputs/rl_logs/peak --policy random --jsonl

  # 무한(-1) 대신 100 에피소드, 시간 상한 6시간:
  python -B scripts/run_rl_logging.py --scenario heavy_demand_150 \
      --episodes 100 --max-seconds 21600 --output-dir outputs/rl_logs/heavy150
"""
from __future__ import annotations

import argparse
import csv
import json
import signal
import sys
import time
from pathlib import Path

import numpy as np

# 다른 머신에서 `python scripts/run_rl_logging.py`로 바로 실행해도 src 패키지를 찾도록 repo 루트를 등록.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.demand import load_scenarios
from src.models.state import ExperimentConfig
from src.rl.env import (
    StackelbergRLEnvironment,
    _record_summary_row,
    _record_to_jsonable,
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Stackelberg RL 무한 롤아웃 -> CSV 스트리밍 로거")
    p.add_argument("--config", default="src/config/default.yaml")
    p.add_argument("--scenarios-config", default="src/config/scenarios.yaml")
    p.add_argument("--scenario", default="peak_demand")
    p.add_argument("--output-dir", default="outputs/rl_logs/run")
    p.add_argument("--policy", choices=["random", "scripted"], default="random")
    p.add_argument(
        "--episodes",
        type=int,
        default=-1,
        help="에피소드 수. -1이면 무한(Ctrl-C 또는 --max-seconds까지).",
    )
    p.add_argument("--start-episode", type=int, default=0, help="재개 시 마지막+1로 주면 seed가 이어진다.")
    p.add_argument("--seed-base", type=int, default=1000, help="episode i의 seed = seed_base + episode_id.")
    p.add_argument("--max-seconds", type=float, default=None, help="벽시계 시간 상한(초). 초과 시 깔끔히 종료.")
    p.add_argument("--leader-n-p-bins", type=int, default=5)
    p.add_argument("--leader-n-uf-bins", type=int, default=5)
    p.add_argument("--jsonl", action="store_true", help="전체 중첩 기록(관측/액션/진단)을 JSONL로도 저장.")
    p.add_argument("--heartbeat-steps", type=int, default=200, help="N 글로벌 스텝마다 진행 한 줄 출력.")
    return p.parse_args()


class _CsvStream:
    """첫 행에서 헤더를 확정하고 이후 같은 스키마로 append-flush 하는 스트리밍 writer."""

    def __init__(self, path: Path):
        self.path = path
        self._fields: list[str] | None = None
        self._handle = None
        self._writer = None
        # 이미 헤더가 있는 파일이면 그 헤더를 채택해 그대로 이어 쓴다(재개 안전).
        if path.exists() and path.stat().st_size > 0:
            with path.open("r", encoding="utf-8", newline="") as h:
                first = h.readline().strip()
            if first:
                self._fields = first.split(",")
                self._handle = path.open("a", encoding="utf-8", newline="")
                self._writer = csv.DictWriter(
                    self._handle, fieldnames=self._fields, extrasaction="ignore", restval=""
                )

    def write(self, row: dict) -> None:
        if self._writer is None:
            self._fields = ["episode", "seed"] + sorted(
                k for k in row if k not in ("episode", "seed")
            )
            self._handle = self.path.open("a", encoding="utf-8", newline="")
            self._writer = csv.DictWriter(
                self._handle, fieldnames=self._fields, extrasaction="ignore", restval=""
            )
            self._writer.writeheader()
        self._writer.writerow(row)
        self._handle.flush()

    def close(self) -> None:
        if self._handle is not None:
            self._handle.flush()
            self._handle.close()


def _pick_actions(env: StackelbergRLEnvironment, policy: str):
    """정책을 한 곳으로 격리. 학습된 정책이 생기면 여기만 교체하면 된다."""
    if policy == "scripted":
        return env.scripted_safe_action_indices()
    leader_index = env.random_leader_action_index()
    follower_indices = env.random_follower_action_indices()
    return leader_index, follower_indices


def main() -> None:
    args = _parse_args()
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    cfg = ExperimentConfig.from_file(args.config)
    scenario = load_scenarios(args.scenarios_config)[args.scenario]
    steps_per_episode = cfg.simulation.n_control_steps

    csv_stream = _CsvStream(out / "rl_steps.csv")
    jsonl_handle = (out / "rl_steps.jsonl").open("a", encoding="utf-8") if args.jsonl else None

    # Ctrl-C / kill 시에도 버퍼를 비우고 깔끔히 빠져나가도록 플래그로 처리.
    stop = {"flag": False}

    def _request_stop(signum, frame):  # noqa: ARG001
        stop["flag"] = True
        print("\n[run_rl_logging] 중단 신호 수신 -> 현재 스텝 마치고 저장 후 종료.", flush=True)

    signal.signal(signal.SIGINT, _request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _request_stop)

    if args.policy == "scripted" and args.episodes != 1:
        print(
            "[run_rl_logging] 경고: plant는 deterministic이라 scripted 정책 반복은 동일 궤적을 낳습니다. "
            "다양한 데이터를 원하면 --policy random 을 쓰세요.",
            flush=True,
        )

    env = StackelbergRLEnvironment(
        cfg, scenario, leader_n_p_bins=args.leader_n_p_bins, leader_n_uf_bins=args.leader_n_uf_bins
    )

    t0 = time.time()
    global_steps = 0
    episode_id = args.start_episode
    n_target = args.episodes  # -1 == 무한

    print(
        f"[run_rl_logging] scenario={args.scenario} policy={args.policy} "
        f"steps/episode={steps_per_episode} episodes={'inf' if n_target < 0 else n_target} "
        f"-> {out}",
        flush=True,
    )

    try:
        while not stop["flag"] and (n_target < 0 or episode_id < args.start_episode + n_target):
            seed = args.seed_base + episode_id
            env.seed = seed
            env.rng = np.random.default_rng(seed)
            env.reset()

            for _ in range(steps_per_episode):
                leader_index, follower_indices = _pick_actions(env, args.policy)
                step = env.step(leader_index, follower_indices)
                record = env.records[-1]

                row = _record_summary_row(record)
                row["episode"] = episode_id
                row["seed"] = seed
                csv_stream.write(row)

                if jsonl_handle is not None:
                    payload = _record_to_jsonable(record)
                    payload["episode"] = episode_id
                    payload["seed"] = seed
                    jsonl_handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
                    jsonl_handle.flush()

                global_steps += 1
                if global_steps % max(1, args.heartbeat_steps) == 0:
                    elapsed = time.time() - t0
                    print(
                        f"[hb] ep={episode_id} step={record.step_index} "
                        f"ttt={record.global_step_ttt:.1f} Lr={record.leader_reward:.1f} "
                        f"gsteps={global_steps} elapsed={elapsed:.0f}s",
                        flush=True,
                    )

                if stop["flag"]:
                    break
                if step.done or step.truncated:
                    break

            episode_id += 1
            if args.max_seconds is not None and (time.time() - t0) >= args.max_seconds:
                print(f"[run_rl_logging] max-seconds({args.max_seconds}s) 도달 -> 종료.", flush=True)
                break
    finally:
        csv_stream.close()
        if jsonl_handle is not None:
            jsonl_handle.flush()
            jsonl_handle.close()

    elapsed = time.time() - t0
    print(
        f"[run_rl_logging] 완료. episodes={episode_id - args.start_episode} "
        f"global_steps={global_steps} elapsed={elapsed:.0f}s -> {out/'rl_steps.csv'}",
        flush=True,
    )


if __name__ == "__main__":
    sys.exit(main())
