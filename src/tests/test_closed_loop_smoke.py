import tempfile
import unittest
from pathlib import Path

from src.experiments.run_experiment import main


class ClosedLoopSmokeTest(unittest.TestCase):
    def test_closed_loop_smoke_outputs_required_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "smoke"
            main([
                "--config", "src/config/default.yaml",
                "--scenario", "peak_demand",
                "--baseline", "fixed_signal_fixed_speed",
                "--controller", "stackelberg_mpc",
                "--T-total", "360",
                "--output", str(out),
            ])
            attempt = out / "attempt_0"
            self.assertTrue((attempt / "config_used.yaml").exists())
            self.assertTrue((attempt / "metrics_summary.json").exists())
            self.assertTrue((attempt / "diagnostics.json").exists())
            self.assertTrue((attempt / "baseline" / "run_log.csv").exists())
            self.assertTrue((attempt / "proposed" / "control_timeseries.csv").exists())
            self.assertTrue((attempt / "proposed" / "state_timeseries.csv").exists())
            self.assertTrue((out / "report.md").exists())


if __name__ == "__main__":
    unittest.main()
