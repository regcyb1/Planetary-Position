"""
Extended Vedic chart layer, built strictly on top of the core Swiss
Ephemeris positions from ephemeris.calculate_chart(). This module never
touches Swiss Ephemeris directly and never recomputes a planetary
longitude -- it only derives further classical rules (houses, dasha,
vargas, panchang) from the longitudes that module already produced.
Keeping this separation means the core planetary-position numbers stay
byte-for-byte whatever Swiss Ephemeris says, regardless of what happens
in this file.
"""

from datetime import datetime, timedelta, timezone

from ephemeris import RASI_NAMES, NAKSHATRA_NAMES, rasi_and_degree, nakshatra

SIGN_LORDS = {
    "Aries": "Mars", "Taurus": "Venus", "Gemini": "Mercury", "Cancer": "Moon",
    "Leo": "Sun", "Virgo": "Mercury", "Libra": "Venus", "Scorpio": "Mars",
    "Sagittarius": "Jupiter", "Capricorn": "Saturn", "Aquarius": "Saturn",
    "Pisces": "Jupiter",
}

DASHA_SEQUENCE = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]
DASHA_YEARS = {"Ketu": 7, "Venus": 20, "Sun": 6, "Moon": 10, "Mars": 7,
               "Rahu": 18, "Jupiter": 16, "Saturn": 19, "Mercury": 17}
DASHA_TOTAL_YEARS = sum(DASHA_YEARS.values())  # 120
YEAR_DAYS = 365.2425  # Gregorian mean year, standard convention used by dasha software

WEEKDAY_LORDS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

TITHI_NAMES = ["Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami", "Shashthi",
               "Saptami", "Ashtami", "Navami", "Dashami", "Ekadashi", "Dwadashi",
               "Trayodashi", "Chaturdashi"]

YOGA_NAMES = ["Vishkambha", "Priti", "Ayushman", "Saubhagya", "Shobhana", "Atiganda",
              "Sukarma", "Dhriti", "Shula", "Ganda", "Vriddhi", "Dhruva", "Vyaghata",
              "Harshana", "Vajra", "Siddhi", "Vyatipata", "Variyana", "Parigha", "Shiva",
              "Siddha", "Sadhya", "Shubha", "Shukla", "Brahma", "Indra", "Vaidhriti"]

KARANA_MOVABLE = ["Bava", "Balava", "Kaulava", "Taitila", "Gara", "Vanija", "Vishti"]


# ---------- Houses (whole-sign system, the classical Parashari default) ----------

def houses(ascendant_rasi: str, planet_positions: dict) -> dict:
    """
    planet_positions: {name: {"rasi": ..., ...}} as produced by calculate_chart.
    Returns {name: {"house": 1-12, "rasi": ..., "house_lord": ...}}.
    """
    asc_index = RASI_NAMES.index(ascendant_rasi)
    result = {}
    for name, data in planet_positions.items():
        planet_rasi_index = RASI_NAMES.index(data["rasi"])
        house_num = (planet_rasi_index - asc_index) % 12 + 1
        result[name] = {"house": house_num, "rasi": data["rasi"]}

    house_signs = {}
    for house_num in range(1, 13):
        sign = RASI_NAMES[(asc_index + house_num - 1) % 12]
        house_signs[house_num] = {"sign": sign, "lord": SIGN_LORDS[sign]}

    return {"planet_houses": result, "house_signs": house_signs}


# ---------- Divisional charts (Vargas) ----------

