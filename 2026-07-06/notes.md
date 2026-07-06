# 2026-07-06 작업 노트 — F1(안전 페널티의 follower 이관): 구현·분해·w-지도

(선행 문서: reports/price_channel_arc_report_20260706.md, 2026-07-05 notes §12~§14)

## 1. F1 구현 (사본, 원본 무수정 — 사용자 지시)

`src/controllers/f1_wu_faithful_follower.py` 신설(7982984): 세 urban rollout의 F1 사본
(0.5cap spill hinge) + `F1WuFaithfulFollower`(urban은 probe 규약으로 F1 rollout 주입해
부모 로직 재사용, freeway는 `_solve_freeway_agent_local` 사본에 ρ_crit 초과차량 선형
hinge) + `F1StackelbergWuMeteredController`(가격 구성은 기본 B2TR 그대로).
`local_signal_plant.py`/`wu_faithful_follower.py` 원본 무수정. 가중치 0 = 부모 비트동일
(사본 무결성 테스트). 러너 변형: -F1/-F1RHO/-F1RHO05, WU-FAITHFUL-FOLLOWER-F1.

## 2. 7200s 결과 + 분해

| 구성 | sweet_155 | sweet_190 |
|---|---:|---:|
| B2TR(현 기본, hinge 없음) | 4391.8 | 12523.0 |
| F1(spill+ρ, w=1) | 4447.0(+1.26%) | **12158.6(−2.91%, 신기록)** |
| F1RHO(ρ만, w=1) | **4447.0(F1과 비트동일)** | **12158.6(F1과 비트동일)** |
| F1RHO05(ρ만, w=0.5) | **4372.5(−0.44%)** | 12442.2(−0.64%) |

- **sweet_190 신기록**(w=1): legacy 격차 1794→**1430**(−20%). 분해: urban −586 /
  freeway +171 / Σmeter 4848→5001 — ρ hinge가 "절벽만 넘지 마라"의 정확한 경계를
  제공하자 freeway agent가 **절벽 직전까지 자신 있게 방류**해 urban을 구제하는 교환이
  성립(안전이 권한 있는 곳에 있으면 성능도 는다).

## 3. spill hinge 전역 무력 — 위상적 원인 (중요한 구조 발견)

