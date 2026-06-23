# Codex 작업 지시: Stackelberg 다중에이전트 DDQN 학습 실행

이 문서 하나로 학습을 처음부터 끝까지 돌릴 수 있도록 자립형으로 정리했다. 이 repo
(`Numerical-Sim`) 루트에서 작업한다.

## 0. 핵심 사실 (먼저 읽을 것)
- 학습은 **순수 로컬 연산**이다. LLM/네트워크 호출이 없으므로 토큰을 쓰지 않는다. 마음껏 오래 돌려도 된다.
- 구조는 **leader 1 + follower N 독립 Double DQN**이다. leader가 (N_P*, N_UF*) target을 고르면
  그 target을 조건으로 follower(도시 신호·고속도로 VSL/metering)가 로컬 action을 고른다(Stackelberg 순서).
- 트레이너 코어: `src/rl/ddqn.py`. 실행 CLI: `scripts/train_rl_ddqn.py`. 둘 다 이미 구현·테스트되어 있다.
- plant는 deterministic이라 탐색 다양성은 ε-greedy에서 나온다.

## 1. 환경 준비
```bash
# Codex 런타임 python에 torch가 없으면 설치(한 번만).
python -m pip install -r requirements.txt
# 또는 최소: python -m pip install numpy torch

# 무결성 확인(18/18 통과해야 함):
python -B -m unittest src.tests.test_rl_environment src.tests.test_rl_ddqn
```
torch는 CPU 빌드면 충분하다. Q-net이 작아 병목은 교통 plant 시뮬(CPU-bound)이라 GPU 이득이 거의 없다.
CUDA가 있으면 `--device cuda`를 써도 되지만 필수는 아니다.

## 2. 학습 실행 (메인)
시나리오 하나당 한 프로세스. 먼저 `peak_demand`로 시작한다.
```bash
python -B scripts/train_rl_ddqn.py \
    --scenario peak_demand \
    --output-dir outputs/rl_train/peak \
    --episodes 3000 \
    --device cpu \
    --hidden 128,128 \
    --lr 1e-3 --gamma 0.99 \
    --batch-size 64 --buffer 50000 \
    --target-sync-every 500 --min-buffer 1000 \
    --eps-start 1.0 --eps-end 0.05 --eps-decay-steps 40000 \
    --reward-scale 0.01 \
    --checkpoint-every 50
```
- 1 에피소드 = `n_control_steps`(peak 기준 40 step). 3000 에피소드 ≈ 12만 env-step.
- CPU 대략 step당 ~0.06s -> **3000 에피소드 ≈ 2시간** 수준(머신마다 다름). 백그라운드로 돌릴 것.
- `--eps-decay-steps 40000`이면 약 1000 에피소드 부근에서 ε이 0.05로 수렴한다.

학습할 시나리오 권장 순서(각각 별 output-dir).
1. `peak_demand` (기본 혼잡)
2. `heavy_demand_150` (강한 수요)
3. `incident_freeway` 또는 capacity-drop 계열 (VSL 작동 regime)
4. `skew_peak` (비대칭 수요)

여러 개를 동시에 돌리려면 프로세스를 분리하고 output-dir만 다르게 준다(서로 독립).

## 3. 모니터링 — 학습이 되고 있는지 판단
`outputs/rl_train/<scn>/train_curve.csv` 컬럼.

| 컬럼 | 의미 | 학습되면 |
|---|---|---|
| `episode_ttt` | 에피소드 총 통행시간(시스템 비용, **낮을수록 좋음**) | 우하향 추세 |
| `leader_return` | leader 누적 보상(=−시스템비용 계열) | 우상향 |
| `mean_follower_return` | follower 평균 누적 보상 | 우상향 |
| `leader_loss` / `mean_follower_loss` | Q 회귀 손실 | 초기 급감 후 낮게 안정 |
| `epsilon` | 탐색률 | 설정대로 감소 |

