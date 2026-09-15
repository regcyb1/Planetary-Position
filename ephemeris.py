"""
Sidereal (Vedic) planetary position calculator built directly on the
Swiss Ephemeris (the same engine underlying most professional astrology
software, VedAstro included). No dependency on any VedAstro source code.
"""

import os
import swisseph as swe

_EPHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ephe")
swe.set_ephe_path(_EPHE_DIR)

AYANAMSA_MODES = {
    "LAHIRI": swe.SIDM_LAHIRI,
    "RAMAN": swe.SIDM_RAMAN,
    "KRISHNAMURTI": swe.SIDM_KRISHNAMURTI,
    "FAGAN_BRADLEY": swe.SIDM_FAGAN_BRADLEY,
}

RASI_NAMES = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

NAKSHATRA_NAMES = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta",
    "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati",
]

# (name, swisseph body id)
BODIES = [
    ("Sun", swe.SUN),
    ("Moon", swe.MOON),
    ("Mars", swe.MARS),
    ("Mercury", swe.MERCURY),
    ("Jupiter", swe.JUPITER),
    ("Venus", swe.VENUS),
    ("Saturn", swe.SATURN),
]


def _deg_to_dms(deg_in_sign: float) -> str:
    d = int(deg_in_sign)
    m_full = (deg_in_sign - d) * 60
    m = int(m_full)
    s = round((m_full - m) * 60)
    if s == 60:
        s = 0
        m += 1
    if m == 60:
        m = 0
        d += 1
    return f"{d}°{m:02d}'{s:02d}\""


def rasi_and_degree(longitude: float):
    longitude = longitude % 360
    rasi_index = int(longitude // 30)
    deg_in_sign = longitude - rasi_index * 30
    return RASI_NAMES[rasi_index], deg_in_sign, _deg_to_dms(deg_in_sign)


def nakshatra(longitude: float):
    longitude = longitude % 360
    span = 360 / 27  # 13deg20'
    index = int(longitude // span)
    deg_in_nak = longitude - index * span
    pada = int(deg_in_nak // (span / 4)) + 1
    return NAKSHATRA_NAMES[index], pada


def julian_day_ut(year: int, month: int, day: int,
                   hour: int, minute: int, second: float,
                   utc_offset_hours: float) -> float:
    """
    Converts a local civil date/time + UTC offset into Julian Day (UT1),
    the time base Swiss Ephemeris requires. Uses Swiss Ephemeris's own
    Gregorian calendar + UTC conversion so leap seconds / calendar edge
    cases are handled exactly the way the ephemeris expects.
    """
    local_decimal_hour = hour + minute / 60 + second / 3600
    utc_decimal_hour = local_decimal_hour - utc_offset_hours

    # roll the date if the UTC offset pushes hour outside 0-24
    jd_local_midnight = swe.julday(year, month, day, 0.0, swe.GREG_CAL)
    jd_ut = jd_local_midnight + utc_decimal_hour / 24.0
    return jd_ut


def calculate_chart(year: int, month: int, day: int,
                     hour: int, minute: int, second: float,
                     utc_offset_hours: float,
                     latitude: float, longitude: float,
                     ayanamsa: str = "LAHIRI",
                     true_node: bool = True) -> dict:
    """
    Returns sidereal (Nirayana) positions for the 9 classical grahas
    (Sun..Saturn, Rahu, Ketu) for the given birth data.

    true_node=True uses the astronomically real (osculating) lunar node,
    which is what most modern Vedic software defaults to; set False for
    the mean node if you specifically want that convention instead.
    """
    if ayanamsa.upper() not in AYANAMSA_MODES:
        raise ValueError(f"Unknown ayanamsa '{ayanamsa}'. Options: {list(AYANAMSA_MODES)}")

    swe.set_sid_mode(AYANAMSA_MODES[ayanamsa.upper()])

    jd_ut = julian_day_ut(year, month, day, hour, minute, second, utc_offset_hours)

    flags = swe.FLG_SIDEREAL | swe.FLG_SWIEPH | swe.FLG_SPEED

    results = {}
    used_fallback = False

    for name, body_id in BODIES:
        (lon, lat, dist, lon_speed, lat_speed, dist_speed), retflag = swe.calc_ut(jd_ut, body_id, flags)
        if not (retflag & swe.FLG_SWIEPH):
            used_fallback = True
        rasi, deg_in_sign, dms = rasi_and_degree(lon)
        nak, pada = nakshatra(lon)
        results[name] = {
            "longitude": round(lon, 6),
            "latitude": round(lat, 6),
            "distance_au": round(dist, 8),
            "speed_deg_per_day": round(lon_speed, 6),
            "rasi": rasi,
            "degree_in_sign": round(deg_in_sign, 4),
            "dms": dms,
            "nakshatra": nak,
            "pada": pada,
            "retrograde": lon_speed < 0,
        }

    node_id = swe.TRUE_NODE if true_node else swe.MEAN_NODE
    (rahu_lon, rahu_lat, rahu_dist, rahu_speed, *_rest), retflag = swe.calc_ut(jd_ut, node_id, flags)
    if not (retflag & swe.FLG_SWIEPH):
        used_fallback = True
    rahu_lon = rahu_lon % 360
    ketu_lon = (rahu_lon + 180) % 360

    for name, lon, speed in (("Rahu", rahu_lon, rahu_speed), ("Ketu", ketu_lon, rahu_speed)):
        rasi, deg_in_sign, dms = rasi_and_degree(lon)
        nak, pada = nakshatra(lon)
        results[name] = {
            "longitude": round(lon, 6),
            "latitude": 0.0,
            "distance_au": None,
            "speed_deg_per_day": round(speed, 6),
            "rasi": rasi,
            "degree_in_sign": round(deg_in_sign, 4),
            "dms": dms,
            "nakshatra": nak,
            "pada": pada,
            "retrograde": True,  # nodes are always retrograde in this convention
        }

    ayanamsa_value = swe.get_ayanamsa_ut(jd_ut)

    # Ascendant / Lagna (needs geographic location, not just time)
    cusps, ascmc = swe.houses_ex(jd_ut, latitude, longitude, b'P', flags=swe.FLG_SIDEREAL)
    asc_lon = ascmc[0] % 360
    asc_rasi, asc_deg, asc_dms = rasi_and_degree(asc_lon)
    asc_nak, asc_pada = nakshatra(asc_lon)
    results["Ascendant"] = {
        "longitude": round(asc_lon, 6),
        "latitude": 0.0,
        "distance_au": None,
        "speed_deg_per_day": None,
        "rasi": asc_rasi,
        "degree_in_sign": round(asc_deg, 4),
        "dms": asc_dms,
        "nakshatra": asc_nak,
        "pada": asc_pada,
        "retrograde": False,
    }

    return {
        "julian_day_ut": jd_ut,
        "ayanamsa": ayanamsa.upper(),
        "ayanamsa_value": round(ayanamsa_value, 6),
        "used_fallback_moshier": used_fallback,
        "planets": results,
    }
