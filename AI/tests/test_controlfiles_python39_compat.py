from __future__ import annotations

import unittest
from pathlib import Path


CONTROLFILES_DIR = Path(__file__).resolve().parents[1] / "controlfiles"


class ControlfilesPython39CompatTest(unittest.TestCase):
    def test_controlfiles_do_not_use_python310_dataclass_slots(self):
        offenders = []
        for path in CONTROLFILES_DIR.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "dataclass(" in text and "slots=" in text:
                offenders.append(path.name)

        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
