# §0 그림: 네트워크 스키매틱 + 21-player 소유권 오버레이 — 전 수치는 offiter 코드에서 추출(발명 금지)
"""f0_network_schematic — 토폴로지 출처(전부 code-of-record):
  - 그리드 leg 인접(2×3, E 비통제, 경계 게이트 7, D/F 남측 램프 leg):
      src/models/grid_topology.py:15-59 (default_grid_node_legs)
  - 신호 5(A,B,C,D,F)·비통제 E·경계 in/out 7쌍·cycle 120/lost 8:
      src/config/default.yaml:55-90, 71-74
  - freeway: FW_W/FW_E, 8 seg × 0.5 km, 2 lanes, cap 4000, v_free 100, rho_crit 33.5:
      src/config/default.yaml:19-30
  - ramp: R_D/R_F × W/E, cap 1500, merge seg {R_D:3, R_F:5}(다이아몬드 재배치 2026-07-13),
      off-ramp OR_D/OR_F × W/E, diverge seg {OR_D:2, OR_F:4}, storage 60 veh(urban 소유):
      src/config/default.yaml:41-53, 131-155; wu_faithful_follower.py:2291-2292
  - agent 분할: segment agent = seg당 1개(segment_local_plant.py:52-68), seg0=origin queue
      소유(:65), merge-seg owner가 metering 소유(:57) → 8-seg 망에서 2×8=16 + urban 5 = 21
      (ANALYSIS_PLAN_FINAL.md:193 'leave-one-out 21 agent' 일치. 'SEG13'은 4-seg 시절 명칭).
동/서 방위는 링크 이름 관습일 뿐 코드에 기하 좌표 없음 — 세그먼트 번호는 진행방향 순서.
"""
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

import pubstyle as ps

# ---- 팔레트(흑백 인쇄에서도 명도차로 구분) ----
C_SIG_FILL = "#CBDDEE"   # urban signal agent
C_SIG_EDGE = "#4477AA"
C_VSL_FILL = "#FBE4CE"   # freeway segment agent (VSL)
C_MET_FILL = "#F0A05A"   # + ramp metering owner
C_EDGE = "#B06A2C"
C_GRAY = "0.45"

XA, XB, XC = 2.0, 5.0, 8.0          # grid columns (A/D, B/E, C/F)
Y_TOP, Y_BOT = 11.55, 9.55          # grid rows
NW, NH = 0.95, 0.62                 # node box size
BAR_X0, CW, BH = 0.55, 1.11, 0.66   # freeway bar origin/cell width/height
Y_FWE, Y_FWW = 5.72, 3.62           # bar bottoms

MERGE_SEG = {"R_D": 3, "R_F": 5}    # default.yaml:49-53
OFF_SEG = {"OR_D": 2, "OR_F": 4}    # default.yaml:141-145


def node_box(ax, x, y, name, controlled):
    fc = C_SIG_FILL if controlled else "white"
    ec = C_SIG_EDGE if controlled else "0.5"
    ls = "-" if controlled else (0, (3, 2))
    ax.add_patch(mpatches.FancyBboxPatch(
        (x - NW / 2, y - NH / 2), NW, NH,
        boxstyle="round,pad=0.03,rounding_size=0.08",
        facecolor=fc, edgecolor=ec, linestyle=ls, linewidth=0.9, zorder=4))
    label = name if controlled else f"{name}"
    ax.text(x, y, label, ha="center", va="center", fontsize=8.5, zorder=5)
    if not controlled:
        ax.text(x, y - NH / 2 - 0.24, "uncontrolled", ha="center", va="top",
                fontsize=5.2, color="0.45", zorder=5)


def road(ax, x0, y0, x1, y1):
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0), zorder=2,
                arrowprops=dict(arrowstyle="<|-|>", color="0.35",
                                lw=0.9, mutation_scale=7, shrinkA=0, shrinkB=0))


def gate(ax, x, y, dx, dy):
    """경계 게이트: in(노드로)·out(바깥으로) 화살표 쌍. (dx,dy)=바깥 방향 단위."""
    L = 0.62
    px, py = -dy * 0.14, dx * 0.14      # 수직 오프셋
    # in
    ax.annotate("", xy=(x + px, y + py), xytext=(x + dx * L + px, y + dy * L + py),
                zorder=3, arrowprops=dict(arrowstyle="-|>", color="0.25",
                                          lw=0.8, mutation_scale=6))
    # out
    ax.annotate("", xy=(x + dx * L - px, y + dy * L - py), xytext=(x - px, y - py),
                zorder=3, arrowprops=dict(arrowstyle="-|>", color="0.62",
                                          lw=0.8, mutation_scale=6))