판단 기준. ε이 충분히 낮아진(>1000 에피소드) 구간에서 `episode_ttt`가 **초기 평균 대비 뚜렷이 낮으면**
학습 성공. 손실만 0에 붙고 `episode_ttt`가 안 내려가면 보상 스케일/lr/탐색을 조정한다(§6).

## 4. 체크포인트 / 재개
- `--checkpoint-every N` 마다 `outputs/rl_train/<scn>/checkpoints/latest.pt`(+`meta.json`) 저장.
- 중단(또는 종료) 시에도 마지막 상태 저장. 이어서 학습:
```bash
python -B scripts/train_rl_ddqn.py --scenario peak_demand \
    --output-dir outputs/rl_train/peak --episodes 2000 --resume   # 하이퍼파라미터는 동일하게
```
- Ctrl-C 보내면 현재 에피소드 마치고 체크포인트 저장 후 종료한다(`--max-seconds`로 시간 상한도 가능).

## 5. 학습 후 평가 (greedy rollout)
트레이너는 탐색을 끈 greedy 평가를 이미 지원한다(`run_episode(i, train=False, greedy=True)`).
학습 전(랜덤)과 학습 후(greedy) `episode_ttt`를 비교하면 정책 가치가 보인다. 예:
```python
import numpy as np
from src.models.demand import load_scenarios
from src.models.state import ExperimentConfig
from src.rl.ddqn import DQNConfig, StackelbergDDQNTrainer
from src.rl.env import StackelbergRLEnvironment

cfg = ExperimentConfig.from_file("src/config/default.yaml")
scn = load_scenarios("src/config/scenarios.yaml")["peak_demand"]
env = StackelbergRLEnvironment(cfg, scn, seed=0)
trainer = StackelbergDDQNTrainer(env, DQNConfig(), device="cpu", seed=0)
trainer.load("outputs/rl_train/peak/checkpoints/latest.pt")
ttt = [trainer.run_episode(i, train=False, greedy=True).episode_ttt for i in range(3)]
print("greedy episode_ttt:", np.mean(ttt))
```
(여력이 되면 이 평가를 `scripts/eval_rl_ddqn.py`로 만들어 MPC P-Stack의 동일 시나리오 TTT와 비교하는 표를
뽑아도 좋다. 단 이건 선택 사항이다.)

## 6. 안 될 때 튜닝 순서
1. `episode_ttt`가 안 내려가면 `--reward-scale`을 0.01 → 0.005 또는 0.02로 조정(Q값 발산/소멸 균형).
2. 그래도면 `--lr`을 1e-3 → 5e-4, `--target-sync-every`를 500 → 1000으로(안정화).
3. 탐색 부족 의심 시 `--eps-decay-steps`를 늘려 더 오래 탐색.
4. 손실이 발산하면 `--batch-size`를 키우고(128) `--min-buffer`를 늘린다(2000).

## 7. 알려진 제약 (보고에 명시할 것)
- leader N_P* action 격자는 현재 `[-100, 1000]` 컴팩트 범위로 클램프되어 있다(`action_space.py`의
  `DEFAULT_DDQN_N_P_RANGE`). 물리 가용범위 안이라 도달 불가 bin 문제는 완화됨.
- N_P*는 plant 직접 입력이 아니라 **follower의 관측 신호**다. 따라서 학습 후 leader 정책이 N_P*를 실제로
  구분해서 쓰는지(=bin이 의미 있는지) 확인하면 좋다(greedy rollout에서 leader_action 분포를 보면 됨).
- inflow/outflow allocation은 이번 milestone에서 학습 action으로 열지 않았다(fixed placeholder).

## 8. 산출물 / 커밋 규칙
- 학습 로그(`outputs/rl_train/**`)는 보통 커밋하지 않는다(용량). 최종 체크포인트와 요약 표/그림만 정리.
- 코드 변경이 있으면 의미 단위로 커밋하고 메시지는 `YYYY-MM-DD: 설명` 형식, 끝에
  `Co-Authored-By` 라인을 붙인다(이 repo 규칙).
- 작업 내용은 `YYYY-MM-DD/notes.md`에 기록한다.
