def relocated_target(value: int) -> int:
    doubled = value * 2
    # Breakpoint requested on THIS comment line: the adapter must relocate it to
    # the next executable line (the return), where value and doubled both exist.
    return doubled + 1


if __name__ == "__main__":
    result = relocated_target(20)
    print(f"remote ssh fixture result={result}")
