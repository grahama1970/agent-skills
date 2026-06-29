"""Arena Team target app with secretly planted search vulnerabilities."""

from __future__ import annotations

import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


def build_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE users (username TEXT, role TEXT)")
    conn.executemany(
        "INSERT INTO users VALUES (?, ?)",
        [
            ("alice", "user"),
            ("bob", "user"),
            ("admin", "admin"),
        ],
    )
    return conn


def search_users(query: str) -> list[str]:
    conn = build_db()
    sql = f"SELECT username FROM users WHERE username LIKE '%{query}%'"
    try:
        return [row[0] for row in conn.execute(sql).fetchall()]
    finally:
        conn.close()


def render_search(query: str) -> str:
    users = search_users(query)
    rows = "".join(f"<li>{user}</li>" for user in users)
    return f"""<!doctype html>
<html>
  <body>
    <h1>Search</h1>
    <form action="/search"><input name="q" value="{query}"></form>
    <p>Results for {query}</p>
    <ul>{rows}</ul>
  </body>
</html>
"""


class SearchHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/search":
            self.send_response(404)
            self.end_headers()
            return

        query = parse_qs(parsed.query).get("q", [""])[0]
        body = render_search(query).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8080), SearchHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
