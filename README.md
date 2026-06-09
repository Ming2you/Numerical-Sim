# Numerical-Sim

MPC 기반 Stackelberg game simulation framework for integrated urban-freeway traffic control.

## Language Policy

- 앞으로 report, review note, agent-facing 문서는 한국어로 작성한다.
- 새로 추가하는 코드 주석과 docstring도 한국어로 작성한다.
- 단, 코드 identifier, public API, config key, file path, command, metric name, 수식 기호, 단위 표기는 기존 영어/기호를 유지한다.
- 원문 오류 메시지, command output, CSV column, JSON key를 인용할 때는 원문 spelling을 그대로 보존한다.
- 한국어 report와 주석은 Codex/Claude의 이후 검토에 지장을 주지 않는 것으로 간주한다.

## Repository Sync Policy

- 작업을 시작하기 전에 항상 GitHub의 `origin/main`이 로컬보다 최신인지 확인한다.
- 로컬 working tree가 clean이고 원격에 새 commit이 있으면, 수정 전에 `git pull --ff-only origin main`으로 자동 fast-forward 한다.
- 로컬에 uncommitted change가 있으면 임의로 덮어쓰지 않고, 충돌 가능성을 보고한 뒤 진행 방식을 정한다.
- direct `main` workflow에서는 불필요한 merge commit을 만들지 않도록 fast-forward pull을 기본으로 사용한다.
- 구현, review, report, validation은 pull 이후의 최신 로컬 코드 기준으로 수행한다.

## Repository Structure

```text
.
|-- AGENTS.md
|-- CLAUDE.md
|-- README.md
|-- docs/
|   |-- codex_implementation_spec.md
|   |-- experiment_acceptance_criteria.md
|   |-- log.md
|   `-- spec/
|-- reports/
|   |-- codex_run_report.md
|   |-- claude_review_report.md
|   `-- final_validation_report.md
|-- src/
|   |-- config/
|   |-- controllers/
|   |-- evaluation/
|   |-- experiments/
|   |-- models/
|   |-- simulation/
|   `-- tests/
`-- outputs/
```

## Run

```powershell
python -m experiments.run_experiment `
  --config src/config/default.yaml `
  --scenario peak_demand `
  --baseline fixed_signal_fixed_speed `
  --controller stackelberg_mpc `
  --output outputs/peak_demand_stackelberg
```

With auto-tuning:

```powershell
python -m experiments.run_experiment `
  --config src/config/default.yaml `
  --scenario peak_demand `
  --baseline fixed_signal_fixed_speed `
  --controller stackelberg_mpc `
  --auto-tune `
  --output outputs/peak_demand_stackelberg_autotune
```

## Agent Workflow

- Codex는 구현, 테스트, simulation 실행, run report 작성을 담당한다.
- Claude는 방법론, 코드 정합성, simulation validity를 독립적으로 검토한다.
- 공유 기록은 `docs/log.md`와 `reports/` 아래 Markdown 파일에 남긴다.
- simulation 결과를 해석하기 전에 traffic model/controller가 현재 spec과 충분히 일치하는지 먼저 확인한다.

## Clean Implementation Boundary

활성 구현은 `src/` 아래에 둔다. 과거 root-level model/controller 파일을 다시 참조하지 않고, 현재 code path는 split spec과 structured package를 기준으로 유지한다.
