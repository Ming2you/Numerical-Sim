# Stackelberg 다중에이전트 DDQN 학습을 다른 로컬 머신에서 토큰 0으로 돌리며 에피소드별 학습곡선을 CSV로 스트리밍하고 체크포인트를 저장하는 CLI
"""실제 RL '학습' run. leader+follower DDQN을 동시에 학습한다.

토큰 0(순수 로컬 CPU/GPU). 에피소드마다 CSV append+flush, 주기적 체크포인트, 재개 지원.

사용 예.
  python -B scripts/train_rl_ddqn.py --scenario peak_demand --episodes 2000 \
      --output-dir outputs/rl_train/peak --device cpu

  # 중단 후 재개(마지막 체크포인트에서 이어서):
  python -B scripts/train_rl_ddqn.py --scenario peak_demand --episodes 2000 \
      --output-dir outputs/rl_train/peak --resume
"""
from __future__ import annotations

import argparse
import csv
import json
import signal
import sys
import time
from pathlib import Path

# 다른 머신에서 `python scripts/train_rl_ddqn.py`로 바로 실행해도 src 패키지를 찾도록 repo 루트 등록.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.demand import load_scenarios
from src.models.state import ExperimentConfig
from src.rl.ddqn import DQNConfig, StackelbergDDQNTrainer, set_global_seed
from src.rl.env import StackelbergRLEnvironment

_CSV_FIELDS = [
    "episode",
    "steps",
    "leader_return",
    "mean_follower_return",
    "leader_loss",
    "mean_follower_loss",
    "epsilon",
    "episode_ttt",
    "elapsed_sec",
]

_EVAL_FIELDS = [
    "episode",
    "eval_episodes",
    "mean_ttt",
    "min_ttt",
    "max_ttt",
    "elapsed_sec",
]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Stackelberg 다중에이전트 DDQN 학습 run")
    p.add_argument("--config", default="src/config/default.yaml")
    p.add_argument("--scenarios-config", default="src/config/scenarios.yaml")
    p.add_argument("--scenario", default="peak_demand")
    p.add_argument("--output-dir", default="outputs/rl_train/run")
    p.add_argument("--episodes", type=int, default=1000)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--device", default="cpu", help="cpu 또는 cuda")
    p.add_argument("--leader-n-p-bins", type=int, default=5)
    p.add_argument("--leader-n-uf-bins", type=int, default=5)
    # DQN 하이퍼파라미터
    p.add_argument("--gamma", type=float, default=0.99)
    p.add_argument("--lr", type=float, default=1.0e-3)
    p.add_argument("--batch-size", type=int, default=64)
    p.add_argument("--buffer", type=int, default=50_000)
    p.add_argument("--hidden", default="128,128", help="콤마 구분 은닉층 폭. 예: 128,128")
    p.add_argument("--target-sync-every", type=int, default=500)
    p.add_argument("--min-buffer", type=int, default=500)
    p.add_argument("--eps-start", type=float, default=1.0)
    p.add_argument("--eps-end", type=float, default=0.05)
    p.add_argument("--eps-decay-steps", type=int, default=20_000)
    p.add_argument("--reward-scale", type=float, default=0.01)
    # 운영
    p.add_argument("--max-seconds", type=float, default=None)
    p.add_argument("--checkpoint-every", type=int, default=50, help="N 에피소드마다 latest 체크포인트 저장.")
    p.add_argument("--resume", action="store_true", help="output-dir의 latest.pt에서 이어서 학습.")
    p.add_argument("--eval-every", type=int, default=0)
    p.add_argument("--eval-episodes", type=int, default=1)
    p.add_argument("--early-stop-ttt-threshold", type=float, default=None)
    p.add_argument("--early-stop-window", type=int, default=8)
    p.add_argument("--early-stop-improvement-tol", type=float, default=0.005)
    p.add_argument("--early-stop-min-episodes", type=int, default=0)
    return p.parse_args()


def _open_csv(path: Path):
    is_new = not (path.exists() and path.stat().st_size > 0)
    handle = path.open("a", encoding="utf-8", newline="")
    writer = csv.DictWriter(handle, fieldnames=_CSV_FIELDS, extrasaction="ignore")
    if is_new:
        writer.writeheader()
        handle.flush()
    return handle, writer


