from __future__ import annotations

import argparse
import json
import logging
import math
import os
from pathlib import Path
import socket
import tempfile
import time
from typing import Any
from datetime import datetime, timezone

LOG = logging.getLogger("sonde1090")


def valid_number(value: Any, *, low: float | None = None, high: float | None = None) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    if not math.isfinite(result):
        return None
    if low is not None and result < low:
        return None
    if high is not None and result > high:
        return None
    return result


def clean_optional(value: Any, low: float, high: float, invalid: tuple[float, ...] = ()) -> float | None:
    result = valid_number(value, low=low, high=high)
    if result is None or result in invalid:
        return None
    return result


def clean_packet(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict) or data.get("type") != "PAYLOAD_SUMMARY":
        return None
    serial = data.get("callsign")
    if not isinstance(serial, str) or not serial.strip() or len(serial) > 100:
        return None
    lat = valid_number(data.get("latitude"), low=-90, high=90)
    lon = valid_number(data.get("longitude"), low=-180, high=180)
    alt = valid_number(data.get("altitude"), low=-1000, high=100000)
    if lat is None or lon is None or alt is None or (lat == 0 and lon == 0):
        return None

    speed = clean_optional(data.get("speed"), 0, 2000, (-1,))
    heading = clean_optional(data.get("heading"), 0, 360, (-1,))
    climb = clean_optional(data.get("vel_v"), -200, 200, (-9999,))
    temp = clean_optional(data.get("temp"), -150, 100, (-273, -273.0))
    humidity = clean_optional(data.get("humidity"), 0, 100, (-1,))
    battery = clean_optional(data.get("batt"), 0, 50, (-1,))
    frequency = data.get("freq")
    if frequency is not None and not isinstance(frequency, str):
        frequency = None
    model = data.get("model")
    if model is not None and not isinstance(model, str):
        model = None
    return {
        "id": serial.strip(),
        "lat": lat, "lon": lon, "altitude_m": alt,
        "speed_kmh": speed,
        "heading_deg": heading,
        "climb_ms": climb,
        "temperature_c": temp,
        "humidity_pct": humidity,
        "battery_v": battery,
        "model": model[:60] if model else None,
        "frequency": frequency[:60] if frequency else None,
    }


