"""Nested/cyclic/oversized state for the bounded-expansion eval (#1438)."""


def build():
    payload = {"user": {"name": "ada", "roles": ["admin", "dev"]}, "count": 3}
    loop = []
    loop.append(loop)  # self-referential: expansion must mark a cycle
    blob = "B" * 50000  # oversized: display value must truncate with metadata
    api_token = "sk-abcdefghijklmnop1234"  # secret-shaped: must be redacted
    unrelated = "must not appear in capture"
    total = payload["count"] + len(loop)
    return total  # breakpoint on this line


if __name__ == "__main__":
    build()
