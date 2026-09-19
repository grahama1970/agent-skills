import argparse
import json


def result(value: int) -> dict[str, int]:
    return {"result": value + 1}


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute one plus the provided integer.")
    parser.add_argument("value", type=int)
    print(json.dumps(result(parser.parse_args().value), sort_keys=True))


if __name__ == "__main__":
    main()
