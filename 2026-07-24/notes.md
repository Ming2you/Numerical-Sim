# 2026-07-24 작업 노트 — granularity·감독자·box-walk 최적 flagship 탐색

## 배경
GPT 지적("P-Stack 이득이 follower 수 때문 아님을 증명하라")에서 출발. P-Stack(21) vs PFO(2/4) granularity 조사 → leader·감독자·box-walk까지 분해.

## 오늘 한 것
1. **P-Stack(4) 5셀 완료** (leader + 4 지역 freeway agent + PFO_SPLIT=2). b13(P-Stack21)와 비교.
2. **b13 − P-Stack(4) 차이 = 3축** 정확히 규명: ①granularity(SEG13 21 vs PFO_SPLIT 9) ②leader rollout box-walk ③감독자(SUP_PFO). follower 스텝 이동한계는 BASELINE_BOX로 동일(내 이전 "segment box 차이" 정정).
3. **LINK_BOX_WALK 구현** (stackelberg_mpc.py:2406 meter ±300 / 2437 VSL ±15 fallback, env-gated). green은 F1 metered 컨트롤러가 trust 6.0 세팅 → b13와 자동 동형.
4. **감독자 캠페인 중단**(box-walk confound 발견) 후 **box-walk 15런 캠페인**(PS4×{nosup,supF,supA}×5셀) 재실행.

## 핵심 결과
- **★box-walk 무효(가설 기각)**: PS4bw ≡ PS4old 전 5셀 **bit-identical**. 훅 불발 아님(_predict가 채점함수, 후보선택 Δ0.0로 확인). 이유=팔로워가 매스텝 N_UF 목표 realized≈selected(gap≈0)→walk 여지 0. 200_w식 metering 고착 병리 없음. **b13 우위는 box-walk 아니라 granularity**. box-walk는 compute ~2배만 늘림.
- **★최적 flagship**: 셀승수 b13=2(Low·High), PS4bw+supF=1(Med), PS4=1(Skew), PFO4=1(Inc). **어떤 4-agent도 b13 지배 못함**. granularity 트레이드오프 — 거친 4-agent=중간부하(Med −102/Skew −86), 촘촘 21-agent=극단·국소(High +354/Inc +220, PS4bw+supF−b13 기준).
- **★감독자 gating(b11 재현)**: supF=supA가 incident만 빼고 전부 동일. Inc서 supA(always) +334 악화 → always-on은 4-agent서도 기각, fargate가 사고회복 보호.

## 판정
단일 flagship이면 **b13 방어 가능**(hard case High·Low 소유). "중간부하 위주면 4-agent+supF 우위"는 조건부 성립. box-walk는 flagship에 넣지 말 것(순비용).

## 데이터/재현
- 결과표: results/flagship_search_boxwalk.txt
- 코드: modified_code/stackelberg_mpc.py (LINK_BOX_WALK), launch_pstack4_boxwalk.sh, analyze_flagship_search.py
- 폴더: outputs/_diag/pstack4bw_* / pstack4bwsupF_* / pstack4bwsupA_*
- 시뮬 python=codex-runtime, 분석=anaconda3(pandas)+UTF8=1

## TODO
- 논문: granularity ablation 표(비단조 트레이드오프) = GPT 반박 + 리치 스토리. box-walk 무효는 각주/부록.
- (보류) landscape multi-step 탐색(candidate heatmap 평평 문제).

## ★다음 세션 (사용자 지시, 자율 재설계)
- **[NEXT_TASK_pstack4_autonomous_redesign.md](NEXT_TASK_pstack4_autonomous_redesign.md)** 참조 — 서브에이전트 3종(원인검증/설계/구현)으로 P-Stack(4) objective 재설계, 사본에서, PFO를 5셀 전부 이길 때까지.
- 이 세션 추가 발견(NEXT_TASK에 상세): P-CENT=valid oracle(전셀 PFO이상, 차이=freeway/urban 균형·램프차등 아님); b13=PFO와 경쟁적(Low/High승); far/hinge/box-walk/감독자/anchor 다 부분·무효; 원인=leader objective 평평(near-tie Δ0.8 vs 실제329)로 과-metering(inc)·green오조정(high). far-split 30런 진행중(bmbj3vo9k).
