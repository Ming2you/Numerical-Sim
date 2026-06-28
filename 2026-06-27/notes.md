# 2026-06-27 작업노트 — 경량 follower 재설계 시도와 결론

## 한 일
1. **전제 오해 규명**: WU-CD-F는 `DistributedCoordinator(ablation="WU_GREEN_VSL_ONLY_TTT")`(중량 full-coupled)였고,
   경량 `WuDistributedController`가 아님(six_controller_comparison.py:51). "WU-CD-F=Wu분해"는 오해.
2. **경량 WuDistributedController가 56/56 무력인 이유**: `_solve_urban_agent`의 집계 국소모델이
   phase를 큐 하나로 보고 균일 sat 사용 → 대칭 sat·고수요 포화에서 throughput이 green-split에 무관 →
   목적함수 평평 → smoothness가 split을 prev=total/2=56에 고정. **이론 아니고 모델이 거칠어서.**
3. **새 follower 재설계 시도(`wu_style_follower.py`)** — 후보를 실제 plant로 국소 채점:
   - (a) spillback cap 추가: 56/56 그대로(0%). cap 안 binding(avail 833 >> discharge 196).
   - (b) urban-only `urban_step` 채점: D/F 탈출(62/67), A/B/C 56 고정, **개선 −0.5%**(T=720).
     freeway 결합 가치 상실 → 중심신호 무동작. ~2.2× 빠르나 품질 붕괴.
   - (c) full-coupled `run_coupled_interval` 채점 + per-signal 가법후보: **n=7 속도이득 0**
     (8min/T=360 = 원본 동급). 후보수 225 vs DC 300이나 per-eval 동일 + leader ×24.

## 결론
- follower 가치는 **결합(urban↔freeway)** 에 있어 결합 빼고 채점 → 가치 상실.
- **n=7은 너무 작아 분해 O(n)가 joint 상수항을 못 이김.** 분해이득은 점근적(큰 n);
  이미 theory scaling 그림이 그 서사 담당. 실측 n=7 follower 분해는 속도이득 없음.
- **n=7 실제 속도 lever는 follower가 아니라 leader**: 후보마다 full follower 24× 호출이 비용원
  (WU-CD-F=follower단독 82s vs P-STACK 1964s). leader 평가 캐싱/coarse 사전필터/warm-start가 다음 후보.

## TODO (다음)
- [ ] leader candidate 평가 비용 절감(검증된 23.88% 유지) — 캐싱/coarse/warm-start.
- [ ] 또는 분해 follower는 "큰 n 스케일링 검증" 용도로만 별도 정리(현 코드 보존).
- [ ] 디버그용 스크립트/출력 정리(2026-06-25/diag_scripts/follower_path_compare.py, outputs/*dbg*).

---

# 2026-06-27 (2부) — Wu 충실 per-signal 국소 rollout follower 신규 구현

## 무엇을 만들었나 (새 파일만, 기존 미수정)
- `src/controllers/local_signal_plant.py` — 신호 1개 movement 큐만 N_p×K_cu substep 전진시키는
  Wu f_i 국소 stepper. 이웃 도착(arr)·이웃 downstream S_eff **동결**. service/spillback은
  `urban_substep`(877~964행)을 per-signal 복제. **전체망 plant 호출 0.**
- `src/controllers/wu_faithful_follower.py` — Jacobi(S_max=5, 결합 동결·동시갱신, warm-start) +
  per-signal urban solve + `solve(...)->NashResult`. 결합변수/freeway VSL/토폴로지는 기존
  `WuDistributedController`를 조합 재사용(미수정). leader=None(PFO)만.
- `2026-06-27/run_wu_faithful.py` — run_controller 복제 검증 러너.

## 1부 결론과의 차이 (왜 이번엔 진짜 local)
1부 (b)는 `urban_step`(전체 5신호 전진), (c)는 `run_coupled_interval`(전체망)으로 채점 → 진짜
local 아님 + global TTT. 이번 구현은 **신호 i movement 큐만** 전진(이웃 동결) + **자기 TTS만**
목적. urban eval 1.29 ms/eval vs freeway 64.5 ms/eval(~50× 쌈), 전체망 rollout 대비 확연히 저렴.

## 결과 (정직)
- sweet_128(스펙 지정, 경부하): **impr -2.03%**, A/B/C=56, D=68, F=60~68.
- sweet_220(고부하): **impr +0.54%**, 5신호 모두 56 탈출(44~62).
- 진단: per-movement 미포화(게이트 250~500/mv vs 서비스 653/mv)라 경부하에선 split이 큐에
  거의 무관 → 국소 TTS 표면 평평, 56 근처가 실제 최적. 고부하서 split binding → 양전환.
  plant 버그 아님. 국소목적 근시안성(Nash vs social) = leader objective TTT 어긋남 계열.

## deviation
- urban 후보에 green 전범위 13점 sweep 추가(pressure ±5 밴드는 56 못 벗어남, 옛 집계모델용).
  국소 rollout이 싸서 폭발 없음. SPEC §2 argmin 충실 위한 의도적 확장.
- freeway는 SPEC §3 허용대로 기존 VSL solve 차용. leader!=None 미구현.
