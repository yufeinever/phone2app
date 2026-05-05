from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_input_logic_tests as runner


runner.TESTS = [
    {
        "id": "L01_wason",
        "kind": "conditional_logic",
        "prompt": "L01 Answer only card labels You see cards A D 4 7 Rule If a card has a vowel on one side it has an even number on the other Which cards must be turned over",
        "zh_question": "你看到四张卡片 A、D、4、7。规则是：如果一张卡一面是元音字母，那么另一面一定是偶数。为了验证规则，必须翻哪几张？",
        "expected": ["A and 7", "A, 7", "A 7", "7 and A"],
    },
    {
        "id": "L02_linda",
        "kind": "fallacy_conjunction",
        "prompt": "L02 Answer only one phrase Linda is outspoken and studied philosophy Which is more likely bank teller or bank teller and feminist",
        "zh_question": "琳达很关心社会议题，学过哲学。哪个更可能：她是银行出纳，还是她是银行出纳并且是女权主义者？",
        "expected": ["bank teller"],
        "reject": ["and feminist"],
    },
    {
        "id": "L03_monty",
        "kind": "probability_reasoning",
        "prompt": "L03 Answer only switch or stay In a three door game you pick door 1 host opens goat door 3 Should you switch or stay for best chance",
        "zh_question": "三门问题：你先选 1 号门，主持人打开 3 号门且里面是羊。为了中奖概率最大，应该换门还是坚持？",
        "expected": ["switch"],
    },
    {
        "id": "L04_knaves",
        "kind": "truth_liar_logic",
        "prompt": "L04 Answer only A status and B status On an island knights tell truth and knaves lie A says we are both knaves What are A and B",
        "zh_question": "骑士永远说真话，骗子永远说假话。A 说：我们俩都是骗子。A 和 B 分别是什么身份？",
        "expected": ["A knave B knight", "A is knave B is knight", "A is knave, B is knight", "A liar B knight"],
    },
    {
        "id": "L05_truth_chain",
        "kind": "truth_liar_logic",
        "prompt": "L05 Answer only names of truth tellers A says B is lying B says C is lying C says A and B are lying Truth tellers always tell truth liars always lie Who tells truth",
        "zh_question": "A 说 B 在说谎；B 说 C 在说谎；C 说 A 和 B 都在说谎。真话者永远说真话，说谎者永远说假话。谁在说真话？",
        "expected": ["B"],
    },
    {
        "id": "L06_all_some",
        "kind": "quantifier_logic",
        "prompt": "L06 Answer only yes or no All poets are writers Some artists are poets Does it follow that some artists are writers",
        "zh_question": "所有诗人都是作家；有些艺术家是诗人。是否必然推出：有些艺术家是作家？",
        "expected": ["yes"],
    },
    {
        "id": "L07_invalid_conversion",
        "kind": "quantifier_logic",
        "prompt": "L07 Answer only yes or no All cats are mammals Does it follow that all mammals are cats",
        "zh_question": "所有猫都是哺乳动物。是否必然推出：所有哺乳动物都是猫？",
        "expected": ["no"],
    },
    {
        "id": "L08_doors_guards",
        "kind": "counterfactual_logic",
        "prompt": "L08 Answer only opposite door Two doors one safe one dangerous One guard lies one tells truth You ask one guard which door would the other guard say is safe Which door should you choose",
        "zh_question": "两扇门一安全一危险，两个守卫一真一假。你问任一守卫：另一个守卫会说哪扇门安全？你应该选择哪扇门？",
        "expected": ["opposite"],
    },
    {
        "id": "L09_only_one_true",
        "kind": "exclusive_logic",
        "prompt": "L09 Answer only guilty person Exactly one of these statements is true A says B is guilty B says A is not guilty C says B is not guilty Exactly one person is guilty Who is guilty",
        "zh_question": "三句话中恰好一句为真：A 说 B 有罪；B 说 A 无罪；C 说 B 无罪。且三人中恰好一人有罪。谁有罪？",
        "expected": ["A"],
    },
    {
        "id": "L10_negation",
        "kind": "formal_logic",
        "prompt": "L10 Answer only yes or no Statement Every report has at least one error Is its negation No report has any error",
        "zh_question": "命题“每份报告至少有一个错误”的否定，是不是“没有任何报告有错误”？",
        "expected": ["no"],
    },
]


if __name__ == "__main__":
    raise SystemExit(runner.main())
