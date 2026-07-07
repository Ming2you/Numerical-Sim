# Joint-pair 가격 채널 probe 보고 (green×offset, metering×VSL) — 2026-07-07

## 배경·가설
per-lever 1차 가격 실패 레버(offset=F3 null, metering=F2 붕괴, VSL=inert). 가설: 결합 쌍이라
1차 편미분≈0이어도 cross-term ∂²TTT가 신호를 가질 수 있다. **구현 전 probe로 go/no-go**(방법론
규율 + FP 위기 대응: probe는 단일 상태 결정론적 FD라 7200s 머신간 발산 ~700에 면역).

## Task 1 — green×offset cross-term (work/joint_green_offset_price_probe.py)
sweet_190 steps 18/24/30, 신호 A/B/C, (Δp1∈±6, Δoff∈±cycle/4) 5×5 격자 전역 horizon TTT.

| 신호 | joint_gain (veh·h/horizon) | Δoff*≠0 |
|---|---|---|
| A | 0.25 / 0.32 / 0.54 | 대부분 Y |
| B | 0.00 / 0.03 / 0.07 | N |
| C | 0.42 / **1.60** / 1.03 | Y |

**판정 = NO-GO.** cross-term은 **존재**(A/C에서 joint 최적 Δoff≠0)하나 이득이 **최대 1.60
veh·h/horizon(0.14%)**. 40스텝 실현해도 ~20–64 veh·h로 **FP 발산 하한(~700–960)의 1/10~1/50**
→ 닫힌 루프서 측정 불가. **offset 실물가치는 intra-signal 아니라 inter-signal(corridor
green-wave).** F3(per-signal 가격 null)·Codex 분해(국소 offset 7%뿐)와 수렴. → Task 2(joint_go
price 구현) 스킵, corridor(MAXBAND식 다신호 offset joint) 레인.

## Task 3 — metering×VSL cross-term (work/joint_metering_vsl_price_probe.py)
⚠ metering 절벽 caveat: ρ>ρ_crit은 미분 무의미 → **sub-critical(ρ<ρ_crit)에서만**.
- sweet_190: step 2~40 전부 ρ≥ρ_crit(33.5) — **sub-critical 상태 없음**(상시 절벽, §12 강화).
- sweet_128 sub-critical(ρ=27~30) 3스텝×2링크: **joint_gain=0.000 전부, Δm=Δvsl=0**(base=최소).

**판정 = NO.** sub-critical은 자유류라 병목 부재 → metering·VSL 단독·cross 모두 0. super-critical은
절벽(§13). **매끄러우면서 비자명한 priceable regime이 존재하지 않음** → RM/VSL joint 가격 무효,
**metering=constraint(F1RHO/등식) 확정.** F2의 완전 실패 이유도 설명(가격은 매끄러운 비자명
기울기 필요, metering/VSL은 그 영역 부재).

## 종합
per-lever 가격 실패 레버는 joint-pair로도 안 살아나되 실패 방식이 다름:
- **offset**: cross-term 있으나 tiny(intra) → **corridor 다신호 joint가 진짜 레인**.
- **metering/VSL**: cross-term 부재(자유류 0/절벽 garbage) → **가격 포기, constraint 확정**.

전 판정 FP-면역(단일상태 결정론적, 이득 절대값 tiny/0). probe-first 규율이 7200s 노이즈 매몰을 방지.

## 재현
- `python -B work/joint_green_offset_price_probe.py --scenario sweet_190 --steps 18,24,30`
- `python -B work/joint_metering_vsl_price_probe.py --scenario sweet_128 --trace 2026-07-06/results/trajectories/g1df_sweet128_7200/control_timeseries.csv`
