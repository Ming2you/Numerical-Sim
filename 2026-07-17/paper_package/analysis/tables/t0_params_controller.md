# 표 0b — 컨트롤러 파라미터 (§0 게재용)

> 출처 규약: `state.py`/`yaml` = 표 0a와 동일. `runner:줄` =
> `work/run_claude_style_five_controller.py`. `follower:줄` =
> `src/controllers/wu_faithful_follower.py`. `sw:줄` = `src/controllers/stackelberg_wu_metered.py`.
> `smpc:줄` = `src/controllers/stackelberg_mpc.py`. `dc:줄` = `src/controllers/distributed_coordinator.py`.
> `cm:줄` = `src/controllers/centralized_mpc.py`. 코드 스냅샷 = offiter repo `0af8778`(2026-07-17).

## P-Stack(walk-MVG) — 본문 제안 컨트롤러

재현 명령(ANALYSIS_PLAN_FINAL.md §7): `P-STACK-WU-FAITHFUL-ALLPRICE-JOINT` +
`BOX_WALK=1 BOX_WALK_VG=1 VSL_BOX=10 METER_BOX=300 NP_PD_ITER=4 NP_BIAS=1 CROSS_OFF=1 FAR_STATE_AWARE=1 SEG13=1 WARMUP_NC_STEPS=20`, `--T-total 10800`.

| 파라미터 | 값 | 출처 |
|---|---|---|
| MPC horizon (horizon_steps) | 3 스텝 (=540 s) | yaml:182, state.py:340; 재현 명령에 HORIZON env 없음 (플래그십은 기본값 사용) |
| leader value depth (leader_value_depth) | 3 스텝 | runner:252–255 (ALLPRICE-JOINT 블록이 env 미지정 시 3으로 설정) |
| leader 전체 rollout 깊이 | horizon+depth = 6 스텝 (=1,080 s, 18분) | smpc:2296 (`depth = horizon_steps + leader_value_depth`) |
| leader 탐색 모드 | grid (runner가 continuous를 override) | runner:78–83 |
| leader 후보 격자 | 전역 ≤49 (≈7×7) / refinement 25 | yaml:184–185, state.py:357–358; leader.py:96–98, 192; smpc:771–777, 803–812 |
| 전역 재탐색 주기 | 1,800 s (=10스텝; 그 외 스텝은 previous 인근 국소 격자 ≤49) | yaml:186, smpc:752–755 |
| local refinement 생략 + rollout 조기절단 (OPT12) | ON (기본) | runner:256–261 |
| follower Jacobi sweep 수 | s_max = min(max_nash_iter, 5) = 5, 블렌딩 α=0.5 | follower:3777–3778; max_nash_iter=10 yaml:211 |
| N_P dual (λ_P) | gain 0.01, cap 10, 후보별 λ̂ 선반영 ON | follower:346–347; state.py:485 |
| N_P primal-dual 반복 (방법 A) | K=4 (`NP_PD_ITER=4`), gain = 0.01×25 = 0.25 | state.py:497, 500; runner:756–758; follower:3884–3906 |
| r̂ 편향 보정 | ON (`NP_BIAS=1`) | state.py:489, runner:734–736 |
| metering 이동 한계 (METER-BOX) | m_prev ± 300 veh/h, 박스 내 등간격 5점 {−R, −R/2, 0, +R/2, +R} | state.py:379, runner:566–569, follower:2422–2438 |
| VSL 이동 한계 (VSL-BOX) | 직전 step commit 앵커 ± 10 km/h (=vsl_set 격자 1칸) | state.py:387, runner:573–575, follower:2396–2403 |
| green 이동 한계 | 가격 trust ± 6 s (기준점 = 가격 측정 운영점 p1_ref) | sw:53, 62; follower:791–799 |
| leader rollout 다중스텝 도달 (BOX-WALK / -VG) | ON / ON — rollout 2번째 interval부터 metering을 intent 방향 ±R/스텝 전진, VSL·green은 끝 지속(edge persistence) | state.py:391, 395; runner:576–581; smpc:2299–2310 |
| 예산 회랑 | Σmeter ≤ budget (부등식) + 하한 α·budget; α_max=0.65, 부하 적응형(본선 ρ/ρ_crit ≤ c_lo=0.7이면 α=0, c_hi=1.0에서 α_max) | follower:286, 290, 293–295, 2744–2752 |
| N_UF 조정 모드 | equality (budget 사영; 회랑이 하한 제공) | state.py:519, yaml:224 |
| 가격 FD 폭 — metering | δ=300 veh/h, trust_frac=0.20 (FD폭 d_r = max(δ, 0.20×1500) = 300; 짝으로만 유효) | runner:276–287; sw:75, 83, 1219–1223, 1308–1317 |
| 가격 FD 폭 — green | δ=6 s (trust와 동일 폭) | sw:53, 62 |
| 가격 FD 폭 — VSL | δ=10 km/h (trust 없음 — VSL-BOX가 이동 구속) | sw:94, 100 |
| 가격 rollout 깊이 | horizon+1 = 4 스텝 | sw:1814 |
| cross 가격 2종 (g×o, v×m) | OFF (2026-07-16 동결; `CROSS_OFF=1`로 명시 고정) | runner:267–274, 661–667 |
| far(MFD tail) terminal | ON, state-aware(ρ·유효차선 유도), weight 1.0 (`FAR_STATE_AWARE=1`) | state.py:346–352; runner:548–555 |
| player 분해 (SEG13) | freeway를 세그먼트당 1 agent로 분해 — 8-seg 망에서 16 freeway + 5 urban = 21 player (명칭 'SEG13'은 4-seg 시절 5+8=13 유래) | follower:242–247; segment_local_plant.py:52–68; runner:691–706 |
| 안전망 | regret guard k=3 (실현>예측×1.10이면 k스텝 incumbent 강제); fallback guard = rollout-TTT 비교; β̂ 추정기 ON(진단 전용); leader hinge OFF | state.py:451, 459, 465, 507 |
| leader setpoint 범위 | N_P* ∈ [−3500, 3500] veh, N_UF* ∈ [0, 6000] veh/h; N_P_crit = 1142.058 veh (MFD argmax 재보정 2026-06-30) | state.py:540–541; yaml:281–290 |

