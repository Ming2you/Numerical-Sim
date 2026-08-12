# 2현시 리터럴이 살아남아 p3/p4 movement 를 조용히 버리는 것을 막는다 (N4-0)
"""`MODEL_PHASES` 를 4현시로 늘려도 하드코딩된 `("p1","p2")` 가 남아 있으면 소용없다.

2026-08-12 실측 - 상류 config 가 150/12/20/78 로 가고 `MODEL_PHASES` 가
`("p1","p2","p3","p4")` 가 된 뒤에도 네 곳이 2현시 튜플을 순회하고 있었다.

    src/controllers/distributed_coordinator.py:345 · :2803 · :3149
    src/controllers/local_signal_plant.py:82

**폴백이 아니라 라이브 경로다.** `wu_distributed` 가 4현시 맵을 옳게 만들어 넘기면
`local_signal_plant.py:82` 가 그 자리에서 p3/p4 를 버린다. 실 토폴로지에서 movement 가
72 -> 38 로 **47.2% 소실** 했다.

이 검사는 소스에 리터럴이 있는지를 본다. 동작 검사보다 약하지만, 같은 실수가 다른 파일에
새로 생기는 것까지 잡는다. 동작 쪽은 `test_four_phase_movements_survive` 가 본다.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
# `("p1", "p2")` / `('p1','p2')` 를 잡는다. 공백과 따옴표 종류를 가리지 않는다.
LITERAL = re.compile(r"""\(\s*['"]p1['"]\s*,\s*['"]p2['"]\s*\)""")


class NoTwoPhaseLiteralTests(unittest.TestCase):
    def test_no_module_iterates_a_hardcoded_two_phase_tuple(self) -> None:
        offenders: list[str] = []
        for path in sorted(SRC.rglob("*.py")):
            if "tests" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for number, line in enumerate(text.splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue          # 주석은 결함을 설명하는 자리다
                if LITERAL.search(line):
                    offenders.append(f"{path.relative_to(SRC)}:{number}  {line.strip()}")
        self.assertEqual(offenders, [], "MODEL_PHASES 를 쓰지 않고 2현시를 하드코딩한 자리")

    def test_model_phases_is_the_single_source(self) -> None:
        from src.models.state import MODEL_PHASES

        self.assertEqual(MODEL_PHASES, ("p1", "p2", "p3", "p4"))


if __name__ == "__main__":
    unittest.main()
