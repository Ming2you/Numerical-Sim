# 패키지 재작업 체크리스트 (2026-07-18, 사용자 지시)

## 확정 방침
- **컨트롤러 5종**: no control / wu / pfo (box) / p-stack (walk-MVG) / centralized.
  무제한 PFO(`_paper_pfo`) **완전 제거**. pfo는 box 버전만.
- **시나리오 통용 이름**: low / med / med skewed / med incident / high demand.
  전 스크립트·그림 축·범례·캡션·표·드래프트에 적용.
- **200_w 완전 제거** (메인 5셀만; §5 한계 서사는 200 비의존으로 재작성).
- **urban 분석 신규**: (1) green split 반응, (2) urban queue 궤적. §2에 소절+그림.

## 시나리오 이름 매핑
| 내부 | 통용 이름 |
|---|---|
| sweet_155_w | low demand |
| sweet_170_w | med demand |
| sweet_170_skew15_w | med demand (skewed) |
| sweet_170_incident_w | med demand (incident) |
| sweet_190_w | high demand |
| ~~sweet_200_w~~ | 제거 |

## 컨트롤러 데이터 소스(offiter → 패키지 data/)
| 팔 | 통용 라벨 | offiter 소스 |
|---|---|---|
| nc | No control | _paper_nc/{cell}/NO-CONTROL |
| wu | Wu (WU-CD-F) | _paper_wucdf/{cell}/WU-CD-F |
| pfo_box | PFO (box) | _paper_pfo_box/{cell}/WU-FAITHFUL-FOLLOWER |
| walk_mvg | P-Stack (walk-MVG) | (기존 패키지 data/walk_mvg) |
| pcent | Centralized | _paper_pcent/{cell}/P-CENT |

## 작업 목록
- [ ] 1. 비교 컨트롤러 데이터 복사 (nc/wu/pfo_box/pcent × 5셀 → 패키지 data/)
- [ ] 2. pubstyle.py 재작성 (CELLS 5, 컨트롤러 5 LABEL/STYLE, SCEN_NAME 매핑, 로더)
- [ ] 3. make_table1.py 재작성 → 표1/1b/1c 5컨트롤러 실데이터·통용이름·200제거
- [ ] 4. 신규 urban 그림: green split 반응, urban queue 궤적 (5컨트롤러, 대표셀)
- [ ] 5. 기존 그림 재생성: 이름 통용화, 무제한PFO·200 그림 제거
- [ ] 6. RESULTS_DRAFT.md: §0.2 이름/§0.3 컨트롤러/§1 표/§2 urban소절 추가/§2e·§5 200서사 제거
- [ ] 7. sanity gate 통과 확인 + 커밋
