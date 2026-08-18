"""Summarize a batch of values by folding running_total over them."""

from tally import running_total


def summarize(values):
    last = 0
    for value in values:
        last = running_total(value)
    return last
