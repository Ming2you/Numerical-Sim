# 2026-06-23 작업 노트

## RL 학습/실행 인프라 추가 (다른 로컬 머신에서 토큰 0으로 run)

동기. 학습/롤아웃은 순수 로컬 CPU/GPU 연산이라 LLM 토큰과 무관하다. 다른 컴퓨터에서 띄워놓고
CSV로 무한 저장 → 사후분석하는 워크플로를 구성했다.

### 1. 데이터 수집 러너 — `scripts/run_rl_logging.py`
- 학습 없이 random/scripted 정책으로 환경을 굴려 **스텝마다 CSV append+flush**(크래시 안전).
- `--episodes -1` 무한, Ctrl-C/`--max-seconds` 종료, 같은 output-dir 재개(append).
- 의존성 numpy만. plant deterministic이라 다양성은 `--policy random`(에피소드별 seed)에서 나옴.

### 2. DDQN 학습 — `src/rl/ddqn.py` + `scripts/train_rl_ddqn.py`
- **leader 1 + follower N 독립 Double DQN**(PyTorch). 에이전트별 online/target Q-net, 리플레이, Adam.
- Stackelberg 순서 보존: leader가 ε-greedy로 target 선택 → 그 target 조건으로 follower 관측 생성
  → follower 선택 → `env.step`. transition next_obs는 한 스텝 지연 완성(follower next_obs가 다음
  스텝 leader action 조건으로 잡혀 bootstrap 분포 불일치 방지).
- 보상 규모(leader ~ -1e3~-2e4)가 커서 `reward_scale`(기본 0.01)로 축소 + Huber loss + grad clip.
- 에피소드별 학습곡선 CSV 스트리밍, 주기적 체크포인트(`latest.pt`+`meta.json`), `--resume` 재개.

### 검증
- 신규 테스트 `src/tests/test_rl_ddqn.py` 4건 + 기존 `test_rl_environment` 10건 = **14/14 통과**.
- E2E 스모크(peak, 6+3 에피소드): leader 1+follower 13, leader action 25개. **학습 확인** —
  leader_loss 3.92→0.12 단조감소, episode_ttt 12,888→~8,500 하락. 재개 정상(global_step 240→360).

### 메모/주의
- torch는 런타임에 없어서 설치함(2.12.1 CPU). `requirements.txt` 신규 작성(numpy/torch/pandas/matplotlib).
- config 파서는 자체 구현(`_load_simple_yaml`)이라 PyYAML 불필요.
- 현 milestone 기준 leader N_P* action bin이 [-3500,3500] 균일 5등분이라 도달범위 밖(별도 권고:
  `reports/rl_code_review_2026-06-23.md`). 학습 정책이 N_P* 신호를 실제로 쓰는지 학습 후 측정 가능.

### 다른 머신 실행
```
git clone https://github.com/Ming2you/Numerical-Sim.git && cd Numerical-Sim
pip install -r requirements.txt
# 학습:
python -B scripts/train_rl_ddqn.py --scenario peak_demand --episodes 2000 \
    --output-dir outputs/rl_train/peak --device cpu
# 데이터 수집만:
python -B scripts/run_rl_logging.py --scenario peak_demand --episodes -1 \
    --output-dir outputs/rl_logs/peak --policy random --jsonl
```

### TODO
- 학습된 정책으로 N_P* bin 유효-퇴화 실측 → 필요시 bin을 reachability 영역으로 재배치.
- 평가 모드(greedy rollout) + MPC(P-Stack) 대비 성능 비교 스크립트.
- 장기 학습 안정성(reward_scale/lr/target_sync) 튜닝.
