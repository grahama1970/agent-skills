def relocated_target(value: int) -> int:
    doubled = value * 2
    return doubled + 1


if __name__ == "__main__":
    result = relocated_target(20)
    print(f"remote ssh fixture result={result}")
