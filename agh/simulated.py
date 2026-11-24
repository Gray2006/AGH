"""离线模拟模型：只用于验证流水线和统计代码，**不代表任何真实模型的能力**。

每次调用按 sha256(prompt) 决定性地返回：以概率 p_correct 返回参考解；以 p_garbage 返回语法错误代码；
其余随机返回该题的一个已知 bug 变体。模型对 hint 不敏感（刻意如此，避免把「答案」埋进模拟里）。
"""

from __future__ import annotations

import hashlib
import random
import re

from .codetasks import TASKS


class SimulatedCoder:
    def __init__(self, p_correct: float = 0.4, p_garbage: float = 0.15, seed: int = 0) -> None:
        self.p_correct, self.p_garbage, self.seed = p_correct, p_garbage, seed
        self.calls = 0

    def __call__(self, prompt: str) -> str:
        self.calls += 1
        m = re.search(r"`(\w+)`", prompt)
        if m is None:
            raise ValueError("模拟模型只认带 `entrypoint` 的提示")
        task = TASKS[m.group(1)]
        h = hashlib.sha256(f"{self.seed}|{prompt}".encode()).digest()
        rng = random.Random(int.from_bytes(h[:8], "big"))
        r = rng.random()
        if r < self.p_correct:
            code = task.reference
        elif r < self.p_correct + self.p_garbage:
            code = f"def {task.spec.entrypoint}(:\n"
        else:
            code = rng.choice(task.mutants)
        return f"```python\n{code}```"


__all__ = ["SimulatedCoder"]
