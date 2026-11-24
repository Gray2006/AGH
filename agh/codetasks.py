"""代码任务集：12 个小函数题，每题带参考解和「已知有 bug 的变体」。

变体的用途是检查**测试本身的质量**（突变测试思路）：若某个变体能通过 hidden 用例，
说明 hidden 用例太弱，分数不可信。`tests/test_codetasks.py` 对每题断言：
参考解 hidden 得 1.0，每个变体 hidden 得分 < 1.0。

只依赖标准库。
"""

# 数据表：每行的参考解/变体是单行 Python 源码，拆行反而不可读
# ruff: noqa: E501

from __future__ import annotations

from dataclasses import dataclass

from .execverify import Case, TaskSpec


@dataclass(frozen=True)
class CodeTask:
    spec: TaskSpec
    prompt: str  # 给模型看的自然语言说明（只含 visible 用例）
    reference: str
    mutants: tuple[str, ...]


def _c(*args, expected) -> Case:
    return Case(tuple(args), expected)


def _task(tid, entry, doc, visible, hidden, reference, mutants) -> CodeTask:
    shown = "\n".join(f"  {entry}{c.args!r} == {c.expected!r}" for c in visible)
    prompt = (
        f"写一个 Python 函数 `{entry}`。{doc}\n只用标准库。可见示例：\n{shown}\n"
        "只输出一个 ```python 代码块，不要解释。"
    )
    return CodeTask(TaskSpec(tid, entry, tuple(visible), tuple(hidden)), prompt, reference, tuple(mutants))


