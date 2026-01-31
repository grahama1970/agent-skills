from http.server import BaseHTTPRequestHandler, HTTPServer
import sys
import threading
import time

PORT = 9999
FAILURES = 2
count = 0

class FlakyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global count
        if count < FAILURES:
            count += 1
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"Fail")
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Success")

def run_server():
    server = HTTPServer(('localhost', PORT), FlakyHandler)
    server.handle_request() # Handle 1
    server.handle_request() # Handle 2
    server.handle_request() # Handle 3 (Success)
    server.server_close()

if __name__ == "__main__":
    run_server()