def cell_x(seg):
    return BAR_X0 + seg * CW


def draw_bar(ax, y, link, ramp_side):
    """8-seg 바 + seg 번호 + agent 채색 + 램프 화살표. ramp_side: 'E' or 'W'."""
    for seg in range(8):
        x = cell_x(seg)
        is_meter = seg in MERGE_SEG.values()
        fc = C_MET_FILL if is_meter else C_VSL_FILL
        hatch = "///" if seg == 0 else None
        ax.add_patch(mpatches.Rectangle(
            (x, y), CW, BH, facecolor=fc, edgecolor=C_EDGE, hatch=hatch,
            linewidth=0.7, zorder=3))
        ax.text(x + CW / 2, y + BH / 2, str(seg), ha="center", va="center",
                fontsize=6.2, zorder=5)
    # 진행방향 화살표 + 링크 라벨
    ax.annotate("", xy=(BAR_X0 + 8 * CW + 0.42, y + BH / 2),
                xytext=(BAR_X0 + 8 * CW + 0.04, y + BH / 2), zorder=3,
                arrowprops=dict(arrowstyle="-|>", color="0.2", lw=1.0, mutation_scale=8))
    ax.text(BAR_X0 - 0.5, y + BH + 0.06, link, ha="left", va="bottom",
            fontsize=7.5, fontweight="bold", zorder=5)
    # 본선 origin(+queue) 유입
    ax.annotate("", xy=(BAR_X0, y + BH / 2), xytext=(BAR_X0 - 0.44, y + BH / 2),
                zorder=3, arrowprops=dict(arrowstyle="-|>", color="0.2",
                                          lw=1.0, mutation_scale=8))
    ax.text(BAR_X0 - 0.24, y - 0.10, "origin\n(+queue)", ha="center", va="top",
            fontsize=4.8, color="0.3", zorder=5)
    # 램프 화살표(바 위쪽 = urban 방향): off는 바→위, on은 위→바
    yt = y + BH
    for stem, node in (("OR_D", "D"), ("OR_F", "F")):
        seg = OFF_SEG[stem]
        x = cell_x(seg) + CW / 2
        ax.annotate("", xy=(x, yt + 0.48), xytext=(x, yt), zorder=3,
                    arrowprops=dict(arrowstyle="-|>", color=C_EDGE,
                                    lw=0.9, mutation_scale=7))
        ax.text(x - 0.06, yt + 0.52, f"{stem}_{ramp_side}", ha="center", va="bottom",
                fontsize=5.0, color="0.2", zorder=5)
    for stem, node in (("R_D", "D"), ("R_F", "F")):
        seg = MERGE_SEG[stem]
        x = cell_x(seg) + CW / 2
        ax.annotate("", xy=(x, yt), xytext=(x, yt + 0.48), zorder=3,
                    arrowprops=dict(arrowstyle="-|>", color="0.2",
                                    lw=0.9, mutation_scale=7))
        ax.text(x + 0.08, yt + 0.52, f"{stem}_{ramp_side}\n" + r"$\leq$1500",
                ha="center", va="bottom", fontsize=5.0, color="0.2", zorder=5)


