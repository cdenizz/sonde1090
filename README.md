# sonde1090

Show radiosondes decoded by [radiosonde_auto_rx](https://github.com/projecthorus/radiosonde_auto_rx) on your local [tar1090](https://github.com/wiedehopf/tar1090) map.

The bridge listens for Horus `PAYLOAD_SUMMARY` UDP packets and writes a GeoJSON file. A small OpenLayers layer reads that file in tar1090. Aircraft data and readsb are left alone.

## Setup

Requires Python 3.10+ and a working tar1090 installation.

In `radiosonde_auto_rx`'s `station.cfg`, enable the UDP output:

```ini
[oziplotter]
payload_summary_enabled = True
payload_summary_host = <broadcast>
payload_summary_port = 55673
```

If auto_rx is running on another machine, set `payload_summary_host` to the machine running the bridge. Make sure UDP port 55673 is reachable.

Clone the repo and find the directory **actually served** by your tar1090 web server (the one containing `index.html`, `config.js`, and `layers.js`):

```sh
git clone https://github.com/cdenizz/sonde1090.git
cd sonde1090

python3 install_overlay.py /path/to/tar1090/html
python3 -m sonde1090 --output /path/to/tar1090/html/sondes.geojson
```

Refresh tar1090 and open **Map Layers → Custom → Radiosondes**. Markers show the sonde ID; click one to see altitude, speed, model and other received fields. The layer also draws a short position trail.

The installer backs up `index.html` before editing it and can be run again. tar1090 updates may overwrite the changes, so keep this repo handy.

### Check it without a balloon

With the bridge running, open a second terminal:

```sh
python3 examples/send_demo.py
```

This sends a test sonde near **51.19209, -1.81665**. Pan the map there if needed. To check the data without tar1090, run the bridge with `--output ./sondes.geojson` and inspect that file after sending the test packet.

## Docker installations

The bridge must write `sondes.geojson` into a directory that tar1090 actually serves. If tar1090 is containerized, use a writable shared volume and ensure the modified `index.html` and overlay files are also served. Paths depend on the Docker image.

UDP broadcast might not cross Docker's default bridge network. Use a reachable unicast destination or host networking where appropriate.

## Options

```text
python3 -m sonde1090 --help

--host            UDP bind address (default: 0.0.0.0)
--port            UDP port (default: 55673)
--output          GeoJSON output path (default: ./sondes.geojson)
--ttl             Remove sondes after this many seconds (default: 900)
--write-interval  File update interval in seconds (default: 2)
--max-points      Trail length per sonde (default: 240)
--max-sondes      Maximum tracked sondes (default: 100)
--verbose         Log received packets
```

Speed is displayed in km/h, altitude in metres, and climb rate in m/s. Sondes expire based on the time the bridge last received a packet.

## Troubleshooting

- **No layer:** Check that `index.html` loads `sonde-overlay.js` before `layers.js`, then hard-refresh the browser.
- **Layer but no sondes:** Check that `/sondes.geojson` is served at the same path as the tar1090 page and contains a GeoJSON `Point`. Try `examples/send_demo.py`.
- **No UDP packets:** Check the `station.cfg` destination, firewall and container networking. Use `--verbose` for bridge logs.
- **Permission denied:** The bridge needs write access to the served directory. The web server needs read access to `sondes.geojson`.

## Development

```sh
python3 -m unittest discover -s tests -v
node --check tar1090/sonde-overlay.js
```

This has been tested with synthetic UDP telemetry. Feedback from live tar1090/auto_rx installations is welcome.

MIT licensed. See [LICENSE](LICENSE).
