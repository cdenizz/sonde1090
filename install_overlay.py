#!/usr/bin/env python3
import argparse
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone

JS_TAG = '<script src="sonde-overlay.js"></script>'
CSS_TAG = '<link rel="stylesheet" href="sonde-overlay.css" type="text/css">'
ANCHOR = '<script src="config.js"></script>'


def install(html_dir: Path):
    html_dir = html_dir.resolve()
    index = html_dir / "index.html"
    if not index.is_file():
        raise ValueError(f"No index.html at {index}; supply the tar1090 HTML directory")
    original = index.read_text(encoding="utf-8-sig")
    if ANCHOR not in original and JS_TAG not in original:
        raise ValueError("Cannot locate tar1090 config.js script tag; unsupported index.html layout")
    if "</head>" not in original:
        raise ValueError("Cannot find the HTML head closing tag")
    if '<script src="layers.js"></script>' in original and original.find(ANCHOR) > original.find('<script src="layers.js"></script>'):
        raise ValueError("config.js must load before layers.js")
    source = Path(__file__).resolve().parent / "tar1090"
    modified = original
    if JS_TAG not in modified:
        modified = modified.replace(ANCHOR, ANCHOR + "\n    " + JS_TAG, 1)
    if CSS_TAG not in modified:
        modified = modified.replace('</head>', '  ' + CSS_TAG + '\n  </head>', 1)
    if modified != original:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = index.with_name("index.html.sonde1090." + stamp + ".bak")
        shutil.copy2(index, backup)
        index.write_text(modified, encoding="utf-8")
        print(f"Backed up index.html to {backup}")
    for name in ("sonde-overlay.js", "sonde-overlay.css"):
        shutil.copy2(source / name, html_dir / name)
    print("Overlay installed. GeoJSON output should be:", html_dir / "sondes.geojson")
    print("Refresh tar1090 (Ctrl+F5) after bridge starts.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("html_dir", type=Path, help="Writable tar1090 HTML directory containing index.html")
    args = parser.parse_args()
    try:
        install(args.html_dir)
    except (OSError, ValueError) as error:
        sys.exit(f"Installation failed: {error}")


if __name__ == "__main__":
    main()