def main():
    ps.sanity_gate()
    fig, ax = ps.new_fig(3.5, 4.6)
    ax.set_xlim(-0.55, 10.35)
    ax.set_ylim(-0.25, 13.15)
    ax.axis("off")

    # ---------------- urban 2×3 grid ----------------
    # 내부 도로 7(양방향 directed 14): A-B, B-C, D-E, E-F, A-D, B-E, C-F
    road(ax, XA + NW / 2, Y_TOP, XB - NW / 2, Y_TOP)
    road(ax, XB + NW / 2, Y_TOP, XC - NW / 2, Y_TOP)
    road(ax, XA + NW / 2, Y_BOT, XB - NW / 2, Y_BOT)
    road(ax, XB + NW / 2, Y_BOT, XC - NW / 2, Y_BOT)
    road(ax, XA, Y_TOP - NH / 2, XA, Y_BOT + NH / 2)
    road(ax, XB, Y_TOP - NH / 2, XB, Y_BOT + NH / 2)
    road(ax, XC, Y_TOP - NH / 2, XC, Y_BOT + NH / 2)
    # 경계 게이트 7쌍: A(top,left), B(top), C(top,right), D(left), F(right)
    gate(ax, XA, Y_TOP + NH / 2, 0, 1)
    gate(ax, XA - NW / 2, Y_TOP, -1, 0)
    gate(ax, XB, Y_TOP + NH / 2, 0, 1)
    gate(ax, XC, Y_TOP + NH / 2, 0, 1)
    gate(ax, XC + NW / 2, Y_TOP, 1, 0)
    gate(ax, XA - NW / 2, Y_BOT, -1, 0)
    gate(ax, XC + NW / 2, Y_BOT, 1, 0)
    ax.text(5.0, Y_TOP + 1.05, "boundary in/out gates (7)", ha="center",
            va="bottom", fontsize=5.6, color="0.35")
    # 노드(신호 agent 5 + 비통제 E)
    for x, name in ((XA, "A"), (XB, "B"), (XC, "C")):
        node_box(ax, x, Y_TOP, name, True)
    node_box(ax, XA, Y_BOT, "D", True)
    node_box(ax, XB, Y_BOT, "E", False)
    node_box(ax, XC, Y_BOT, "F", True)

    # ---------------- interchange stems (D, F -> freeway) ----------------
    xd = cell_x(3)            # D 인터체인지: off seg2 / on seg3 경계
    xf = cell_x(5)            # F 인터체인지: off seg4 / on seg5 경계
    for x_node, x_ic in ((XA, xd), (XC, xf)):
        ax.plot([x_node, x_ic], [Y_BOT - NH / 2 - 0.05, 7.55],
                color="0.72", lw=0.8, linestyle=(0, (3, 2)), zorder=1)
        ax.plot([x_ic, x_ic], [7.55, 2.95],
                color="0.72", lw=0.8, linestyle=(0, (3, 2)), zorder=1)
    for x_node, x_ic, name in ((XA, xd, "D"), (XC, xf, "F")):
        xm = (x_node + x_ic) / 2.0
        ym = (Y_BOT - NH / 2 - 0.05 + 7.55) / 2.0
        ax.text(xm, ym, f"{name} interchange", ha="center", va="center",
                fontsize=5.4, color="0.4", style="italic", zorder=2,
                bbox=dict(facecolor="white", edgecolor="none", pad=0.6))

    # ---------------- freeway bars ----------------
    draw_bar(ax, Y_FWE, "FW_E (eastbound)", "E")
    draw_bar(ax, Y_FWW, "FW_W (westbound)", "W")
    ax.text(5.0, Y_FWW - 0.62,
        "each link: 8 seg × 0.5 km, 2 lanes, $q_{cap}$ 4000 veh/h, "
        "$v_{free}$ 100 km/h, $\\rho_{crit}$ 33.5;\n"
        "off-ramps → 60-veh storage (urban-owned) → D/F approaches; "
        "on-ramp queue ≤ 180 veh;\n"
        "segment index runs in direction of travel (E/W naming nominal — "
        "no geometry in model)",
        ha="center", va="top", fontsize=5.2, color="0.3")
    ax.text(5.0, Y_FWW - 1.72,
            "players: 5 urban + 2 × 8 freeway = 21 (per-segment agents, SEG13)",
            ha="center", va="top", fontsize=6.4, fontweight="bold")

    # ---------------- legend / player count ----------------
    handles = [
        mpatches.Patch(facecolor=C_SIG_FILL, edgecolor=C_SIG_EDGE, linewidth=0.8,
                       label="urban signal agent (5): green split, cycle 120 s"),
        mpatches.Patch(facecolor=C_VSL_FILL, edgecolor=C_EDGE, linewidth=0.7,
                       label="freeway segment agent (2×8): own-segment VSL"),
        mpatches.Patch(facecolor=C_MET_FILL, edgecolor=C_EDGE, linewidth=0.7,
                       label="+ ramp-metering owner (seg 3: R_D, seg 5: R_F)"),
        mpatches.Patch(facecolor=C_VSL_FILL, edgecolor=C_EDGE, hatch="///",
                       linewidth=0.7, label="seg 0: also owns mainline origin queue"),
    ]
    ax.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.005),
              fontsize=5.6, frameon=False, handlelength=1.4,
              handleheight=0.9, borderaxespad=0.0, labelspacing=0.35)

    ps.save(fig, "f0_network_schematic")


if __name__ == "__main__":
    main()
