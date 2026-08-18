"""A function whose paused frame holds credential-shaped values.

Used by the redaction eval: none of these values may reach a proof artifact
verbatim. `password` and `api_token` are caught by name; `canary` has an
innocuous name but a JWT-shaped value, so it must be caught by value.
"""


def authenticate(user):
    password = "hunter2-do-not-leak-7f3a"
    api_token = "sk-abcdefghijklmnop0123456789ABCD"
    canary = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.abcd1234efgh"
    ok = bool(user and password and api_token and canary)
    return ok


if __name__ == "__main__":
    print(authenticate("alice"))
