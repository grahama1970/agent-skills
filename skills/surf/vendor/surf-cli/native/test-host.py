#!/usr/bin/env python3
import sys
import struct
import json

# Log to file
with open("/tmp/pi-chrome-host.log", "a") as f:
    f.write("Python host starting...\n")

def send_message(message):
    encoded = json.dumps(message).encode('utf-8')
    sys.stdout.buffer.write(struct.pack('I', len(encoded)))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()

# Send ready message
send_message({"type": "HOST_READY"})

with open("/tmp/pi-chrome-host.log", "a") as f:
    f.write("Sent HOST_READY, waiting for messages...\n")

# Read messages
while True:
    try:
        length_bytes = sys.stdin.buffer.read(4)
        if len(length_bytes) == 0:
            break
        length = struct.unpack('I', length_bytes)[0]
        message = sys.stdin.buffer.read(length).decode('utf-8')
        data = json.loads(message)
        with open("/tmp/pi-chrome-host.log", "a") as f:
            f.write(f"Received: {data}\n")
        # Echo back
        send_message({"id": data.get("id"), "success": True})
    except Exception as e:
        with open("/tmp/pi-chrome-host.log", "a") as f:
            f.write(f"Error: {e}\n")
        break

with open("/tmp/pi-chrome-host.log", "a") as f:
    f.write("Host exiting\n")
