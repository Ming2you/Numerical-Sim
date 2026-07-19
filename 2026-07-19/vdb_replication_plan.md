# VdB(2007) 완전 재현 — 자립형 계획서 (분기 트랙, 2026-07-19)

## 목적
Van den Berg et al.(2007) "Integrated traffic control for mixed urban and freeway networks"를
클린룸으로 재현 → Table 1 패턴 검증 → 같은 plant에 P-Stack 이식(문헌-앵커 비교).
본선(cross-gate)과 독립 작업. 원문 PDF: 사용자 Desktop/test/3X3 Toy Network/.

## 성공 기준(사용자 확정 필요, 기본 권장 = 패턴 재현)
Table 1 패턴: 시나리오 1~3 total 개선 2~7%(vs SCOOT/UTOPIA), 시나리오 4(최대 큐 20 제약)서
UTOPIA 폭발(+40% TTS로 준수)·SCOOT 소가중 위반(큐 93)·MPC 저비용 준수(큐 21).
수치 일치는 그림 데이터(turning rate Fig.8, 망 기하) 확보 시에만.

## 구성요소(전부 논문 §2~3에 서술)
1. freeway: destination-independent METANET(Messmer-Papageorgiou 1990). 파라미터(Kotsialos
   1999) = v_free 106 / ρ_crit 33.5 / ρ_max 180 / Q_cap 4000 / τ 18s / ν 65 / κ 40 / a 1.867.
   origin 큐 모델(Eq 3). 속도식 = relaxation+convection+anticipation(merge 마찰항 없음 — 확인됨).
   기존 src/models/metanet.py 코어 함수 재사용 가능(같은 계보, 검증 완료).
2. urban: Kashani & Saridis(1983) 큐 모델 — **목적지 추적** x_{o,s,d}(Eq 6), 포화유량
   Q_cap,osd=1000 veh/h, 차량장 6m, v=50km/h, green 이진 g∈{0,1}.
3. 인터페이스: on/off-ramp 결합(§2.3), T_f=10s / T_u=1s / T_c=120s.
4. 컨트롤러 3종: 중앙 MPC(전 레버 동시 최적화, receding horizon; Np/Nc 수치는 텍스트 추출
   실패 — Hegyi 2004 계보에서 보충하고 출처 명시), SCOOT 아날로그(큐 90% 초과 시 cycle 증가
   휴리스틱, §서술), UTOPIA/SPOT 아날로그(§서술).
5. 시나리오 4종: basic(freeway 3600/urban 1000 veh/h), urban 차단, rush(2000→4000 피크 10분),
   max-queue 20(대/소가중).

## 클린룸 설계
src/vdb/ 독립 모듈(plant·controllers·runner). 본선 스택 무접촉. 단계 게이트:
  P1 plant(보존식·개루프 sanity) → P2 기준선 2종(상대 거동) → P3 MPC(Table 1 패턴) →
  P4 P-Stack 이식(문헌-앵커 비교).

## 본선에서 이월된 관련 지식(교훈)
- 자유출구 경계 = min(ρ,ρ_crit)(Hegyi 표준) — zero-gradient는 fallback 오용(본선서 실증).
- 제약은 가격 계산 지점에 있어야 계층이 한 방향(리더-follower 가격 상쇄 실측).
- VdB 실측 개선율 2~7%가 정상 대역(40%는 깨진 기준선 대비).
- 분기점 커밋: cross-gate 8d03ffa. 브랜치: vdb-replication.
