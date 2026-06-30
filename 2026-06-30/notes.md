# 2026-06-30 작업 노트

## 1. wu 컨트롤러 default를 WuFaithfulFollower로 전환

### 무엇을
- `src/experiments/six_controller_comparison.py` 어댑터: `WU-CD-F` 매핑을
  `DistributedCoordinator(ablation="WU_GREEN_VSL_ONLY_TTT")` → **`WuFaithfulFollower(authority="wu")`** 로 교체.
- PFO(`PROPOSED-FOLLOWERS-ONLY`)·P-Stack(`PROPOSED-STACKELBERG`)는 이미 WuFaithfulFollower 기반이라 변경 없음
  (PFO=`WuFaithfulFollower(cfg)`(authority="proposed"), P-Stack=`StackelbergWuMeteredController`).

### 왜
- 앞으로 모든 분석에서 "wu/PFO/P-Stack"을 **WuFaithfulFollower 한 코드베이스**로 통일.
- 옛 `DistributedCoordinator` 기반 wu 경로는 분석에서 은퇴.

### 검증
- decide()가 이미 `{"WU-CD-F","PROPOSED-FOLLOWERS-ONLY"}`를 같은 `.solve()` 경로로 처리 → 한 줄 교체로 충분.
- 6 컨트롤러 어댑터 생성 import 테스트 통과:
  NO-CONTROL→None, WU-CD-F→WuFaithfulFollower, PROPOSED-FOLLOWERS-ONLY→WuFaithfulFollower,
  PROPOSED-STACKELBERG→StackelbergWuMeteredController, CLASSICAL-HIERARCHICAL→ClassicalHierarchicalController,
  PROPOSED-CENTRALIZED→CentralizedMPC.

## 2. 옛 코드 archive

- `archive/legacy_2026_06_30/` 생성, `leader_grid_injection_diagnostic.py` 이동(git mv).
- **핵심 제약**: 옛 컨트롤러 클래스(`WuDistributedController`, `StackelbergMPCController`, `DistributedCoordinator`)는
  새 코드가 라이브러리로 의존(상속·생성)하고 테스트 ~30곳이 사용하므로 **물리 이동 불가** → 제자리 유지하되
  standalone 분석 컨트롤러로는 미사용. 상세는 `archive/legacy_2026_06_30/README.md`.

## 3. VSL-mod를 default로 (사용자 결정: "smoothness=0 빼고 다")

`src/config/default.yaml` 및 `wu_distributed.py` 영구 변경(기존값 교체):

| 노브 | 변경 | 위치 |
|---|---|---|
| off-ramp storage | 120 → **60** (절반) | default.yaml `urban_link_storage_veh.OR_*_storage` |
| off_ramp_split_ratio | 0.06 → **0.4** | default.yaml `off_ramp_split_ratio` |
| lane_reduction(spillback 강도) | 0.35 → **1.0** (Wu eq22 full lane) | default.yaml `freeway_offramp_capacity_drop` |
| candidate pin | off (`bottleneck_idx=set()`) | wu_distributed.py `_relaxed_freeway_segment_candidates` |
| vsl_smoothness_weight | **미변경(0.1 유지)** | — (사용자 제외) |

→ **plant이 근본적으로 바뀜**: off-ramp 유출 0.06→0.4(freeway의 40%가 urban으로)·spillback full-lane.
**기존 모든 결과·figure와 비교 불가(완전 새 baseline).** urban-freeway coupling이 강해져 interface 분석이 풍부해짐.

**검증**: 새 값 4개 로드 확인, medium_demand T=1800 smoke NaN 없이 동작(no_control 320.6 / WU 320.4).
**관찰**: smoothness 유지로 **MPC(WU/PFO/P-Stack)의 VSL은 대부분 안 켜짐**(medium_demand min VSL=100).
이는 사용자 tradeoff의 예상 결과(과포화 VSL 과활성 회피). **반면 classical hierarchical은 threshold로 VSL 활성**.
pin-off는 단일실험상 효과 0이라 무해하나 이론상 약손해 가능(주석에 복원법 명시).

## 4. off_ramp_split 0.4 → 0.2 재조정 (핵심 발견)

split 0.4 첫 run에서 **P-Stack 파국(−24~38%)·PFO 약화(+56%→+2%)** 발견. 원인 진단:
- **PFO 약화**: split 0.4가 freeway 유량 40%를 urban으로 빼내 → **freeway가 병목이 아님**(비용 16~22%) →
  metering 레버가 칠 대상 없음. (옛 plant freeway 59% → PFO +56%였음.)
