# 터미널 freeway 셀의 영구 gridlock 원인 규명 — 실제 metanet 함수로 하류경계·v_min 격리 실험
import sys
sys.path.insert(0, r"C:\Users\alsrj\Desktop\Numerical-Sim-offiter\src")
from models.metanet import (
    metanet_speed_update_kmh,
    effective_desired_speed_kmh,
    segment_flow_veh_h,
)

# --- default.yaml FD 상수 (그대로) ---
v_free = 100.0; rho_crit = 33.5; rho_max = 95.01964207118104
v_min = 5.0; a = 1.867
nu_free = 65.0; nu_cong = 250.0; tau_h = 0.005; kappa = 40.0
alpha_vsl = 0.0
lanes = 2.0; L = 0.5; dt_h = 0.002777777777777778   # 10초 substep

def nu_of(rho):
    # capacity_drop_anticipation=true, VSL 없음(vsl=v_free)
    return nu_cong if rho > rho_crit else nu_free

def v_eff_of(rho):
    return effective_desired_speed_kmh(
        rho, v_free, rho_crit, v_free, alpha_vsl, False, a, False, rho_max, 0.0)

def run(q_in, downstream_rho_mode, v_min_use, upstream_v_mode="jam",
        n=600, rho0=92.0, v0=5.5, label=""):
    rho, v = rho0, v0
    for k in range(n):
        veh = rho * L * lanes
        qo = segment_flow_veh_h(rho, v, lanes)          # 터미널 배출 = 자기 rho*v*lanes
        veh_new = max(0.0, veh + dt_h * (q_in - qo))
        rho_new = veh_new / (L * lanes)
        ds_rho = rho if downstream_rho_mode == "own" else float(downstream_rho_mode)
        up_v = v if upstream_v_mode == "jam" else v_free
        veff = v_eff_of(rho)
        v_new = metanet_speed_update_kmh(
            v, up_v, rho, ds_rho, veff, dt_h, L, tau_h, nu_of(rho), kappa, v_min_use)
        rho, v = rho_new, v_new
    qo = segment_flow_veh_h(rho, v, lanes)
    print(f"  {label:52s} -> rho={rho:6.2f}  v={v:6.2f} km/h  q_out={qo:7.1f} veh/h")
    return rho, v

print(f"[기준값] Ve(rho=92) = {v_eff_of(92.0):.2f} km/h  (v_min={v_min}에 걸림)")
print(f"[기준값] Ve(rho_crit=33.5) = {v_eff_of(33.5):.2f} km/h,  capacity ~ {segment_flow_veh_h(33.5, v_eff_of(33.5), lanes):.0f} veh/h (2차로)")
print(f"[기준값] jam 배출 = 92*{v_min}*2 = {segment_flow_veh_h(92.0, v_min, lanes):.0f} veh/h")
print()
print("=== 유입 1204 veh/h (rampdown 후 실측), 초기 rho=92 jam 상태에서 90분+ 방치 ===")
run(1204.0, "own",  5.0, label="현재 모델: downstream_rho=자기밀도, v_min=5")
run(1204.0, 8.0,    5.0, label="[수정A] 자유출구 경계 downstream_rho=8")
run(1204.0, "own",  0.3, label="[수정B] v_min=0.3 (거의 완전정지 허용)")
run(1204.0, 8.0,    0.3, label="[수정A+B] 자유출구 + v_min=0.3")
print()
print("=== knife-edge 확인: 같은 현재모델, 유입만 조금씩 낮춤 (경계=own, v_min=5) ===")
for q in (1300, 1204, 1100, 1000, 900, 800):
    run(float(q), "own", 5.0, label=f"유입 {q} veh/h")
