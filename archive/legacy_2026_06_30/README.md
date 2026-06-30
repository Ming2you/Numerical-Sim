# Legacy 보관 (2026-06-30)

WuFaithfulFollower를 "wu" 계열 default로 전환하면서, **분석에서 더 이상 쓰지 않는 옛 standalone 코드**를 여기 보관한다. 사용자가 찾기 전까지 앞으로의 분석/figure 생성에는 사용하지 않는다.

## 여기로 옮긴 것

- `leader_grid_injection_diagnostic.py` — 옛 leader grid 주입 진단 스크립트. 아무 모듈도 import하지 않아 안전하게 이동함.

## 옮기지 *못한* 것 (중요)

다음 옛 컨트롤러 클래스들은 **새 코드가 라이브러리로 의존**하므로 제자리(`src/controllers/`)에 남겨둔다. 물리 이동 시 새 PFO/P-Stack과 ~30개 테스트가 import 단계에서 깨진다.

| 옛 파일 | 왜 남기나 |
|---|---|
| `wu_distributed.py` (`WuDistributedController`) | `WuFaithfulFollower.__init__`이 topology·coupling 재사용 위해 생성 |
| `stackelberg_mpc.py` (`StackelbergMPCController`) | 새 P-Stack(`StackelbergWuMeteredController`)이 **상속** |
| `distributed_coordinator.py` (`DistributedCoordinator`) | `stackelberg_mpc.py`가 import + 테스트 ~30곳 사용 |

→ 이들은 **내부 라이브러리로만 유지**되고, **standalone 비교 컨트롤러로는 분석에서 미사용**이다.

## 분석에서 은퇴한 컨트롤러 (six_controller_comparison 어댑터)

- `WU-CD-F`: 옛 `DistributedCoordinator(ablation="WU_GREEN_VSL_ONLY_TTT")` → **`WuFaithfulFollower(authority="wu")`로 교체**(green+VSL, metering=용량, offset 고정).
- `WU-MATCHED-STACKELBERG`, `WU-CC-F`: 사용자 지정 6-컨트롤러 세트에서 제외(필요 시 어댑터에 정의는 남아 있음).

활성 6 컨트롤러: NO-CONTROL / WU-CD-F(=WuFaithfulFollower wu) / PROPOSED-FOLLOWERS-ONLY(PFO) / PROPOSED-STACKELBERG(P-Stack) / CLASSICAL-HIERARCHICAL / PROPOSED-CENTRALIZED.
