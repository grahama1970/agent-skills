"""Running tally with a variable-state bug.

`seen` is a mutable default argument: it is created once when the function
is defined and then shared by every call. Totals therefore leak between
unrelated callers. The defect is invisible from the return value of any one
call -- you only see it by pausing inside the function and reading `seen`.
"""


def running_total(value, seen=[]):
    seen.append(value)
    total = sum(seen)
    return total
