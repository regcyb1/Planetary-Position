import csv
import io
import json
import re
from datetime import datetime, timedelta, timezone
from flask import Flask, Response, render_template, request

from ephemeris import calculate_chart, AYANAMSA_MODES
from vedic import houses, divisional_charts, vimshottari_dasha, panchang

app = Flask(__name__)


class InputError(ValueError):
    pass


def parse_date(text: str):
    text = text.strip()
    m = re.match(r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})$", text)
    if not m:
        raise InputError(f"Date '{text}' not understood. Use dd/mm/yyyy.")
    day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= month <= 12):
        raise InputError(f"Month {month} out of range in '{text}'.")
    if not (1 <= day <= 31):
        raise InputError(f"Day {day} out of range in '{text}'.")
    return year, month, day


def parse_clock(text: str):
    text = text.strip()
    m = re.match(r"^(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?$", text)
    if not m:
        raise InputError(f"Time '{text}' not understood. Use HH:mm (24h).")
    hour, minute = int(m.group(1)), int(m.group(2))
    second = int(m.group(3)) if m.group(3) else 0
    if not (0 <= hour <= 23):
        raise InputError(f"Hour {hour} out of range in '{text}'.")
    if not (0 <= minute <= 59):
        raise InputError(f"Minute {minute} out of range in '{text}'.")
    return hour, minute, second


def parse_offset(text: str):
    text = text.strip()
    m = re.match(r"^([+-]?)(\d{1,2}):(\d{1,2})$", text)
    if not m:
        raise InputError(f"UTC offset '{text}' not understood. Use +HH:mm or -HH:mm.")
    sign = -1 if m.group(1) == "-" else 1
    hours, minutes = int(m.group(2)), int(m.group(3))
    if hours > 14 or minutes > 59:
        raise InputError(f"UTC offset '{text}' out of plausible range.")
    return sign * (hours + minutes / 60)


def parse_float(text: str, label: str, lo: float, hi: float):
    text = text.strip()
    try:
        val = float(text)
    except ValueError:
        raise InputError(f"{label} '{text}' is not a number.")
    if not (lo <= val <= hi):
        raise InputError(f"{label} {val} out of range ({lo} to {hi}).")
    return val


DEFAULTS = {
    "date": "16/10/1990",
    "time": "14:20",
    "offset": "+05:45",
    "location": "Kathmandu, Nepal",
    "latitude": "27.7172",
    "longitude": "85.3240",
    "ayanamsa": "LAHIRI",
    "node": "true",
}


PLANET_ORDER = ["Ascendant", "Sun", "Moon", "Mars", "Mercury",
                "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]


def parse_and_calculate(form_values: dict):
    """Shared by both pages so the extended chart is always derived from
    the exact same core calculation the Planetary Positions page shows."""
    year, month, day = parse_date(form_values["date"])
    hour, minute, second = parse_clock(form_values["time"])
    utc_offset = parse_offset(form_values["offset"])
    latitude = parse_float(form_values["latitude"], "Latitude", -90, 90)
    longitude = parse_float(form_values["longitude"], "Longitude", -180, 180)
    ayanamsa = form_values["ayanamsa"]
    if ayanamsa not in AYANAMSA_MODES:
        raise InputError(f"Unknown ayanamsa '{ayanamsa}'.")
    true_node = form_values["node"] == "true"

    result = calculate_chart(
        year, month, day, hour, minute, second,
        utc_offset, latitude, longitude,
        ayanamsa=ayanamsa, true_node=true_node,
    )

    birth_utc = datetime(year, month, day, hour, minute, int(second)) - timedelta(hours=utc_offset)
    return result, birth_utc


@app.route("/", methods=["GET", "POST"])
def index():
    form_values = dict(DEFAULTS)
    result = None
    error = None

    if request.method == "POST":
        form_values.update({k: request.form.get(k, v) for k, v in DEFAULTS.items()})
        try:
            result, _birth_utc = parse_and_calculate(form_values)
        except InputError as e:
            error = str(e)
        except Exception as e:
            error = f"Calculation failed: {e}"

    return render_template(
        "index.html",
        values=form_values,
        result=result,
        error=error,
        ayanamsa_options=list(AYANAMSA_MODES.keys()),
        planet_order=PLANET_ORDER,
    )


@app.route("/extended", methods=["GET", "POST"])
def extended():
    form_values = dict(DEFAULTS)
    result = None
    house_data = None
    varga_data = None
    dasha_data = None
    panchang_data = None
    error = None

    if request.method == "POST":
        form_values.update({k: request.form.get(k, v) for k, v in DEFAULTS.items()})
        try:
            result, birth_utc = parse_and_calculate(form_values)

            asc_rasi = result["planets"]["Ascendant"]["rasi"]
            planet_only = {k: v for k, v in result["planets"].items() if k != "Ascendant"}

            house_data = houses(asc_rasi, planet_only)
            varga_data = divisional_charts(planet_only)
            dasha_data = vimshottari_dasha(result["planets"]["Moon"]["longitude"], birth_utc)
            panchang_data = panchang(
                result["planets"]["Sun"]["longitude"],
                result["planets"]["Moon"]["longitude"],
                birth_utc,
            )
        except InputError as e:
            error = str(e)
        except Exception as e:
            error = f"Calculation failed: {e}"

    return render_template(
        "extended.html",
        values=form_values,
        result=result,
        house_data=house_data,
        varga_data=varga_data,
        dasha_data=dasha_data,
        panchang_data=panchang_data,
        error=error,
        ayanamsa_options=list(AYANAMSA_MODES.keys()),
        planet_order=[p for p in PLANET_ORDER if p != "Ascendant"],
    )


def _export_metadata(form_values: dict, result: dict) -> dict:
    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Swiss Ephemeris (pyswisseph), Lahiri-family sidereal calculation",
        "birth_date": form_values["date"],
        "birth_time": form_values["time"],
        "utc_offset": form_values["offset"],
        "location_name": form_values["location"],
        "latitude": form_values["latitude"],
        "longitude": form_values["longitude"],
        "ayanamsa": result["ayanamsa"],
        "ayanamsa_value_deg": result["ayanamsa_value"],
        "julian_day_ut": result["julian_day_ut"],
        "used_fallback_moshier": result["used_fallback_moshier"],
    }


