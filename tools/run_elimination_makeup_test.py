from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_input_logic_tests as runner


runner.TESTS = [
    {
        "id": "E11_pet_elimination_makeup",
        "kind": "elimination_logic",
        "prompt": "E11 Answer only final name Ann Bob Cara each has one pet cat dog fish Cara has fish Ann does not have cat Bob does not have dog Who has dog",
        "zh_question": "Ann、Bob、Cara 各养一种宠物：猫、狗、鱼。Cara 养鱼；Ann 不养猫；Bob 不养狗。谁养狗？",
        "expected": ["Ann"],
    }
]


if __name__ == "__main__":
    raise SystemExit(runner.main())
