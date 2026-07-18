# 그림 재생성 안내 (다른 컴퓨터용)

그림 파일(`analysis/figures/*.pdf|png`)은 **repo에 추적하지 않는다**(재생성 가능, 용량 큼).
다른 컴퓨터에서 그림을 그리려면 아래로 전부 재생성한다.

## 재생성
```bash
cd 2026-07-17/paper_package/analysis/scripts
python run_all.py
```
- `analysis/figures/`에 PDF(벡터) + PNG(600dpi)가 생성된다.
- 개별 그림만: `python fig_ttt_traj.py`, `python fig_urban_queue.py` 등.
- `run_all.py`는 시작 시 `pubstyle.sanity_gate()`로 walk_mvg 5셀 개선%가 표1과 일치하는지
  자동 검증한다(불일치 시 즉시 중단).

## 필요 환경
- Python 3.12, `pandas` / `numpy` / `matplotlib`.
- **Times New Roman 폰트**(없으면 serif 폴백 + 경고 — 저널 제출 전 실제 폰트 확인).

## 데이터 출처(이미 repo에 포함)
- `data/<arm>/<cell>/{run_log,control_timeseries,state_timeseries}.csv`
  - arm = nc / wu / pfo_box / pcent / walk_mvg (메인 5컨트롤러) + farsa_ref/pd4_ref/box300_vsl10_ref(§3 변형).
  - cell = sweet_155_w / sweet_170_w / sweet_170_skew15_w / sweet_170_incident_w / sweet_190_w.
- 표: `analysis/tables/`(t1_macro_full 자동생성, t_sensitivity_b8 등).
- 초안: `analysis/draft/RESULTS_DRAFT.md` (v3, 5컨트롤러·통용명·urban 포함).

## 주의
- 통용 시나리오명(Low/Med/Med skewed/Med incident/High demand)은 `pubstyle.SCEN_NAME`에 중앙화 —
  그림 축·범례·제목이 여기서 나온다.
- 무제한 PFO·sweet_200_w는 논문에서 제외(pubstyle CELLS/CONTROLLERS 반영).