## 기준선 구성 (각 1행)

| 컨트롤러 | 구성·구별 설정 | 출처 |
|---|---|---|
| NC | `baseline_control("no_control")` — green 56/56 s(=112/2), VSL 100 km/h, ramp 전량 방류, offset 0, allocation 없음 | runner:470–471; state.py:1108–1127 |
| WU-CD-F | `DistributedCoordinator(ablation="WU_GREEN_VSL_ONLY_TTT")`, leader 없음(`solve(state, None, …)`). 권한 = green+VSL만 — metering=용량 고정, offset=0, allocation 비움. Jacobi 반복 ≤ max_nash_iter=10, 수렴 tol 1e-3, under-relaxation α=0.8. 본 논문 이동 한계(±300/±10/±6) 미부과(문헌 충실; VSL 명목 max_vsl_step=20 드리프트 클램프만) | runner:105–106, 476–484; dc:300, 315–319, 346–364, 1837, 1927, 2914, 3026 |
| PFO | `WuFaithfulFollower` 단독(leader=None) — 가격 채널 완전 휴면(None이면 비트동일), 신호별 own-TTS green + freeway own-TTT metering/VSL 자율. env는 `WARMUP_NC_STEPS=20`만. ★SEG13 부여 금지(5배 악화 실측) | runner:107–108; follower:150–158(가격 휴면), 2820–2846(자율 metering); baseline_queue.sh 주석 |
| PFO+box | PFO + `BASELINE_BOX=1` — walk-MVG와 동일 이동 한계: metering prev±300 박스 5점, green prev±6 s(앵커=직전 step commit). VSL 미적용(무제한 PFO의 VSL 이동 실측 0). 플래그 OFF 시 PFO와 비트동일 검증(notes.md §12) | state.py:396–400; runner:582–584; follower:806–810, 1558–1562, 2831–2846 |
| P-CENT | `CentralizedMPC(mode="proposed")` — 전권 joint(green+VSL+offset+metering+게이트 서비스 분율). 실런 솔버 = **centralized structured grid search(coarse→fine, 전권 joint 행동공간), serial(단일 프로세스 직렬)** — 이 런타임에 scipy 부재로 SLSQP 경로 불성립, ImportError 시 structured-grid fallback(실런 진단 `centralized_slsqp_available=0.0`으로 물증 확정). spec 16.13의 "동일 budget centralized numerical reference"이며 연속 NLP 천장이 아님. 이동 한계 의도적 미부과(rate-limit-free 상한 프레이밍, 사용자 결정 2026-07-18; VSL만 명목 max_vsl_step=20 bound) | runner:445–447; cm:59–77(권한), 103–104(VSL bound), 437–501(coarse→fine grid), 554–577(scipy fallback); _paper_pcent run_log 진단 |
