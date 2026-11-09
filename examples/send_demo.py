#!/usr/bin/env python3
import argparse
import json
import socket
from datetime import datetime, timezone


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=55673)
    args = parser.parse_args()
    sample = {
        "type": "PAYLOAD_SUMMARY",
        "station": "SONDE1090-TEST",
        "callsign": "TEST-RS41",
        "latitude": 51.19209,
        "longitude": -1.81665,
        "altitude": 1377.9,
        "speed": 36.3,
        "heading": 228.0,
        "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
        "model": "RS41",
        "freq": "404.401 MHz",
        "vel_v": 4.8,
        "temp": -16.5,
        "comment": "SYNTHETIC TEST - NOT A LIVE RADIOSONDE",
    }
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(json.dumps(sample).encode("utf-8"), (args.host, args.port))
    print(f"Sent synthetic TEST-RS41 to {args.host}:{args.port} (not a real sonde)")


if __name__ == "__main__":
    main()
