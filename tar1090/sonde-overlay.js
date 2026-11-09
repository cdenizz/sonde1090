(function () {
    "use strict";
    if (typeof ol === "undefined" || typeof custom_layers === "undefined") {
        console.error("Sonde1090 must be included after config.js and before layers.js");
        return;
    }

    const source = new ol.source.Vector();
    const pointStyle = new ol.style.Style({
        image: new ol.style.Circle({
            radius: 8,
            fill: new ol.style.Fill({ color: "#ffba45" }),
            stroke: new ol.style.Stroke({ color: "#292521", width: 2 })
        }),
        text: new ol.style.Text({
            offsetY: -19,
            font: "bold 12px sans-serif",
            fill: new ol.style.Fill({ color: "#ffffff" }),
            stroke: new ol.style.Stroke({ color: "#222222", width: 3 })
        })
    });
    const trailStyle = new ol.style.Style({
        stroke: new ol.style.Stroke({ color: "#ffba45", width: 2, lineDash: [5, 4] })
    });
    const layer = new ol.layer.Vector({
        title: "Radiosondes",
        name: "sonde1090",
        type: "overlay",
        visible: true,
        zIndex: 110,
        source: source,
        style: function (feature) {
            if (feature.get("kind") === "trail") return trailStyle;
            const label = String(feature.get("id") || "Sonde").slice(0, 35);
            const style = pointStyle.clone();
            style.getText().setText(label);
            return style;
        }
    });
    custom_layers.push(layer);

    let lastSuccess = 0;
    let busy = false;
    const format = new ol.format.GeoJSON();
    async function refresh() {
        if (busy) return;
        busy = true;
        try {
            const response = await fetch("sondes.geojson?_=" + Date.now(), { cache: "no-store" });
            if (!response.ok) throw new Error("HTTP " + response.status);
            const json = await response.json();
            if (json.type !== "FeatureCollection" || !Array.isArray(json.features)) {
                throw new Error("Invalid GeoJSON response");
            }
            const features = format.readFeatures(json, { featureProjection: "EPSG:3857" });
            source.clear(true);
            source.addFeatures(features);
            lastSuccess = Date.now();
        } catch (error) {
            if (Date.now() - lastSuccess > 30000) source.clear(true);
            console.debug("Sonde1090: no fresh GeoJSON", error);
        } finally {
            busy = false;
        }
    }
    refresh();
    setInterval(refresh, 3000);

    function addPopup(map) {
        const element = document.createElement("div");
        element.className = "sonde1090-popup";
        element.style.display = "none";
        const popup = new ol.Overlay({
            element: element,
            positioning: "bottom-center",
            offset: [0, -18],
            stopEvent: false
        });
        map.addOverlay(popup);
        map.on("singleclick", function (evt) {
            let match = null;
            map.forEachFeatureAtPixel(evt.pixel, function (feature, foundLayer) {
                if (foundLayer === layer && feature.get("kind") === "sonde") {
                    match = feature;
                    return feature;
                }
            });
            if (!match) {
                element.style.display = "none";
                popup.setPosition(undefined);
                return;
            }
            element.replaceChildren();
            const title = document.createElement("strong");
            title.textContent = String(match.get("id") || "Radiosonde");
            element.appendChild(title);
            const rows = [
                ["Model", match.get("model")],
                ["Frequency", match.get("frequency")],
                ["Altitude", fmt(match.get("altitude_m"), "m")],
                ["Speed", fmt(match.get("speed_kmh"), "km/h")],
                ["Heading", fmt(match.get("heading_deg"), "°")],
                ["Climb", fmt(match.get("climb_ms"), "m/s")],
                ["Temperature", fmt(match.get("temperature_c"), "°C")],
                ["Received", match.get("received_utc")]
            ];
            rows.forEach(function (item) {
                if (item[1] === null || item[1] === undefined || item[1] === "") return;
                const line = document.createElement("div");
                line.textContent = item[0] + ": " + item[1];
                element.appendChild(line);
            });
            element.style.display = "block";
            popup.setPosition(match.getGeometry().getCoordinates());
        });
    }
    function fmt(value, suffix) {
        return typeof value === "number" && Number.isFinite(value) ?
            Math.round(value * 10) / 10 + " " + suffix : null;
    }

    document.addEventListener("DOMContentLoaded", function () {
        let attempts = 0;
        const timer = setInterval(function () {
            attempts++;
            if (typeof OLMap !== "undefined" && OLMap) {
                clearInterval(timer);
                addPopup(OLMap);
            } else if (attempts > 120) {
                clearInterval(timer);
            }
        }, 500);
    });
})();