- **freeway 수요↑로는 복구 불가**: f2.4/u0.5도 freeway 35% — split이 구조적으로 freeway를 비움.
- **진짜 레버 = off_ramp_split**(검증): urban1.0/f1.6 고정, split 0.4→0.15서 freeway% 22→63%, PFO −0.4→+29%.
- **split 0.2가 균형점**: off-ramp spillback 발화(lane loss ~0.2, VSL 무대 유지) + 고부하서 freeway 병목(55%)
  → PFO +24%·metering 켜짐·**PFO VSL도 켜짐(min 70)**. → **default split 0.2로 확정**.
- **P-Stack 파국 원인**: leader N_P_crit_veh=509(옛 plant)인데 split 0.4 plant 보호영역 누적이 2071~8681(4~17배)
  → leader가 극단 N_P 목표(−734)로 진동·오작동. split 0.2서도 **N_P_crit 재보정 필요**(TODO).

## 5. 8 시나리오 확정 (split 0.2, 균형×강도 factorial)

보정 그리드로 균형(freeway%)·강도(peakQ) 확정. 전부 seeded ±15% 게이트 가중(비대칭):

| 시나리오 | u / f=ramp | freeway% | peakQ | regime |
|---|---|---|---|---|
| urban_med | 1.3/1.5 | 25% | 696 | urban-heavy 중간 |
| urban_peak | 1.8/1.5 | 25% | 2085 | urban-heavy peak |
| bal_med | 1.0/1.6 | 42% | 844 | balanced 중간 |
| bal_peak | 1.2/1.7 | 52% | 2910 | balanced peak |
| fwy_med | 0.7/1.7 | 56% | 1127 | freeway-heavy 중간 |
| fwy_peak | 0.7/1.9 | 60% | 3405 | freeway-heavy peak |
| bal_skew | 1.0/1.6 +서동2:1 | 42% | — | balanced+skew |
| bal_incident | 1.0/1.6 +FW_E폐쇄1800-3600 | ↑ | — | balanced+incident |

**발견: freeway는 cliff가 있음**(f1.6↔1.7 사이 급전이). f≤1.6 urban지배, f≥1.7 freeway병목+급혼잡(capacity-drop).

## 6. off_ramp_split 0.4 → 0.2 (최종) + 컨트롤러 재보정

- **split 0.4 → 0.2**: metering·VSL 둘 다 살아나는 균형점(고부하서 freeway 병목 55%, PFO+24%·VSL min70 켜짐).
  freeway엔 cliff(f1.6↔1.7) 존재 — 병목 되면 이미 capacity-drop 급혼잡.
- **N_P_crit_veh 509 → 1142** (split 0.2 plant MFD argmax, production 41524 @ N_P=1142).
  leader·hierarchical·centralized가 공유하는 perimeter 기준 → 하나로 셋 다 정정.
- **재보정 검증(fwy_peak)**: 음수였던 셋 전부 정상화 — PFO +48.0%, P-Stack +47.3%(was −37.7%),
  centralized +56.4%(was −6.3%), hierarchical +4.4%(was −1.7%). P-Stack N_P 진동도 −800 근처 안정.

## 7. leader 가치 진단 (사용자 질의)

- **P-Stack < PFO 원인(fwy_peak)**: leader가 N_UF 목표로 follower metering을 제약(error=0 binding) →
  PFO 자유선택과 다른 궤적 → 약손해. perimeter penalty(target_penalty)는 0(N_P<crit이라 미발화).
  근본=objective fidelity gap + follower 미수렴(nonconvergence_penalty 5.43).
- **leader가 작동하려면 urban 누적 > N_P_crit(1142)** 필요. 8 시나리오 전부 누적 ≤730(미달) → leader 무력이 정상.
  urban_scale 3.0+에서 누적이 임계 돌파(u3.2→1320, u3.5→1666).
- **urban_gridlock(u3.2/f0.9) 추가**: 누적 1320>임계. P-Stack **+0.28% vs PFO +0.17%** → **leader가 이김**.
  단 gridlock선 모든 컨트롤러 ~0%(수요초과 근본한계)라 leader 절대가치 미미(+0.11pp).
  → **이 plant에서 leader value는 작다**(양수지만). 사용자 가설(수요 부족) 확정.

## 시나리오 최종(9개): urban_med/urban_peak/bal_med/bal_peak/fwy_med/fwy_peak/bal_skew/bal_incident + urban_gridlock

## TODO (다음)
- 9 시나리오 × 6 컨트롤러 full run (T=3600) → 데이터.
- 6-섹션 정량 분석(docs/figure_design 규격).
- (선택) urban_peak를 u3.0+로 올려 leader 무대 강화 검토.
