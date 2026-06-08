"""
Model and controller parameters.

The topology now follows Zhai et al. (2025) Figure 3. Model constants are kept
from the earlier METANET/Kashani numerical implementation unless explicitly
overridden.
"""
from dataclasses import dataclass, field


@dataclass
class MetanetParams:
    """METANET freeway model parameters. [P] unless noted."""
    v_free: float = 106.0      # km/h   [P]
    rho_crit: float = 33.5     # veh/km/lane [P]
    rho_max: float = 180.0     # veh/km/lane [P]
    Q_cap: float = 4000.0      # veh/h  [P] (per link, 2 lanes)
    tau: float = 18.0 / 3600.0 # h  (18 s) [P]
    nu: float = 65.0           # km^2/h [P]
    kappa: float = 40.0        # veh/km/lane [P]
    a_m: float = 1.867         # -      [P]
    # numerical floor to avoid divide-by-zero in anticipation term
    rho_eps: float = 1e-3

    def V(self, rho):
        """Desired speed V(rho), Eq. (2)."""
        import numpy as np
        return self.v_free * np.exp(-(1.0 / self.a_m) * (rho / self.rho_crit) ** self.a_m)


@dataclass
class UrbanParams:
    """Urban (Kashani-extended) model parameters. [P] unless noted."""
    Q_sat: float = 1000.0      # veh/h  saturation flow [P]
    L_veh: float = 6.0         # m      avg vehicle length [P]
    v_avg: float = 50.0        # km/h   avg link speed [P]


@dataclass
class TimeParams:
    """Time steps."""
    Tc: float = 120.0          # s  controller step [P]
    Tf: float = 10.0           # s  freeway step    [P]
    Tu: float = 1.0            # s  urban step       [P]
    sim_time: float = 1800.0   # s  total (30 min)   [P]

    @property
    def Tf_h(self):
        return self.Tf / 3600.0

    @property
    def Tu_h(self):
        return self.Tu / 3600.0

    @property
    def K_cu(self):
        """Tc / Tu (urban steps per controller step)."""
        return int(round(self.Tc / self.Tu))

    @property
    def K_cf(self):
        """Tc / Tf (freeway steps per controller step)."""
        return int(round(self.Tc / self.Tf))

    @property
    def K_fu(self):
        """Tf / Tu (urban steps per freeway step)."""
        return int(round(self.Tf / self.Tu))


@dataclass
class MPCParams:
    """MPC parameters. [P]."""
    Np: int = 8                # prediction horizon [P]
    Nc: int = 3                # control horizon    [P]
    alpha: float = 1.0         # urban/freeway TTS weight [P]
    cycle_time: float = 120.0  # s  signal cycle [A] = Tc
    g_min: float = 0.2         # min green fraction per phase [A]
    g_max: float = 0.8         # max green fraction per phase [A]
    b_min: float = 0.2         # min ramp metering rate [A]
    b_max: float = 1.0         # max ramp metering rate [A]
    vsl_min: float = 60.0      # km/h min direction-level VSL [A]
    vsl_max: float = 106.0     # km/h max direction-level VSL [A]
    # optimizer
    maxiter: int = 40          # SLSQP iterations per control step [A]
    n_starts: int = 2          # multi-start [A] (paper uses multi-start SQP)


@dataclass
class Params:
    metanet: MetanetParams = field(default_factory=MetanetParams)
    urban: UrbanParams = field(default_factory=UrbanParams)
    time: TimeParams = field(default_factory=TimeParams)
    mpc: MPCParams = field(default_factory=MPCParams)
