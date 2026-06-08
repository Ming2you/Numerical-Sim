import unittest

from src.evaluation.metrics import boundary_cv, improvement_rate
from src.models.urban_queue_model import safe_balance_index


class MetricTests(unittest.TestCase):
    def test_improvement_rate_lower_is_better(self):
        self.assertAlmostEqual(improvement_rate(100.0, 92.0, "lower_is_better"), 8.0)

    def test_improvement_rate_higher_is_better(self):
        self.assertAlmostEqual(improvement_rate(100.0, 108.0, "higher_is_better"), 8.0)

    def test_boundary_cv_zero_queue_case(self):
        self.assertEqual(boundary_cv([0.0, 0.0, 0.0]), 0.0)

    def test_balance_index_equal_queue_is_zero_or_near_zero(self):
        self.assertLessEqual(safe_balance_index([10.0, 10.0, 10.0]), 1e-12)

    def test_balance_index_unbalanced_queue_is_positive(self):
        self.assertGreater(safe_balance_index([1.0, 9.0, 20.0]), 0.0)


if __name__ == "__main__":
    unittest.main()