class SondeStore:
    def __init__(self, ttl_seconds: float = 900, max_points: int = 240, max_sondes: int = 100):
        if ttl_seconds <= 0 or max_points < 2 or max_sondes < 1:
            raise ValueError("TTL must be positive, max-points >= 2 and max-sondes >= 1")
        self.ttl_seconds = ttl_seconds
        self.max_points = max_points
        self.max_sondes = max_sondes
        self._sondes: dict[str, dict[str, Any]] = {}

    def add(self, data: Any, received: float | None = None) -> bool:
        record = clean_packet(data)
        if record is None:
            return False
        now = time.time() if received is None else received
        self.prune(now)
        sid = record["id"]
        if sid not in self._sondes and len(self._sondes) >= self.max_sondes:
            oldest = min(self._sondes, key=lambda key: self._sondes[key]["seen"])
            del self._sondes[oldest]
        entry = self._sondes.get(sid)
        if entry is None:
            entry = {"record": record, "seen": now, "trail": []}
            self._sondes[sid] = entry
        entry["record"] = record
        entry["seen"] = now
        trail = entry["trail"]
        point = [record["lon"], record["lat"]]
        if not trail or point != trail[-1]:
            trail.append(point)
            if len(trail) > self.max_points:
                del trail[: len(trail) - self.max_points]
        return True

    def prune(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        for sid in list(self._sondes):
            if now - self._sondes[sid]["seen"] > self.ttl_seconds:
                del self._sondes[sid]

    def geojson(self, now: float | None = None) -> dict[str, Any]:
        now = time.time() if now is None else now
        self.prune(now)
        features = []
        for sid, entry in sorted(self._sondes.items()):
            record = entry["record"]
            props = {key: value for key, value in record.items() if key not in ("lat", "lon")}
            props["received_utc"] = datetime.fromtimestamp(entry["seen"], timezone.utc).isoformat()
            props["age_seconds"] = round(max(0, now - entry["seen"]), 1)
            if len(entry["trail"]) >= 2:
                features.append({
                    "type": "Feature", "id": sid + ":trail",
                    "geometry": {"type": "LineString", "coordinates": entry["trail"]},
                    "properties": {"id": sid, "kind": "trail"},
                })
            features.append({
                "type": "Feature", "id": sid,
                "geometry": {"type": "Point", "coordinates": [record["lon"], record["lat"]]},
                "properties": {**props, "kind": "sonde"},
            })
        return {"type": "FeatureCollection", "features": features}


def write_geojson(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(data, ensure_ascii=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    fd, tmp_name = tempfile.mkstemp(prefix=".sonde1090-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
        os.chmod(tmp_name, 0o644)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def parse_forward_target(value: str) -> tuple[str, int]:
    host, sep, port_text = value.rpartition(":")
    if not sep or not host or not port_text.isdecimal():
        raise argparse.ArgumentTypeError("expected HOST:PORT")
    port = int(port_text)
    if not 1 <= port <= 65535 or host == "0.0.0.0":
        raise argparse.ArgumentTypeError("invalid forward destination")
    return host, port


def forward_packet(packet: bytes, sock: socket.socket, targets: list[tuple[str, int]]) -> None:
    for target in targets:
        try:
            sock.sendto(packet, target)
        except OSError as exc:
            LOG.warning("Could not forward UDP to %s:%d: %s", *target, exc)


def run(args: argparse.Namespace) -> None:
    output = Path(args.output).expanduser().resolve()
    store = SondeStore(args.ttl, args.max_points, args.max_sondes)
    write_geojson(output, store.geojson())
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as relay:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((args.host, args.port))
        sock.settimeout(min(args.write_interval, 1.0))
        LOG.info("Listening for Horus UDP on %s:%s", args.host, args.port)
        LOG.info("Publishing GeoJSON to %s", output)
        for target in args.forward:
            LOG.info("Forwarding UDP to %s:%d", *target)
        last_write = time.monotonic()
        dirty = False
        while True:
            try:
                packet, _ = sock.recvfrom(65535)
                if args.forward:
                    forward_packet(packet, relay, args.forward)
                try:
                    payload = json.loads(packet)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    LOG.debug("Ignored invalid JSON datagram")
                    continue
                if store.add(payload):
                    dirty = True
                    LOG.debug("Received %s", payload.get("callsign"))
            except socket.timeout:
                pass
            if time.monotonic() - last_write >= args.write_interval:
                write_geojson(output, store.geojson())
                if dirty:
                    LOG.info("Updated map (%s radiosondes)", len(store._sondes))
                dirty = False
                last_write = time.monotonic()


def main() -> None:
    parser = argparse.ArgumentParser(description="Horus UDP radiosondes -> tar1090 GeoJSON overlay")
    parser.add_argument("--host", default="0.0.0.0", help="UDP listening address (default 0.0.0.0)")
    parser.add_argument("--port", type=int, default=55673, help="UDP listening port (default 55673)")
    parser.add_argument("--output", default="./sondes.geojson", help="Path served by tar1090")
    parser.add_argument("--ttl", type=float, default=900, help="Remove stale sondes after N seconds")
    parser.add_argument("--write-interval", type=float, default=2.0, help="GeoJSON publishing interval")
    parser.add_argument("--max-points", type=int, default=240, help="Maximum trail positions per sonde")
    parser.add_argument("--max-sondes", type=int, default=100, help="Maximum simultaneously tracked sondes")
    parser.add_argument("--forward", type=parse_forward_target, action="append", default=[], metavar="HOST:PORT", help="Forward raw UDP packets to another listener; repeat for more")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    if not (1 <= args.port <= 65535) or args.write_interval <= 0:
        parser.error("port must be 1..65535 and write-interval must be positive")
    for host, port in args.forward:
        if port == args.port and host.lower() in ("localhost", "127.0.0.1", args.host.lower()):
            parser.error("forward destination points to the bridge itself")
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    try:
        run(args)
    except KeyboardInterrupt:
        LOG.info("Stopped")
    except (OSError, ValueError) as exc:
        parser.exit(1, f"sonde1090: {exc}\n")


if __name__ == "__main__":
    main()
