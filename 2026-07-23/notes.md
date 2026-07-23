# 2026-07-23 작업 노트

## 무엇을 했나
- 가격(marginal-externality price) 4채널 전체(green/metering/VSL/offset)의 TTT 기여를 격리하는 ablation 실험.
- 방법: `ALLPRICE_OFF=1`(4채널 전부 off, budget만) 닫힌루프 + `PRICE_CF=1`(가격 ON 유지하되 매 스텝 "가격 없었으면 골랐을 lever" 반사실 기록).
- 5셀: Low(155)/Medium(170)/Med-Skew(170skew)/Med-Incident(170inc)/High(190).

## 핵심 결과 (→ 논문 TABLE 4)
가격 제거 시 TTT 변화 (ΔTTT = OFF−ON, veh·h):
- Low −16 (−0.5%), Medium +337 (+8.8%), Med-Skew +166 (+4.2%), Med-Incident +1 (+0.0%), High +568 (+9.9%).
- 결론: 가격은 화장품 아님. 지속 혼잡(Med/Skew/High)에서 +4~10% 기여, 사고는 중립, 경부하는 살짝 해로움.

## 왜 incident만 0%인가 (검증됨, "더 신기한" 발견)
- 사고(seg6 완전 차선폐쇄, capdrop=1.00, t1980~3600s)가 freeway 배출용량을 **외생 고정**.
- 데이터: 사고 중 `mainline_exit_flow_total`이 ON/OFF 거의 동일(±2%) → 총 처리량 불변 → 총 TTT 핀 고정.
- 가격은 놀지 않음: metering 더 조여 freeway TTT −212, urban TTT +212로 정확히 상쇄(제로섬).
- **경계조건**: 가격 가치 = "컨트롤러가 처리량을 바꾸느냐(예방가능 혼잡→가격 유효)" vs "배분만 바꾸느냐(강제 병목→중립)".

## 버그/이슈
- `PRICE_CF` 반사실 솔브가 솔버 내부 warm-start 상태를 흘려 **cf_190만 오염**(+11%, 6366 vs base 5734).
  → TABLE 4의 190 ON은 base_190(clean) 사용. 나머지 4셀은 cf≈base라 무관.
  → TODO: 반사실 솔브 전 솔버 clone하거나 내부상태 snapshot/restore로 누수 차단(190 per-step 깨끗이 원하면).

## 산출물
- results/price_ablation_table.tex (LaTeX booktabs, TABLE 4)
- results/price_ablation_table.tsv (Word 붙여넣기용)
- results/price_ablation_caption.md (캡션 + 본문 문단 + 근거 데이터)
- 원자료: outputs/_diag/{cf,alloff}_{155,170,170skew,170inc,190}/, 분석 outputs/_diag/cf_analysis.py

## TODO
- 논문에 TABLE 4 삽입 + 해설 문단.
- (선택) cf_190 반사실 상태누수 고쳐 재실행 → 190 per-step lever 궤적 clean.
- table3 compute-cost의 CAND25 오라벨 정정(→ CAND49 또는 bias15).

---

# VSL 마찰(smoothness) 감사 + vsl_smoothness_weight 0.1→0 확정

## 배경/질문
- 기존 결과에서 VSL이 cooldown congestion 회복 후에도 115로 안 돌아가고 100에 고착.
- 사용자 질문: metering 마찰 0.1이 단위상 과대한 것 아닌가(veh/h에 곱해지니).

## 감사 결과 (독립 워크플로우 CONFIRMED)
- 플래그십(P-STACK-WU-FAITHFUL=F1WuFaithfulFollower)의 활성 마찰은 **VSL·green 2종뿐**.
- metering 마찰은 `freeway_follower.py:604`·`distributed_coordinator.py:2433`(PFO/분산)에만, 플래그십 미적용.
  → `NO_FRICTION=1`의 metering·offset=0 세팅은 플래그십에서 **dead assignment**.
- 사용자 단위 지적은 물리적으로 옳음(base_190 측정 metering|Δ|=177.8veh/h vs VSL 0.625km/h, 0.1 공유 시 285×)
  — 단 그 경로(PFO/분산)에만 해당, 플래그십 무관.

## VSL 마찰 스윕 + 분해 (5셀 155/170/170skew/170inc/190, VSL만 조정·green 0.1 고정)
- **회복 임계 weight = 0.005~0.02 사이**: 0.005·0은 5셀 전부 115 회복, 0.02~0.1은 대부분 100 고착.
- **순수 VSL 효과**(VSL0·green0.1 − base): 전 셀 TTT **−3~−41 개선**(평균 −23). cooldown 115 복귀로 통행시간↓.
  → 마찰 0.1이 작은 실이득을 막고 있었음(cosmetic 아님).
- **순수 green 효과**(all-off − VSL0): 170 +323 / 170inc +275 / 190 +437 손해 → NO_FRICTION 파국은 green 탓.

## 변경
- `src/config/default.yaml` freeway_follower.vsl_smoothness_weight 0.1→**0.0** (green/metering 0.1 유지)
- `src/models/state.py:604` FreewayFollowerConfig.vsl_smoothness_weight 0.1→**0.0**
- ★yaml 파서가 인라인 `#` 주석 안 벗김 → 주석은 전체줄로. 실효값 float 0.0 검증(ExperimentConfig.from_file)+스모크 6스텝 완주.

## TODO (중요)
- **본선 그리드 재실행 필요**: default 공유라 baseline(PFO/Cent/Dist)도 VSL 마찰 0(플래그십만 검증). 논문 표 소폭 변동.
- 원자료: outputs/_diag/vslw{000,0005,002,003,004,005}_*, 분석 work/preview_vslw.py·wait_vslw_final.py, 리포트 outputs/_diag/VSLW_*.txt