def _open_eval_csv(path: Path):
    is_new = not (path.exists() and path.stat().st_size > 0)
    handle = path.open("a", encoding="utf-8", newline="")
    writer = csv.DictWriter(handle, fieldnames=_EVAL_FIELDS, extrasaction="ignore")
    if is_new:
        writer.writeheader()
        handle.flush()
    return handle, writer


def _load_eval_history(path: Path) -> list[tuple[int, float]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        history = []
        for row in rows:
            try:
                history.append((int(row["episode"]), float(row["mean_ttt"])))
            except (KeyError, TypeError, ValueError):
                continue
        return history


def _mean(values: list[float]) -> float:
    return sum(values) / max(1, len(values))


def _early_stop_status(
    history: list[tuple[int, float]],
    threshold: float | None,
    window: int,
    improvement_tol: float,
) -> dict:
    if threshold is None:
        return {"ready": False, "stop": False}
    n = max(1, int(window))
    if len(history) < 2 * n:
        return {"ready": False, "stop": False, "needed_points": 2 * n}
    values = [float(value) for _, value in history]
    previous = _mean(values[-2 * n:-n])
    recent = _mean(values[-n:])
    improvement = (previous - recent) / max(abs(previous), 1.0)
    return {
        "ready": True,
        "stop": recent <= threshold and abs(improvement) <= improvement_tol,
        "previous_mean_ttt": previous,
        "recent_mean_ttt": recent,
        "relative_improvement": improvement,
    }


def _run_greedy_eval(trainer: StackelbergDDQNTrainer, episode: int, eval_episodes: int) -> list[float]:
    values = []
    for _ in range(max(1, int(eval_episodes))):
        stats = trainer.run_episode(episode, train=False, greedy=True)
        values.append(float(stats.episode_ttt))
    return values


def main() -> None:
    args = _parse_args()
    out = Path(args.output_dir)
    (out / "checkpoints").mkdir(parents=True, exist_ok=True)

    set_global_seed(args.seed)
    cfg = ExperimentConfig.from_file(args.config)
    scenario = load_scenarios(args.scenarios_config)[args.scenario]
    env = StackelbergRLEnvironment(
        cfg,
        scenario,
        seed=args.seed,
        leader_n_p_bins=args.leader_n_p_bins,
        leader_n_uf_bins=args.leader_n_uf_bins,
    )

    hidden = tuple(int(x) for x in str(args.hidden).split(",") if x.strip())
    dqn_cfg = DQNConfig(
        gamma=args.gamma,
        lr=args.lr,
        batch_size=args.batch_size,
        buffer_capacity=args.buffer,
        hidden=hidden,
        target_sync_every=args.target_sync_every,
        min_buffer=args.min_buffer,
        eps_start=args.eps_start,
        eps_end=args.eps_end,
        eps_decay_steps=args.eps_decay_steps,
        reward_scale=args.reward_scale,
    )
    trainer = StackelbergDDQNTrainer(env, dqn_cfg, device=args.device, seed=args.seed)

    latest = out / "checkpoints" / "latest.pt"
    start_episode = 0
    meta_path = out / "checkpoints" / "meta.json"
    if args.resume and latest.exists():
        trainer.load(latest)
        if meta_path.exists():
            start_episode = int(json.loads(meta_path.read_text(encoding="utf-8")).get("next_episode", 0))
        print(f"[train] resume: {latest} 에서 episode {start_episode}부터, global_step={trainer.global_step}", flush=True)

    handle, writer = _open_csv(out / "train_curve.csv")
    eval_path = out / "eval_curve.csv"
    eval_handle = None
    eval_writer = None
    eval_history = _load_eval_history(eval_path)
    if args.eval_every > 0:
        eval_handle, eval_writer = _open_eval_csv(eval_path)

    stop = {"flag": False}

    def _request_stop(signum, frame):  # noqa: ARG001
        stop["flag"] = True
        print("\n[train] 중단 신호 수신 -> 체크포인트 저장 후 종료.", flush=True)

    signal.signal(signal.SIGINT, _request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _request_stop)

    print(
        f"[train] scenario={args.scenario} device={args.device} agents=1+{len(trainer.followers)} "
        f"leader_actions={env.leader_action_space.size} episodes={args.episodes} -> {out}",
        flush=True,
    )

    t0 = time.time()
    episode = start_episode
    end_episode = start_episode + args.episodes
    try:
        while not stop["flag"] and episode < end_episode:
            stats = trainer.run_episode(episode, train=True)
            elapsed = time.time() - t0
            writer.writerow(
                {
                    "episode": stats.episode,
                    "steps": stats.steps,
                    "leader_return": round(stats.leader_return, 4),
                    "mean_follower_return": round(stats.mean_follower_return, 4),
                    "leader_loss": round(stats.leader_loss, 6),
                    "mean_follower_loss": round(stats.mean_follower_loss, 6),
                    "epsilon": round(stats.epsilon, 4),
                    "episode_ttt": round(stats.episode_ttt, 3),
                    "elapsed_sec": round(elapsed, 1),
                }
            )
            handle.flush()
            print(
                f"[ep {stats.episode}] Lret={stats.leader_return:.1f} "
                f"Fret={stats.mean_follower_return:.1f} ttt={stats.episode_ttt:.0f} "
                f"eps={stats.epsilon:.3f} Lloss={stats.leader_loss:.4f} t={elapsed:.0f}s",
                flush=True,
            )

            episode += 1
            if (episode % max(1, args.checkpoint_every) == 0) or stop["flag"]:
                trainer.save(latest)
                meta_path.write_text(json.dumps({"next_episode": episode}), encoding="utf-8")

            if args.eval_every > 0 and episode % max(1, args.eval_every) == 0:
                eval_ttts = _run_greedy_eval(trainer, episode, args.eval_episodes)
                eval_elapsed = time.time() - t0
                eval_mean = _mean(eval_ttts)
                eval_history.append((episode, eval_mean))
                if eval_writer is not None and eval_handle is not None:
                    eval_writer.writerow(
                        {
                            "episode": episode,
                            "eval_episodes": max(1, int(args.eval_episodes)),
                            "mean_ttt": round(eval_mean, 3),
                            "min_ttt": round(min(eval_ttts), 3),
                            "max_ttt": round(max(eval_ttts), 3),
                            "elapsed_sec": round(eval_elapsed, 1),
                        }
                    )
                    eval_handle.flush()
                early = _early_stop_status(
                    eval_history,
                    args.early_stop_ttt_threshold,
                    args.early_stop_window,
                    args.early_stop_improvement_tol,
                )
                print(
                    f"[eval ep {episode}] mean_ttt={eval_mean:.1f} "
                    f"min={min(eval_ttts):.1f} max={max(eval_ttts):.1f}",
                    flush=True,
                )
                if early.get("ready"):
                    print(
                        f"[early-stop check] recent={early['recent_mean_ttt']:.1f} "
                        f"previous={early['previous_mean_ttt']:.1f} "
                        f"rel_improve={early['relative_improvement']:.4f}",
                        flush=True,
                    )
                if episode >= args.early_stop_min_episodes and early.get("stop"):
                    print(
                        "[early-stop] greedy eval TTT is below threshold and long-window "
                        "improvement is near zero.",
                        flush=True,
                    )
                    stop["flag"] = True
                    trainer.save(latest)
                    meta_path.write_text(json.dumps({"next_episode": episode}), encoding="utf-8")

            if args.max_seconds is not None and (time.time() - t0) >= args.max_seconds:
                print(f"[train] max-seconds({args.max_seconds}s) 도달 -> 종료.", flush=True)
                break
    finally:
        trainer.save(latest)
        meta_path.write_text(json.dumps({"next_episode": episode}), encoding="utf-8")
        handle.flush()
        handle.close()
        if eval_handle is not None:
            eval_handle.flush()
            eval_handle.close()

    print(
        f"[train] 완료. episodes={episode - start_episode} global_step={trainer.global_step} "
        f"elapsed={time.time() - t0:.0f}s -> {out/'train_curve.csv'} (ckpt: {latest})",
        flush=True,
    )


if __name__ == "__main__":
    sys.exit(main())
