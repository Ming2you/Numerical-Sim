# TABLE 4 — 캡션 + 본문 해설 문단 (2026-07-23)

## Caption
**TABLE 4 Contribution of Marginal-Externality Pricing to Network TTT (veh·h, 900–14,400 s)**
Proposed = full controller (budgets + four price channels); Pricing removed = same controller
with all price channels (green time, ramp metering, VSL, offset) disabled, retaining only the
aggregate budgets. ΔTTT = (Pricing removed) − Proposed; Contribution = ΔTTT / Proposed.

## 본문 삽입용 문단 (English)
To isolate the contribution of the marginal-externality prices, we re-ran the proposed controller
with all four price channels (green time, ramp metering, VSL, and offset) disabled, retaining only
the aggregate budgets. Table 4 reports the resulting network-wide TTT over the 900–14,400 s analysis
period. Removing the price layer increases TTT by 8.8%, 4.2%, and 9.9% under medium, medium-skew, and
high demand, respectively, showing that pricing provides a substantial refinement on top of
budget-based coordination when congestion is preventable. In the incident scenario, by contrast, the
price layer is TTT-neutral (0.0%): the 30-minute lane closure fixes the freeway discharge capacity, so
control can only redistribute delay between the freeway and urban subnetworks rather than reduce it.
Under low demand, where little congestion forms, pricing slightly increases TTT (−0.5%). These results
indicate that the value of marginal-externality pricing depends on whether the controller can influence
bottleneck throughput (preventable congestion) or only its allocation (an imposed capacity loss).

## 근거 데이터 (내부, 논문 미기재)
- ON = base_* (순수 price-ON b13 flagship), OFF = alloff_* (ALLPRICE_OFF=1, 4채널 전부 off)
- 정밀값: Low 2989.8/2973.8, Med 3809.6/4146.1, Skew 3990.2/4156.4, Inc 5546.3/5546.9, High 5734.8/6303.1
- incident 제로섬 증거: 사고 중 mainline_exit_flow_total ON≈OFF(±2%), freeway TTT −212 / urban TTT +212 상쇄
- cf_190은 PRICE_CF 반사실 상태누수로 오염(+11%) → ON은 base_190 사용(clean)
- Contribution% 분모 = ON(full-pricing). 논문 Figure5 관례(분모=비교baseline)를 따르려면 분모=OFF로:
  Med +8.1%, Skew +4.0%, High +9.0% (Δ veh·h는 분모무관 동일)