@app.route("/export/<fmt>")
def export(fmt):
    form_values = dict(DEFAULTS)
    form_values.update({k: request.args.get(k, v) for k, v in DEFAULTS.items()})

    try:
        result, _birth_utc = parse_and_calculate(form_values)
    except InputError as e:
        return Response(f"Input error: {e}", status=400, mimetype="text/plain")
    except Exception as e:
        return Response(f"Calculation failed: {e}", status=400, mimetype="text/plain")

    stamp = f"{form_values['date'].replace('/', '-')}_{form_values['time'].replace(':', '')}"
    metadata = _export_metadata(form_values, result)

    if fmt == "json":
        payload = {"metadata": metadata, "planets": result["planets"]}
        body = json.dumps(payload, indent=2, ensure_ascii=False)
        return Response(
            body, mimetype="application/json",
            headers={"Content-Disposition": f"attachment; filename=planetary_position_{stamp}.json"},
        )

    if fmt == "csv":
        buf = io.StringIO()
        for k, v in metadata.items():
            buf.write(f"# {k}: {v}\n")
        writer = csv.writer(buf)
        columns = ["planet", "longitude_deg", "latitude_deg", "distance_au",
                   "speed_deg_per_day", "retrograde", "rasi", "degree_in_sign",
                   "dms", "nakshatra", "pada"]
        writer.writerow(columns)
        for name in PLANET_ORDER:
            p = result["planets"][name]
            writer.writerow([
                name, p["longitude"], p["latitude"], p["distance_au"],
                p["speed_deg_per_day"], p["retrograde"], p["rasi"],
                p["degree_in_sign"], p["dms"], p["nakshatra"], p["pada"],
            ])
        return Response(
            buf.getvalue(), mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=planetary_position_{stamp}.csv"},
        )

    return Response(f"Unknown format '{fmt}'. Use json or csv.", status=400, mimetype="text/plain")


@app.route("/export-extended/json")
def export_extended():
    form_values = dict(DEFAULTS)
    form_values.update({k: request.args.get(k, v) for k, v in DEFAULTS.items()})

    try:
        result, birth_utc = parse_and_calculate(form_values)
        asc_rasi = result["planets"]["Ascendant"]["rasi"]
        planet_only = {k: v for k, v in result["planets"].items() if k != "Ascendant"}

        payload = {
            "metadata": _export_metadata(form_values, result),
            "planets": result["planets"],
            "houses": houses(asc_rasi, planet_only),
            "divisional_charts": divisional_charts(planet_only),
            "vimshottari_dasha": vimshottari_dasha(result["planets"]["Moon"]["longitude"], birth_utc),
            "panchang": panchang(
                result["planets"]["Sun"]["longitude"],
                result["planets"]["Moon"]["longitude"],
                birth_utc,
            ),
        }
    except InputError as e:
        return Response(f"Input error: {e}", status=400, mimetype="text/plain")
    except Exception as e:
        return Response(f"Calculation failed: {e}", status=400, mimetype="text/plain")

    stamp = f"{form_values['date'].replace('/', '-')}_{form_values['time'].replace(':', '')}"
    body = json.dumps(payload, indent=2, ensure_ascii=False)
    return Response(
        body, mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename=vedic_chart_{stamp}.json"},
    )


if __name__ == "__main__":
    app.run(debug=True, port=5001)
