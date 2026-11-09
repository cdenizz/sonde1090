import json
from pathlib import Path
import stat
import tempfile
import unittest

from sonde1090.bridge import SondeStore, clean_packet, write_geojson


def packet(**updates):
    sample = {
        "type": "PAYLOAD_SUMMARY", "station": "TEST",
        "callsign": "V5010902", "latitude": 51.19209, "longitude": -1.81665,
        "altitude": 1377.92594, "speed": 36.338868, "heading": 227.96102,
        "time": "05:33:43", "comment": "Radiosonde", "model": "RS41",
        "freq": "404.401 MHz", "temp": -273.0, "vel_v": 4.8,
        "sats": 9, "batt": 2.9,
    }
    sample.update(updates)
    return sample


class TestParser(unittest.TestCase):
    def test_realistic_packet(self):
        result = clean_packet(packet())
        self.assertEqual(result["id"], "V5010902")
        self.assertAlmostEqual(result["speed_kmh"], 36.338868)
        self.assertEqual(result["altitude_m"], 1377.92594)
        self.assertEqual(result["heading_deg"], 227.96102)
        self.assertEqual(result["climb_ms"], 4.8)
        self.assertIsNone(result["temperature_c"])

    def test_invalid_types_or_locations(self):
        for updates in (
            {"type": "CHASE_CAR"}, {"latitude": 999},
            {"latitude": float("nan")}, {"longitude": float("inf")},
            {"latitude": 0.0, "longitude": 0.0},
            {"altitude": "1000"}, {"callsign": ""},
            {"latitude": True},
        ):
            with self.subTest(updates=updates):
                self.assertIsNone(clean_packet(packet(**updates)))

    def test_missing_optional_fields(self):
        p = packet()
        for field in ["speed", "heading", "freq", "model", "vel_v"]:
            p.pop(field)
        r = clean_packet(p)
        self.assertIsNone(r["speed_kmh"])
        self.assertIsNone(r["heading_deg"])
        self.assertIsNone(r["climb_ms"])

    def test_sentinel_values(self):
        r = clean_packet(packet(speed=-1, heading=-1, vel_v=-9999, temp=-273))
        self.assertIsNone(r["speed_kmh"])
        self.assertIsNone(r["heading_deg"])
        self.assertIsNone(r["climb_ms"])
        self.assertIsNone(r["temperature_c"])


class TestStore(unittest.TestCase):
    def test_geojson_multiple_trails(self):
        store = SondeStore(ttl_seconds=10, max_points=3)
        self.assertTrue(store.add(packet(), received=100))
        self.assertTrue(store.add(packet(longitude=-1.81), received=101))
        self.assertTrue(store.add(packet(longitude=-1.80), received=102))
        self.assertTrue(store.add(packet(longitude=-1.79), received=103))
        self.assertTrue(store.add(packet(callsign="OTHER"), received=103))
        geo = store.geojson(now=103)
        points = [f for f in geo["features"] if f["geometry"]["type"] == "Point"]
        lines = [f for f in geo["features"] if f["geometry"]["type"] == "LineString"]
        self.assertEqual(len(points), 2)
        self.assertEqual(len(lines), 1)
        self.assertEqual(len(lines[0]["geometry"]["coordinates"]), 3)
        target = next(p for p in points if p["id"] == "V5010902")
        self.assertEqual(target["properties"]["kind"], "sonde")
        self.assertEqual(target["geometry"]["coordinates"], [-1.79, 51.19209])

    def test_stale_sondes_expire(self):
        store = SondeStore(ttl_seconds=10)
        store.add(packet(), received=100)
        self.assertEqual(len(store.geojson(now=110)["features"]), 1)
        self.assertEqual(store.geojson(now=110.1)["features"], [])

    def test_max_sondes(self):
        store = SondeStore(ttl_seconds=100, max_sondes=2)
        for index in range(3):
            store.add(packet(callsign=str(index)), received=100 + index)
        ids = {f["id"] for f in store.geojson(now=103)["features"]}
        self.assertEqual(ids, {"1", "2"})

    def test_atomic_json_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "target" / "sondes.geojson"
            store = SondeStore()
            store.add(packet(), received=100)
            write_geojson(path, store.geojson(now=100))
            data = json.loads(path.read_text())
            self.assertEqual(data["type"], "FeatureCollection")
            self.assertEqual(len(data["features"]), 1)
            if hasattr(stat, "S_IRGRP"):
                self.assertTrue(path.stat().st_mode & stat.S_IROTH)
            self.assertEqual(list(path.parent.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
