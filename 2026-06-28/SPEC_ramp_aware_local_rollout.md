# 명세: ramp-aware per-signal 국소 rollout (분해손실 27%p 수정)

## 근거 (왜 이게 fix인가)
- 검증(A↔B): sweet_128 분해손실 ≈27%p. lever는 **urban green**(VSL 무력), 특히 **D/F가 p2-heavy(p1→20)**.
- 원인: 현 `rollout_local_tts`(local_signal_plant.py)는 신호 movement 큐만 전진 + **freeway/ramp 통째 동결**(off-ramp 유입=고정상수, off-ramp storage·on-ramp reservoir 동역학 **없음**). 그래서 split의 결합 결과(off-ramp storage 차오름·freeway 적재)를 못 봐 **p1-heavy를 잘못 선택**(local argmin 62/86 vs plant 38/20).
- coupling이 off-ramp 유입으로 `arr_p1`을 부풀려(arr_D_p1=2114 > arr_p2=1401) own-TTS가 demand-responsive하게 p1을 키움. 실제 전역 최적은 게이트수요(p2, in_D_left=1171) 우선.

## 핵심 설계 결정
**off-ramp storage·on-ramp reservoir를 urban agent(D/F)에 귀속**(Wu §IV-A: "off-ramp (m,i) is also contained in agent i"). 국소 rollout이 이 ramp 인터페이스를 **직접 전진**시키고, **freeway 본선(ρ,v)만 동결**(진짜 이웃 결합변수). ramp 인터페이스는 자기 권역이라 국소로 굴려도 O(n) 유지. (freeway 전체를 굴리는 것도, 통째 동결하는 것도 아닌 중간.)

## 구현 (새 파일/확장, 기존 미변경)
대상: freeway-인접 신호(D,F). 그 외 신호(A,B,C)는 기존 국소 rollout 유지(ramp 없음).

### 추가 국소 상태 (agent 소유)
- off-ramp storage 점유: `OR_D_W_storage, OR_D_E_storage`(D), `OR_F_W/E_storage`(F).
- on-ramp reservoir 큐: `R_D_W, R_D_E`(D), `R_F_W/E`(F).
- 기존: 자기 movement 큐.

### 동역학 (substep마다, 실제 plant 회계와 일치)
1. **off-ramp storage 유입(동결)**: freeway→off-ramp 유출 = coupling 고정값(`_last_offramp_flow`/off-ramp inflow). storage += inflow·dt.
2. **off-ramp discharge(green-gated)**: off_ramp-kind movement이 storage에서 urban으로 방출, green_fraction(phase)·cap·하류 S_eff로 제한(`_drain_offramp_storage` 회계 복제). 못 빼면 storage 차오름.
3. **on-ramp 적재(green-gated)**: on_ramp-kind movement이 green에 따라 reservoir(R_*)로 release, ramp_queue_max로 cap. 넘치면 urban movement 큐로 backup.
4. **urban movement 큐**: 기존 회계.

### 목적함수 (agent own-TTS — ramp 귀속 반영)
`J_i = Σ_substep ( Σ urban movement 큐 + Σ off-ramp storage 점유 + Σ on-ramp reservoir 큐 ) · dt  + R_i·|Δg|`
- off-ramp storage·on-ramp 큐가 자기 비용에 들어가 split의 결합 상충(off-ramp 비용 vs freeway 적재)이 보임.
- (선택) on-ramp 적재에 freeway 혼잡도(동결 ρ) 비례 가중 → de facto ramp metering. 1차엔 생략 가능, 효과 부족시 추가.

### 동결(이웃 결합변수)
- freeway 본선 ρ,v(off-ramp inflow·on-ramp 수용에 영향) — 한 step 내 고정, iteration마다 갱신(가능하면; 최소 step당 1회). **arr 갱신은 유지.**

## 검증 (코더↔검토 루프, 무에러까지)
- (V1) D/F 국소 rollout이 off-ramp storage·on-ramp reservoir를 전진시키는가(freeway 본선만 동결, 전체 freeway 호출 없음).
- (V2) 회계가 실제 plant(`_drain_offramp_storage`, ramp_requests, off-ramp storage 재귀속)와 정성 일치.
- (V3) D/F argmin이 plant 방향(p1↓)으로 뒤집히는가(국소 scoring vs 실제 plant).
- (V4) **closed-loop sweet_128 T=3600: −1.19% → 양의 큰 개선**(목표 WU-CD-F +25% 근처), **비용은 국소 유지**(전역 채점 78s/step 대비 훨씬 쌈).
- (V5) 회귀: 수요 스윕(170/190/220) 무해, A/B/C 영향 없음.

## 불변
- 기존 코드 미변경(복제/참조만). plant 차량보존·단위 일관. 반드시 closed-loop로 측정(단일-state 프로브 불신).
