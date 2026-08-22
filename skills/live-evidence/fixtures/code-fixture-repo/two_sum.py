def two_sum(nums: list[int], target: int) -> list[int]:
    """Return the indices of the two values that sum to target.

    Single pass with a hash map: for each value, the complement
    (target minus value) is the only number that can pair with it,
    so an O(1) lookup replaces the O(n) inner scan of brute force.
    """
    seen: dict[int, int] = {}
    for index, value in enumerate(nums):
        complement = target - value
        if complement in seen:
            return [seen[complement], index]
        seen[value] = index
    return []