def navamsa_sign(longitude: float) -> str:
    """D9. Verified formula: navamsa_index = (rasi_index*9 + part) mod 12,
    part = which 3d20' division (0-8) the longitude falls in within its sign."""
    longitude = longitude % 360
    rasi_index = int(longitude // 30)
    deg_in_sign = longitude - rasi_index * 30
    part = int(deg_in_sign // (30 / 9))
    return RASI_NAMES[(rasi_index * 9 + part) % 12]


def dasamsa_sign(longitude: float) -> str:
    """D10. Classical rule: odd signs (Aries, Gemini, ...) count from
    themselves; even signs (Taurus, Cancer, ...) count from the 9th sign
    from themselves. 10 divisions of 3 degrees each."""
    longitude = longitude % 360
    rasi_index = int(longitude // 30)
    deg_in_sign = longitude - rasi_index * 30
    part = int(deg_in_sign // 3)
    start = rasi_index if rasi_index % 2 == 0 else (rasi_index + 8) % 12
    return RASI_NAMES[(start + part) % 12]


def divisional_charts(planet_positions: dict) -> dict:
    result = {}
    for name, data in planet_positions.items():
        lon = data["longitude"]
        result[name] = {
            "D9_navamsa": navamsa_sign(lon),
            "D10_dasamsa": dasamsa_sign(lon),
        }
    return result


# ---------- Vimshottari Dasha ----------

def vimshottari_dasha(moon_longitude: float, birth_datetime_utc: datetime,
                       years_to_project: float = 120.0):
    nak_span = 360 / 27
    moon_longitude = moon_longitude % 360
    nak_index = int(moon_longitude // nak_span)
    deg_in_nak = moon_longitude - nak_index * nak_span
    fraction_traversed = deg_in_nak / nak_span

    birth_lord = DASHA_SEQUENCE[nak_index % 9]
    lord_pos = DASHA_SEQUENCE.index(birth_lord)

    first_maha_years_remaining = DASHA_YEARS[birth_lord] * (1 - fraction_traversed)

    mahadashas = []
    cursor = birth_datetime_utc
    remaining_years = years_to_project
    idx = lord_pos
    first = True

    while remaining_years > 0:
        lord = DASHA_SEQUENCE[idx % 9]
        duration_years = first_maha_years_remaining if first else DASHA_YEARS[lord]
        duration_years = min(duration_years, remaining_years)
        start = cursor
        end = cursor + timedelta(days=duration_years * YEAR_DAYS)

        # antardashas: sub-periods within this mahadasha, same 9-sequence
        # starting at the mahadasha's own lord, each sized proportionally
        antardashas = []
        a_cursor = start
        full_maha_years = first_maha_years_remaining if first else DASHA_YEARS[lord]
        for a_offset in range(9):
            a_lord = DASHA_SEQUENCE[(DASHA_SEQUENCE.index(lord) + a_offset) % 9]
            a_years = full_maha_years * DASHA_YEARS[a_lord] / DASHA_TOTAL_YEARS
            a_start = a_cursor
            a_end = a_cursor + timedelta(days=a_years * YEAR_DAYS)
            if a_end > end:
                a_end = end
            antardashas.append({
                "lord": a_lord,
                "start": a_start.strftime("%d/%m/%Y"),
                "end": a_end.strftime("%d/%m/%Y"),
            })
            a_cursor = a_end
            if a_cursor >= end:
                break

        mahadashas.append({
            "lord": lord,
            "start": start.strftime("%d/%m/%Y"),
            "end": end.strftime("%d/%m/%Y"),
            "years": round(duration_years, 2),
            "antardashas": antardashas,
        })

        cursor = end
        remaining_years -= duration_years
        idx += 1
        first = False

    return {"birth_nakshatra_lord": birth_lord, "mahadashas": mahadashas}


# ---------- Panchang ----------

def panchang(sun_longitude: float, moon_longitude: float, local_datetime) -> dict:
    sun_longitude = sun_longitude % 360
    moon_longitude = moon_longitude % 360
    diff = (moon_longitude - sun_longitude) % 360

    tithi_num_1_based = int(diff // 12) + 1  # 1-30
    paksha = "Shukla" if tithi_num_1_based <= 15 else "Krishna"
    if tithi_num_1_based in (15, 30):
        tithi_name = "Purnima" if tithi_num_1_based == 15 else "Amavasya"
    else:
        tithi_name = TITHI_NAMES[(tithi_num_1_based - 1) % 15]

    weekday = WEEKDAY_LORDS[local_datetime.weekday()]

    yoga_span = 360 / 27
    yoga_sum = (sun_longitude + moon_longitude) % 360
    yoga_index = int(yoga_sum // yoga_span)
    yoga_name = YOGA_NAMES[yoga_index]

    karana_index = int(diff // 6)  # 0-59
    if karana_index == 0:
        karana_name = "Kimstughna"
    elif karana_index <= 56:
        karana_name = KARANA_MOVABLE[(karana_index - 1) % 7]
    elif karana_index == 57:
        karana_name = "Shakuni"
    elif karana_index == 58:
        karana_name = "Chatushpada"
    else:
        karana_name = "Naga"

    moon_nak, moon_pada = nakshatra(moon_longitude)

    return {
        "tithi": f"{tithi_name} ({paksha})",
        "tithi_number": tithi_num_1_based,
        "vara": weekday,
        "vara_lord": {"Sunday": "Sun", "Monday": "Moon", "Tuesday": "Mars",
                      "Wednesday": "Mercury", "Thursday": "Jupiter",
                      "Friday": "Venus", "Saturday": "Saturn"}[weekday],
        "yoga": yoga_name,
        "karana": karana_name,
        "nakshatra": moon_nak,
        "pada": moon_pada,
        "note": "Vara/Tithi computed from civil midnight-to-midnight day; "
                "traditional panchang uses sunrise-to-sunrise, which can "
                "shift these near day boundaries.",
    }
