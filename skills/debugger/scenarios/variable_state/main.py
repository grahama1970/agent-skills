"""Two independent reports over disjoint inputs.

The second report is wrong: `tally.running_total` leaks state from the first
report through its shared mutable default argument, so `second` is inflated by
the values the first report already accumulated. A debugger set on the tally
return line shows `seen` already carrying the first report's values when the
second report begins.
"""

from report import summarize


def _never_called():
    sentinel = "this line is unreachable in a normal run"
    return sentinel


def main():
    first = summarize([1, 2, 3])
    second = summarize([10, 20])
    verdict = "ok" if second == 30 else "polluted"
    print(f"first={first} second={second} verdict={verdict}")
    return second


if __name__ == "__main__":
    main()