TASKS: dict[str, CodeTask] = {
    t.spec.task_id: t
    for t in (
        _task(
            "dedupe", "dedupe", "去重，保持首次出现的顺序。",
            [_c([1, 2, 1, 3], expected=[1, 2, 3])],
            [_c(["a", "b", "a", "c", "b"], expected=["a", "b", "c"]), _c([5, 5, 5], expected=[5]),
             _c([3, 1, 2], expected=[3, 1, 2]), _c([], expected=[])],
            "def dedupe(xs):\n    s, o = set(), []\n    for x in xs:\n        if x not in s:\n            s.add(x); o.append(x)\n    return o\n",
            ["def dedupe(xs):\n    return sorted(set(xs), key=str)\n",
             "def dedupe(xs):\n    return list(set(xs))\n"],
        ),
        _task(
            "merge_intervals", "merge_intervals", "合并重叠或相接的闭区间，结果按起点升序。",
            [_c([[1, 3], [2, 6], [8, 10]], expected=[[1, 6], [8, 10]])],
            [_c([[1, 4], [4, 5]], expected=[[1, 5]]), _c([[5, 6], [1, 2]], expected=[[1, 2], [5, 6]]),
             _c([[1, 10], [2, 3]], expected=[[1, 10]]), _c([], expected=[])],
            "def merge_intervals(iv):\n    o = []\n    for a, b in sorted(iv):\n        if o and a <= o[-1][1]:\n            o[-1][1] = max(o[-1][1], b)\n        else:\n            o.append([a, b])\n    return o\n",
            ["def merge_intervals(iv):\n    o = []\n    for a, b in sorted(iv):\n        if o and a < o[-1][1]:\n            o[-1][1] = max(o[-1][1], b)\n        else:\n            o.append([a, b])\n    return o\n",
             "def merge_intervals(iv):\n    o = []\n    for a, b in iv:\n        if o and a <= o[-1][1]:\n            o[-1][1] = max(o[-1][1], b)\n        else:\n            o.append([a, b])\n    return o\n"],
        ),
        _task(
            "balanced", "balanced", "判断 ()[]{} 括号串是否合法匹配，空串合法。",
            [_c("()", expected=True), _c("(]", expected=False)],
            [_c("([{}])", expected=True), _c("((", expected=False), _c("", expected=True), _c("([)]", expected=False), _c("]", expected=False)],
            "def balanced(s):\n    p = {')': '(', ']': '[', '}': '{'}\n    st = []\n    for ch in s:\n        if ch in '([{':\n            st.append(ch)\n        elif not st or st.pop() != p[ch]:\n            return False\n    return not st\n",
            ["def balanced(s):\n    return s.count('(') == s.count(')') and s.count('[') == s.count(']') and s.count('{') == s.count('}')\n",
             "def balanced(s):\n    p = {')': '(', ']': '[', '}': '{'}\n    st = []\n    for ch in s:\n        if ch in '([{':\n            st.append(ch)\n        elif st and st.pop() != p[ch]:\n            return False\n    return not st\n"],
        ),
        _task(
            "fib", "fib", "返回第 n 个斐波那契数，fib(0)=0，fib(1)=1。",
            [_c(0, expected=0), _c(10, expected=55)],
            [_c(1, expected=1), _c(2, expected=1), _c(20, expected=6765), _c(50, expected=12586269025)],
            "def fib(n):\n    a, b = 0, 1\n    for _ in range(n):\n        a, b = b, a + b\n    return a\n",
            ["def fib(n):\n    return n if n < 2 else fib(n - 1) + fib(n - 2)\n",
             "def fib(n):\n    a, b = 1, 1\n    for _ in range(n):\n        a, b = b, a + b\n    return a\n"],
        ),
        _task(
            "is_palindrome", "is_palindrome", "只看字母和数字、忽略大小写，判断是否回文。",
            [_c("A man, a plan, a canal: Panama", expected=True)],
            [_c("race a car", expected=False), _c("", expected=True), _c("0P", expected=False), _c("No 'x' in Nixon", expected=True)],
            "def is_palindrome(s):\n    t = [c.lower() for c in s if c.isalnum()]\n    return t == t[::-1]\n",
            ["def is_palindrome(s):\n    return s == s[::-1]\n",
             "def is_palindrome(s):\n    t = ''.join(c for c in s if c.isalpha()).lower()\n    return t == t[::-1]\n"],
        ),
        _task(
            "flatten", "flatten", "把任意深度嵌套的列表展平成一维列表，保持顺序。",
            [_c([1, [2, [3]]], expected=[1, 2, 3])],
            [_c([], expected=[]), _c([[[]]], expected=[]), _c([1, [2, 3], [[4], 5]], expected=[1, 2, 3, 4, 5]), _c([[["a"]], "b"], expected=["a", "b"])],
            "def flatten(x):\n    o = []\n    for i in x:\n        if isinstance(i, list):\n            o.extend(flatten(i))\n        else:\n            o.append(i)\n    return o\n",
            ["def flatten(x):\n    o = []\n    for i in x:\n        if isinstance(i, list):\n            o.extend(i)\n        else:\n            o.append(i)\n    return o\n"],
        ),
        _task(
            "max_subarray", "max_subarray", "返回非空连续子数组的最大和。",
            [_c([-2, 1, -3, 4, -1, 2, 1, -5, 4], expected=6)],
            [_c([-3, -1, -2], expected=-1), _c([5], expected=5), _c([1, 2, 3], expected=6), _c([2, -1, 2, -1, 2], expected=4)],
            "def max_subarray(xs):\n    best = cur = xs[0]\n    for x in xs[1:]:\n        cur = max(x, cur + x)\n        best = max(best, cur)\n    return best\n",
            ["def max_subarray(xs):\n    best = cur = 0\n    for x in xs:\n        cur = max(0, cur + x)\n        best = max(best, cur)\n    return best\n"],
        ),
        _task(
            "roman_to_int", "roman_to_int", "罗马数字转整数（1 到 3999）。",
            [_c("III", expected=3), _c("MCMXCIV", expected=1994)],
            [_c("IV", expected=4), _c("IX", expected=9), _c("LVIII", expected=58), _c("MMMCMXCIX", expected=3999)],
            "def roman_to_int(s):\n    v = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}\n    t = 0\n    for i, c in enumerate(s):\n        if i + 1 < len(s) and v[c] < v[s[i + 1]]:\n            t -= v[c]\n        else:\n            t += v[c]\n    return t\n",
            ["def roman_to_int(s):\n    v = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}\n    return sum(v[c] for c in s)\n"],
        ),
        _task(
            "rle_encode", "rle_encode", "行程编码：连续相同字符压成 字符+次数，空串返回空串。",
            [_c("aaabcc", expected="a3b1c2")],
            [_c("", expected=""), _c("a", expected="a1"), _c("abab", expected="a1b1a1b1"), _c("zzzzzzzzzzzz", expected="z12")],
            "def rle_encode(s):\n    o, i = [], 0\n    while i < len(s):\n        j = i\n        while j < len(s) and s[j] == s[i]:\n            j += 1\n        o.append(s[i] + str(j - i))\n        i = j\n    return ''.join(o)\n",
            ["def rle_encode(s):\n    from collections import Counter\n    return ''.join(c + str(n) for c, n in Counter(s).items())\n",
             "def rle_encode(s):\n    o, i = [], 0\n    while i < len(s):\n        j = i\n        while j < len(s) and s[j] == s[i]:\n            j += 1\n        o.append(s[i] + (str(j - i) if j - i > 1 else ''))\n        i = j\n    return ''.join(o)\n"],
        ),
        _task(
            "gcd", "gcd", "返回两个非负整数的最大公约数，gcd(0, n) = n。",
            [_c(12, 18, expected=6)],
            [_c(0, 5, expected=5), _c(7, 0, expected=7), _c(17, 13, expected=1), _c(100, 75, expected=25)],
            "def gcd(a, b):\n    while b:\n        a, b = b, a % b\n    return a\n",
            ["def gcd(a, b):\n    for d in range(min(a, b), 0, -1):\n        if a % d == 0 and b % d == 0:\n            return d\n    return 1\n"],
        ),
        _task(
            "rotate", "rotate", "把列表向右循环移动 k 位（k 可大于长度，k>=0），返回新列表。",
            [_c([1, 2, 3, 4, 5], 2, expected=[4, 5, 1, 2, 3])],
            [_c([], 3, expected=[]), _c([1, 2, 3], 3, expected=[1, 2, 3]), _c([1, 2, 3], 4, expected=[3, 1, 2]), _c([1], 100, expected=[1])],
            "def rotate(xs, k):\n    if not xs:\n        return []\n    k %= len(xs)\n    return xs[len(xs) - k:] + xs[:len(xs) - k]\n",
            ["def rotate(xs, k):\n    return xs[-k:] + xs[:-k]\n"],
        ),
        _task(
            "second_largest", "second_largest", "返回列表中第二大的**不同**数值；不同值少于 2 个时返回 None。",
            [_c([3, 1, 2], expected=2)],
            [_c([5, 5, 5], expected=None), _c([1], expected=None), _c([4, 4, 3], expected=3), _c([-1, -5, -3], expected=-3)],
            "def second_largest(xs):\n    u = sorted(set(xs), reverse=True)\n    return u[1] if len(u) > 1 else None\n",
            ["def second_largest(xs):\n    s = sorted(xs, reverse=True)\n    return s[1] if len(s) > 1 else None\n"],
        ),
        _task(
            "edit_distance", "edit_distance", "两个字符串的最小编辑距离（插入/删除/替换各算 1）。",
            [_c("kitten", "sitting", expected=3)],
            [_c("", "", expected=0), _c("", "abc", expected=3), _c("abc", "", expected=3),
             _c("same", "same", expected=0), _c("flaw", "lawn", expected=2)],
            "def edit_distance(a, b):\n    prev = list(range(len(b) + 1))\n    for i, ca in enumerate(a, 1):\n        cur = [i]\n        for j, cb in enumerate(b, 1):\n            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))\n        prev = cur\n    return prev[-1]\n",
            ["def edit_distance(a, b):\n    return abs(len(a) - len(b))\n",
             "def edit_distance(a, b):\n    return sum(1 for x, y in zip(a, b) if x != y) + abs(len(a) - len(b))\n"],
        ),
        _task(
            "parse_int", "parse_int", "把字符串转成整数：忽略前导空格，可带一个 +/-，读到非数字停止；没有数字返回 0。",
            [_c("42", expected=42), _c("   -13", expected=-13)],
            [_c("", expected=0), _c("abc", expected=0), _c("+7", expected=7), _c(" 00042", expected=42),
             _c("-0", expected=0), _c("3.14", expected=3)],
            "def parse_int(s):\n    s = s.lstrip()\n    if not s:\n        return 0\n    sign, i = 1, 0\n    if s[0] in '+-':\n        sign = -1 if s[0] == '-' else 1\n        i = 1\n    n = 0\n    while i < len(s) and s[i].isdigit():\n        n = n * 10 + int(s[i])\n        i += 1\n    return sign * n\n",
            ["def parse_int(s):\n    return int(s)\n",
             "def parse_int(s):\n    n = 0\n    for ch in s:\n        if ch.isdigit():\n            n = n * 10 + int(ch)\n    return n\n"],
        ),
        _task(
            "longest_palindrome_subseq", "longest_palindrome_subseq", "最长回文**子序列**的长度（不要求连续）。",
            [_c("bbbab", expected=4)],
            [_c("", expected=0), _c("a", expected=1), _c("abc", expected=1), _c("aaa", expected=3),
             _c("character", expected=5)],
            "def longest_palindrome_subseq(s):\n    n = len(s)\n    dp = [[0] * n for _ in range(n)]\n    for i in range(n - 1, -1, -1):\n        dp[i][i] = 1\n        for j in range(i + 1, n):\n            if s[i] == s[j]:\n                dp[i][j] = dp[i + 1][j - 1] + 2\n            else:\n                dp[i][j] = max(dp[i + 1][j], dp[i][j - 1])\n    return dp[0][n - 1] if n else 0\n",
            ["def longest_palindrome_subseq(s):\n    best = 0\n    for i in range(len(s)):\n        for j in range(i, len(s)):\n            t = s[i:j + 1]\n            if t == t[::-1]:\n                best = max(best, len(t))\n    return best\n",
             "def longest_palindrome_subseq(s):\n    return len(set(s))\n"],
        ),
    )
}

__all__ = ["TASKS", "CodeTask"]
