# freeway agent ramp metering 탐색 결과 (closed-loop T=3600, no_control baseline)

| scenario | no_control | follower | impr% | metering frac (mean) | solve ms/step |
|---|---|---|---|---|---|
| sweet_128 | 3089.532 | 1339.914 | +56.63% | DW0.42 FW0.99 DE0.39 FE0.97 | 8148 |
| sweet_170 | 6002.206 | 3625.024 | +39.61% | DW0.26 FW0.38 DE0.26 FE0.33 | 6112 |
| sweet_190 | 7166.467 | 4807.076 | +32.92% | DW0.25 FW0.29 DE0.48 FE0.49 | 7568 |
| sweet_220 | 8800.579 | 7161.522 | +18.62% | DW0.63 FW0.63 DE0.66 FE0.66 | 9235 |

이전 튜닝-패널티(ramp_metering_weight=10.0) sweet_128 = +30.67%, 회귀 +3.12/+1.54/+1.52%.
greens(sweet_128): A/B/C=56, D=55.5, F=58 (balanced 회복, starvation 제거).