F1RHO == F1 **비트동일**(양 시나리오): spill hinge가 어떤 argmin도 바꾸지 않았다.
원인은 버그가 아니라 위상: 국소 rollout의 s_eff는 **자기 origin 링크만 갱신·이웃
동결**인데, 이 망에서 movement는 항상 하류/타 신호 링크로만 흐른다(2026-07-01 finding
#2의 위상 사실) — **내 green이 채우는 링크는 전부 동결된 이웃**이라 후보 간 페널티
차이가 구조적으로 0.

**함의 — 절벽의 소유 구조가 처방을 결정한다**:

| 절벽 유형 | 소유 구조 | 처방 | 실증 |
|---|---|---|---|
| freeway ρ_crit | 자기 레버가 자기 절벽 통제 | **follower own-objective hinge** | F1RHO 190 −2.91% |
| urban spillback | cross-agent(보내는 쪽은 못 보고, 받는 쪽은 못 막음) | **leader 제약 채널(N_P + λ 적분)** | 기존 구조가 이미 정답 |
| 완만 조정 | — | 가격 + trust | B2TR |

F1의 urban 항은 이관 불가(위상적 무력)이자 불필요(N_P가 담당) — 사용자 제안의 freeway
반쪽이 정확히 적중했고, urban 반쪽은 "왜 안 되는가"의 구조적 이유를 밝혀냈다.

## 4. ρ hinge w-지도 (hinge는 가격이 아니라 마진 항 — w는 정당한 노브)

155: w=0→4391.8, **0.5→4372.5(최선)**, 1.0→4447.0 (비단조, 최적 0.25~0.75 사이).
190: w에 단조 개선(마진 가치는 절벽 근접도에 비례 — 원리적으로 자연).

- **w=0.5 = STOP-clean 승격 후보**: 측정된 두 시나리오 모두에서 현 기본(B2TR) 대비 개선.
- **w=1.0 = 190 특화 opt-in**: 최대 이득(−2.91%), 155 비용(+1.26%).
- sweet_128 실사(F1RHO05) 진행 중 → §5에 추가 예정.

## 5. sweet_128 실사 + 최종 표

F1RHO05 sweet_128 = **1530.360, B2TR과 비트 동일**(경부하에선 본선이 임계 근처에 안 가
hinge 무발화 — 위험 0의 이상적 실사 결과).

| 7200s | sweet_128 | sweet_155 | sweet_190 |
|---|---:|---:|---:|
| B2TR(현 기본) | 1530.4 | 4391.8 | 12523.0 |
| **F1RHO05(w=0.5)** | **1530.4(동일)** | **4372.5(−0.44%)** | **12442.2(−0.64%)** |
| F1RHO(w=1.0) | (무발화→동일) | 4447.0(+1.26%) | **12158.6(−2.91%)** |

**F1RHO05는 B2TR을 약우월(weakly dominate)** — 전 시나리오 STOP-clean.

## 6. F2·F3 판정 (sweet_190 7200s, 기준 F1RHO 12158.6)

**F2(metering 가격 + hinge 방어) = 음성**: 19074.1 — B3CERT와 동일 붕괴(freeway 5607,
Σmeter 5411). 같은 hinge로 등식 budget이면 신기록(F1RHO 5001)인데 가격이면 붕괴 —
**차이는 hinge가 아니라 권한(07-05 §14)**: 가격 모드의 soft budget이 leader 권한을 끊고,
follower 국소 onset 창은 좁으며 거기서 절벽-맹인 가격이 hinge와 싸우고, jam 후엔 국소
hinge도 후보 불변(3국면의 국소판). **metering 가격 = 4구성(B3/TR/CERT/F2) 전패, 영구
아카이브.** metering 조정 최종 = leader 등식/ceiling + hinge-informed 응답(F1RHO).

**F3(offset per-signal 가격) = 무효(null)**: 12158.622 — F1RHO와 비트 동일, 커밋 offset
0/120. 이중 무효화: (i) **leader의 offset 한계가치 ≈ 0**(전 신호·전 step 0.0000 — 신호
하나의 ±14s는 9분 전역 TTT를 안 움직임), (ii) 가격 0이라 탐색이 selfish로 퇴화(103회
비영 제안) → corridor 가드가 전부 기각(2026-06-29 판정의 가드 작동). **기전: offset은
joint 결합 변수** — green wave 가치는 여러 신호의 offset이 함께 맞을 때 생기고 단독
이동의 편미분은 ~0. per-signal 가격(편미분)은 구조적으로 결합 패턴을 발견 불가. legacy가
offset을 쓴 것은 전역 응답의 통째 평가(joint) 덕분.

**조정 수단 분류 최종판**:

| 레버 | 성질 | 정답 수단 | 실증 |
|---|---|---|---|
| green | 완만·가역·개별 | 가격+trust | B2TR(3 regime 개선) |
| metering | 절벽·비가역 | leader 등식 + hinge-informed 응답 | F1RHO(190 신기록) |
| offset | **joint 결합** | per-signal 가격 불가 — 패턴 수준 조정 필요(미해결) | F3 null |
| urban spillback | cross-agent | N_P 제약 채널 | F1 분해 |

### 6.1 보강 해석 — per-actuator price의 한계와 joint response

F2/F3 판정은 "metering은 hard constraint만 가능" 또는 "offset은 무가치"라는 의미가 아니다.
legacy가 성능을 냈던 구조는 `rho_crit`을 절대 제약으로 둔 것이 아니라, RM/VSL/green/offset
후보를 더 joint하게 rollout해 **일시적 밀도 초과, ramp/urban queue relief, throughput 증가**의
교환을 직접 평가했다는 쪽에 가깝다.

따라서 F2 음성의 더 정확한 해석은: metering의 한계가치는 VSL과 함께 정의되는 freeway
bottleneck-level joint value인데, 이를 ramp별 1차 scalar price로 투영하면서 RM-VSL의
대체/보완 관계(cross term)를 잃었다는 것이다. 마찬가지로 F3의 offset null은 offset이
무의미해서가 아니라, green split과 여러 신호 offset이 함께 맞을 때만 progression 가치가
나오는 **joint corridor variable**을 per-signal 편미분으로 본 결과다.

다음 설계 원칙:

| 묶음 | 권장 response 단위 | 이유 |
|---|---|---|
| RM + VSL | bottleneck-level `(RM, VSL)` joint candidate 또는 shadow price | 둘 다 유효 유입/충격파를 조절하지만 ramp queue와 mainline speed 부작용이 달라 cross term 필요 |
| green + offset | corridor-level `(green, offset)` phase pattern 후보 | green은 서비스량, offset은 서비스 시점 — progression은 결합 패턴에서 발생 |

즉 현재 결론은 "가격 채널 폐기"가 아니라 **단독·완만 레버(green)는 B2TR scalar price,
결합 레버(RM/VSL, green/offset)는 joint candidate-level response**로 분류하는 쪽이 더 안전하다.

## 7. TODO
- [ ] **기본값 전환 여부 = 사용자 결정 대기**(원본 무수정 유지 중). 메뉴: (a) F1RHO05
  기본(약우월) + -F1RHO(w=1) opt-in, (b) 현상 유지(B2TR), (c) w=0.75 knee 후 결정.
- [ ] **offset의 남은 길 = joint/패턴 조정**: per-signal 가격이 아니라 leader가 corridor
  위상 패턴(예: A·C 동시 offset 조합 후보)을 직접 후보 평가 — legacy식 joint 평가의
  저렴판. 잔여 legacy 격차(F1RHO 기준 1430)의 유력 재료이나 별도 설계 필요.
- [ ] 러너 -F2/-F3/-F23은 기록용 보존(전부 음성/무효 판정).

---

# 이하 Claude 세션 (2026-07-06 후반) — 개념·전략 종합 (코드 변경 없음, 방향 확정)

가격 채널 아크 종결 후, cost·trust·horizon·value·전략 논의를 종합. 실험 없이 개념 정리 +
기여 프레이밍 확정. 다음 세션이 재유도 없이 집도록 남김.

## 8. Cost 분석 — B2는 legacy와 같은 order(~2배 쌈), 주범은 follower 아닌 leader

- 실측/추정(sweet_190 7200s): PFO(leader 없음) ~4s/step, **B2 전체 decide ~44s/step**(follower
  3s + leader ~41s), **legacy 96s/step**. → B2는 legacy 대비 **~2배 쌈, 그러나 같은 order**.
  TTT는 legacy가 더 좋음(10729 < 12523). 즉 현 B2 = **"조금 싸고 성능은 나쁨"** — raw로는 어느
  축도 압도 못 함. 사용자 지적 정당.
- **비용 주범 = leader의 전역 rollout**(candidate search + price FD), follower는 진짜 쌈(분산).
  legacy든 B2든 "leader가 전역 rollout"이 지배적이라 같은 order가 됨.
- **점근 차별점(진짜 가치)**: legacy = O(후보수 × 전역), B2 price FD = **O(신호수) 고정**. 큰
  네트워크·고해상도서 B2가 이김. 지금 규모선 비슷. → cost 우위 주장은 **점근/확장성**으로.

## 9. Trust region 재조명 — successive linearization + 보폭 문제 + 3축 정당화

- 사용자 통찰: "이웃 밖 최적이면 경계서 재측정" = **successive linearization(trust-region SQP)**.
  현 B2TR이 이미 **control step을 건너서** 그렇게 함(event-trigger가 새 운영점서 재측정). trust
  region은 재측정을 *막는* 게 아니라 **각 스텝을 안전하게(한 이웃씩) 만드는 짝**.
- **핵심 정정**: 폭주는 "얼마나 멀리 계산"이 아니라 **"한 step에 commit하는 보폭"** 문제.
  receding: 9분 horizon이라도 **3분마다 첫 interval만 commit** → plant가 매 3분 검증. 무제한 B2가
  폭주한 건 한 step 보폭이 커서(선형 월권, 155서 68→86 18s 점프) plant 검증이 못 따라잡아서.
  trust = 보폭 제한 = plant가 매 step 따라잡게. 사용자 결론: **traffic 통념(신호 급변 금지)과
  정렬되므로 보폭 제한이 맞다.**
- **trust region 3축 정당화(논문용)**: 같은 δ가 (1) 선형 가격 유효반경(수학), (2) 신호 rate
  제약 |Δg|≤Δg_max(공학 통념), (3) 분산 결합 안정성(게임이론)에서 동시 수렴. "세 근거가 한
  δ로 만난다"는 강한 서사.

## 10. Horizon 확장 — 선형 비용, green엔 무익, 단 metering엔 다름(재개방)

- 9분→15분 = 3→5 interval = rollout당 **~1.67배**(선형, 폭발 아님). B2 44→~73s/step → legacy(96s)
  대비 2.2배 우위가 **1.3배로 축소**. cost 관점 불리.
- **green**: §7(07-05)서 폭주점의 h=3 gradient 이미 옳음 → horizon 문제 아님, 확장 무익.
  장기비용 걱정이면 확장 말고 **terminal cost**가 싼 레버.
- **metering은 다름(중요)**: 절벽 breakdown이 **지연**(누적 ~30분)이라 horizon에 진짜 민감.
  9분에선 막을 수 있는 순간(절벽 전) breakdown이 창 밖 → 눈멂. **긴 horizon + metering 가격은
  실패한 5구성(9분)에 없음** → 미검증. 단 caveat: secant-across-불연속(부호만 맞고 크기 노이즈),
  ~3.3배 비용, own-TTS 방류 유인, trust-walk도 절벽 넘음. 깨끗한 해법 아니나 "9분이 죽였나"는
  기록이 안 닫은 물음.

## 11. Metering 가격 왜 눈머나 — 미분 vs 값, 지연이 살인범

- 가격 = raw TTT 아니라 **레버에 대한 기울기(미분)**. 롤아웃은 jam을 값으로 보지만, 가격은 그
  값의 접선을 떼 내려주는데 **절벽서 3국면 전부 무의미**: 절벽 전=약함(±δ가 절벽 못 닿음,
  boiling frog), 절벽 위=쓰레기(불연속 secant, 부호반전 −0.447), 절벽 후=0(jam 포화, 평평).
- **비유**: 안개 절벽 — 평지 기울기 ~0("안전"), 끝에선 정의불가, 떨어진 뒤 또 0. 기울기만
  보고 걸으면 떨어짐. 고도 지도(value)를 알아야 안 떨어짐.
- **지연이 핵심 살인범**(사용자 진단, 정당): 막을 수 있는 순간(절벽 전)엔 breakdown이 9분 밖 →
  안 보임. 보이는 순간(절벽 위)엔 이미 넘음 → 미분 쓰레기 + 비가역. **즉각적이면 ±δ가 절벽
  가로질러 잡힘** — 지연이 없으면 가격화됨. 지연(누적 원인)이 갭을 만듦.
- **고차식(2차)도 절벽엔 무력**: Taylor는 매끄러운 국소 도구, 절벽은 문턱(비국소·비다항식).
  ±δ probe 밖 문턱은 몇 차든 못 봄(창을 넓히는 게 아니라 창 안을 다듬음). 절벽 위선 2차가
  오히려 악화(뒤집힌 포물선→경계로 더 빨리). **"고차식으로 문턱 잡기"의 극한 = 제약**(=F1RHO
  N_UF ceiling, §12 퇴화 정리와 일치). 단 **green(매끄러움)엔 2차 가격 유효**(Newton·자기정지,
  미시도 카드).

## 12. Value function/ADP — parked 다음 스텝, 그러나 짓지 않음

- 개념: 가격(∇V, 기울기)이 아니라 **V(값) 자체**를 하달. follower가 "결과 상태"를 V로 채점 →
  레버 독립(green/offset/metering 통일), 비볼록·절벽·근시를 값 차원서 우회.
- **제어이론 프레임**: 가격 g_ext = **costate/adjoint = ∇V**(Pontryagin/PMP). value = **V(Bellman/
  DP)**. 우리는 PMP식 adjoint 조정을 해왔고 Bellman이 대안. 절벽서 가격 죽고 value 사는 이유를
  이 이분법이 예언(adjoint 국소1차 vs Bellman 전역).
- **비용**: value는 비용을 **online→offline**으로 이동. V가 **분해(구역별+경계)되면** online 저렴
  (함수 조회)·legacy 우위. **안 분해되면 legacy 비용 회귀**(사용자 직감 맞는 지점). → **관문
  질문 = "이 망서 V가 구역별로 분해되나"**(VDN/QMIX·MFG에서 빌림).
- **general 함정**: **legacy 해로 fit한 V = 비general(기생), 폐기.** 단 terminal cost 자체는 legacy
  의존 아님 — 출처가 marginal과 같은 leader 모델 rollout. 자기 위로 오르려면 **policy iteration(ADP,
  모델만으로)**, legacy는 벤치마크로 강등.

## 13. **전략 확정 — price-based externality를 기여로, value/RL은 회귀 위험이라 안 감**

- **결정**: value function 시스템을 지어 SOTA RL과 성능 경쟁 → **포화·열세 시장 회귀 위험**. 안 감.
  value는 **"1차 가격이 못 넘는 경계 너머 = Bellman/DP"** 로 **이론적 지목만**(HJI/MFG/max-pressure
  인용), 짓지 않음.
- **기여의 정체 = 조정의 지도**(컨트롤러가 아님): 언제 가격으로 되고(볼록·가역=green), 언제
  제약으로 퇴화하고(절벽·비가역=metering), 언제 원리적으로 1차 분산 조정이 못 닿나(joint=offset).
  RL-for-traffic 문헌에 **없는** 특성화.
- **왕관 이론 = Weitzman "Prices vs. Quantities"(1974)**: green=price instrument, metering=quantity
  instrument가 **곡률·가역성이 결정하는 Weitzman 경계**의 제어이론적 실현. + Pontryagin/Bellman
  이분법. → 얕은 실험이 아니라 깊은 이론.
- **리뷰어 방어 3가드(반드시)**:
  1. Weitzman·Pontryagin/Bellman을 **전면 이론**으로.
  2. **congestion/road pricing과 명시 구별** — 그건 수요/운전자 가격(60년 됨), 우리는 **제어
     행동의 externality를 agent 간 coordination signal로**(액추에이터 가격). "controller-externality".
  3. **centralized 대비 = Pareto(비용/확장/해석), 성능 우위 주장 금지**(legacy TTT가 더 좋음:
     10729<12523). **decentralized(PFO 13627) 대비는 ~8% 성능 개선 = 당당히 주장.**
- 격차 수치(sweet_190 7200s): PFO 13627 > B2-OFF 12790 > **B2TR 12523** > F1RHO 12158 ≫ legacy
  10729. 잔여 격차(~1430-1794) = **1차 분산 조정이 회수 못 한 joint 몫**(value/DP 영역, 지목만).

## 14. Contribution statement 초안 (§13 기반)

> 혼합 urban-freeway 네트워크의 분산 Stackelberg MPC에서, leader가 각 분산 follower에게
> **제어 행동의 전역 externality를 Pigouvian marginal price(g_ext = 전역한계 − 자기한계)로
> 하달**하는 조정 원리를 제시한다. 이 1차 가격이 **볼록·가역 레버(신호 green split)에선 분산
> 조정을 중앙에 근접**시키나(무부하/중부하/고부하 3 regime 개선, 순수 분산 대비 ~8%),
> **절벽·비가역 레버(ramp metering)에선 제약으로 퇴화**하고(Weitzman prices-vs-quantities의
> 제어이론적 실현), **joint 결합 변수(offset)에선 편미분이 구조적으로 결합 패턴을 못 봄**을
> 이론(Pontryagin adjoint=∇V의 한계)과 실험으로 특성화한다. 중앙(joint) 대비 성능이 아니라
> **비용·확장성(O(신호) vs O(후보))·해석가능성의 Pareto 개선**으로, 1차 분산 조정이 회수
> 가능한 조정 가치의 경계를 규명한다.

## 15. TODO (다음)
- [ ] 위 contribution statement를 논문 §1/§요약으로 다듬기(3가드 반영).
- [ ] Weitzman·Pontryagin/Bellman·max-pressure·MFG 관련문헌 정식 인용 정리.
- [ ] (parked) value/ADP: "V가 구역별 분해되나" 5분 진단 — 열면 별도 트랙, 짓기 전 관문.
- [ ] green 2차 가격(Newton·자기정지) 미시도 카드 — 곡률 부호·잡음 probe 먼저.

## 16. Legacy 격차 실측 분해 (별도 리포트) — 희생 아님, 방류+joint offset

`reports/legacy_gap_decomposition_20260706.md` 참조. 핵심:
- **plant 동일성 확정**: legacy 현재 HEAD 재실행 = Jul-3과 비트 동일(10728.8), 비교 유효.
- **격차(2162)는 전량 urban, freeway 동률(1527 vs 1552)** → **beyond-cliff 희생 해 아님(Route 1 폐기).**
- **Step 1 방류 lever**: N_UF 강제↑(4848→5176) → 총 −650(30%), urban·freeway 동시 개선, 556s≪legacy.
  under-release 원인 = leader 9분 horizon이 방류의 장기 urban 배수 이득 못 봄 → **urban 압력 신호**로 일반화 가능.
- **Step 2 offset 국소**: −158(7%, freeway 악화) → **per-signal offset 불충분(F3 가격+국소 best-response 둘 다 실패)** = **joint 변수 재확증.**
- **Step 3(진행 중)**: legacy offset 오라클 주입+N_UF 강제로 "나머지 63%=joint offset" 확정 예정.
- 다음: (1) 방류=urban 압력 leader 신호(일반화), (2) offset=corridor joint 값싼 근사(미해결 핵심).

---

# 이하 Claude 세션 (2026-07-06 야간) — offset 격차의 층위 분리: D/F 레버 활성화(G1)

## 17. offset externality 전파 진단 → D/F offset 활성화(G1) = 신기록

**진단(사용자 질문 "plant/local이 offset externality를 전파하나" 대응, scratchpad
corridor_graph_check / offset_propagation_diag):**
- **plant는 offset externality를 모델링함**(urban_queue_model.py:933,966 — offset-aware
  discharge → 시간분해 arrival_buffer → 하류 서비스). 확인: A offset 스윕이 전역 TTT를
  움직임(단, 방향 일관·크기 미미).
- **plant offset 민감도(step24 horizon TTT range)**: **F=10.7 ≫ C 1.56 > D 0.81 > A 0.30
  > B 0.12.** 가장 큰 offset 레버 2개(F,D)가 **ramp 신호**.
- **그런데 ramp 신호 offset은 `_solve_offset_local`에서 offset=0 고정**(has_ramps 가드,
  "storage 동역학 복잡" 단순화)이었다. legacy는 D/F offset을 std 44/35로 씀 → **격차의
  유력한 몫 = 꺼져 있던 D/F offset 레버.**
- corridor 그래프(=_upstream_leaving_map, 물리 토폴로지 유도)는 **완전 연결 메시**(A↔B,
  B↔C, C↔F, A→D, D→A) — 엣지 누락 아님. 전파 코드도 작동(B→C peak 이동 실증). 그래서
  처방은 "이웃 전파 추가"가 아니라 "**D/F offset 레버 켜기**"였다.

**구현(G1, 커밋 6ae775c)**: `_solve_offset_local_ramp` — ramp-aware phased rollout(P1.5
use_phased_ramp 경로 재사용, frozen ramp 입력 구성)로 ramp 신호 offset 탐색.
`ramp_offset_enabled` 플래그(기본 False=비트동일). offset 블록 게이트에 추가 + ramp-only
격리 모드. corridor 가드(realized horizon TTT) 최종 검증자 유지. 러너 G1DF(D/F만)/
G1ALL(전 신호). F1RHO base. 테스트 24/24(신규 test_ramp_offset 3건).

**결과(sweet_190 7200s) — D/F offset은 켜기만 하면 이득, A/B/C는 selfish라 해로움:**

| 구성 | total | urban / freeway | 완료 | 잔존 | legacy 격차 |
|---|---:|---|---:|---:|---:|
| legacy | 10728.8 | 9201 / 1527 | — | — | — |
| **G1DF (D/F offset만)** | **11872.9** | **10258 / 1615** | **32023** | **12963** | **1144** |
| F1RHO (offset 없음) | 12158.6 | 10527 / 1631 | 31480 | 13549 | 1430 |
| G1ALL (전 신호 offset) | 12638.0 | 11095 / 1543 | 30991 | 14042 | 1909 |

- **G1DF = 신기록.** F1RHO 대비 **−285.7(−2.35%)**, legacy 격차 1430→1144(**−20%**).
  개선 거의 전량 urban(−269 / freeway −16) — offset=urban 레버 진단 적중. 완료 +543/
  잔존 −586.
- **G1ALL(전 신호) = F1RHO보다 +479 악화** — A/B/C offset을 selfish 국소로 얹으면
  corridor de-coordinate(2026-06-29 finding + Codex Step 2 재확증). **offset 격차는 두 층위**:
  (a) **D/F = self-contained 레버, 활성화만으로 회수(우리 몫)**, (b) **A/B/C = corridor
  좌표 문제, selfish 국소는 해로움(Codex 패턴 레인)**. 우리·Codex 작업 경계가 데이터로 선명.
- **관찰(후속 여지)**: G1DF에서 D/F offset이 40 step 중 **3번만** 비영 커밋(가드가 나머지
  되돌림)인데도 −285.7 회수 → 가드 마진(0.5%)이 보수적, 완화 시 추가 여지 가능성.
- **다음**: G1DF 155/128 교차검증(진행 중), 가드 완화 스윕, D/F offset을 leader 좌표
  신호로 승격(격차의 D/F 몫을 일반화).

### 17.1 G1DF 3-시나리오 교차검증 — **전부 신기록(회귀 없는 순수 개선)**

| 7200s | sweet_128 | sweet_155 | sweet_190 |
|---|---:|---:|---:|
| B2TR(기존 기본) | 1530.4 | 4391.8 | 12523.0 |
| F1RHO05 | 1530.4 | 4372.5 | 12442.2 |
| F1RHO | 1530.4 | 4447.0 | 12158.6 |
| **G1DF(D/F offset)** | **1510.5** | **4267.9** | **11872.9** |

- **G1DF가 전 열에서 이전 최선을 이김**: 128 −1.30% / 155 −2.39%(vs F1RHO05) / 190
  −2.35%(vs F1RHO). STOP-clean, 회귀 0. 이 아크 최강 단일 결과이자 legacy 격차를 한 번에
  가장 크게(190: 1430→1144) 좁힌 스텝.
- **새 배포 후보 = G1DF**(F1RHO의 ρ_crit hinge + D/F offset). 원본 무수정·플래그 게이트라
  기본값 전환은 여전히 사용자 결정(현 기본 B2TR 유지 중).
- 함의: legacy 격차(§16 분해)의 세 몫 중 (a)방류=Codex 트랙, (b)A/B/C corridor joint=
  Codex 트랙, **(c)D/F offset 레버=본 세션이 회수**. 격차 정복 지도의 한 칸이 채워짐.
