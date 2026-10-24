#!/usr/bin/env python3
"""Build the public data file for the iLottery Atlas (insights/ilottery/atlas.json).

Reads the private research package (fonsica-data) and writes ONLY aggregates and
curated facts. Game-level data, prize tables, daily snapshots and estimates stay
private: they are the data pack sold on request.

Usage:
  python3 _pipeline/ilottery/build_atlas.py [--data /path/to/fonsica-data] [--check]

The data path defaults to $FONSICA_DATA, then ../fonsica-insights/data (the research bot's home), then ../fonsica-data next to this repo,
then fonsica-data inside it. Standard library only.
"""

import argparse
import csv
import gzip
import json
import math
import os
import re
import statistics
import sys
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(REPO, "insights", "ilottery", "atlas.json")
PAGE = os.path.join(REPO, "insights", "ilottery", "index.html")

# Every file the build reads, relative to the data folder (update_atlas.py watches these)
INPUTS = [
    "einstant_games_catalog.csv", "lotteries_suppliers.csv", "studio_master.csv",
    "studio_market_share_by_region.csv", "ilottery_contracts.csv", "prize_tables_all.csv.gz",
    "history_tables/eInstant_sales_by_lottery_year.csv",
    "history_tables/digital_instant_revenue_by_market_year.csv",
    "history_tables/lottery_einstant_launch.csv",
    "history_tables/michigan/michigan_launch_curves.csv",
    "history_tables/michigan/michigan_provider_share_month.csv",
    "history_tables/michigan/michigan_rank_month.csv",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_data_dir(cli):
    candidates = [cli, os.environ.get("FONSICA_DATA"),
                  os.path.join(REPO, "..", "fonsica-insights", "data"),   # the research bot's home
                  os.path.join(REPO, "..", "fonsica-data"),
                  os.path.join(REPO, "fonsica-data")]
    for c in candidates:
        if c and os.path.isfile(os.path.join(c, "einstant_games_catalog.csv")):
            return os.path.abspath(c)
    sys.exit("fonsica-data not found: pass --data or set FONSICA_DATA")


def read_csv(data, rel):
    with open(os.path.join(data, rel), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def num(v):
    try:
        x = float(str(v).replace(",", ".").strip())
        return x if x == x else None  # NaN guard
    except (TypeError, ValueError):
        return None


def r1(x):
    return None if x is None else round(x, 1)


def money_m(text):
    """'$9.3B' -> 9300.0, '$930M' -> 930.0, '—' -> None (USD millions)."""
    m = re.match(r"^\$?([\d.,]+)\s*([BM])", str(text).strip())
    if not m:
        return None
    v = float(m.group(1).replace(",", ""))
    return v * 1000 if m.group(2) == "B" else v


REGION_EN = {
    "Europa": "Europe",
    "Nordamerika": "North America",
    "Latinamerika & Karibien": "Latin America",
    "Asien-Stillahavet": "Asia-Pacific",
    "Afrika": "Africa",
    "Mellanöstern & Nordafrika": "Middle East & North Africa",
}

TIERS = ["einstants", "online", "planned", "offline"]

# The register is written in Swedish; the public page needs English place names
PLACE_EN = {
    "Estland": "Estonia", "Lettland": "Latvia", "Litauen": "Lithuania",
    "Bosnien och Hercegovina": "Bosnia and Herzegovina", "Bulgarien": "Bulgaria",
    "Kroatien": "Croatia", "Nordmakedonien": "North Macedonia", "Polen": "Poland",
    "Rumänien": "Romania", "Serbien": "Serbia", "Slovakien": "Slovakia",
    "Slovenien": "Slovenia", "Tjeckien": "Czechia", "Ukraina": "Ukraine", "Ungern": "Hungary",
    "Schweiz": "Switzerland", "Tyskland": "Germany", "Österrike": "Austria",
    "Förenade Arabemiraten": "United Arab Emirates", "Atlantic Canada (NB, NS, PEI, NL)": "Atlantic Canada",
    "Saskatchewan / territorier": "Saskatchewan and territories", "Azerbajdzjan": "Azerbaijan",
    "Libanon": "Lebanon", "Mexiko": "Mexico", "Algeriet": "Algeria", "Egypten": "Egypt",
    "Marocko": "Morocco", "Danmark": "Denmark", "Island": "Iceland", "Norge": "Norway",
    "Sverige": "Sweden", "Australien": "Australia", "Nya Zeeland": "New Zealand",
    "Brasilien": "Brazil", "Grekland": "Greece", "Italien": "Italy", "Spanien": "Spain",
    "Spanien – Katalonien": "Catalonia, Spain", "Filippinerna": "Philippines",
    "Turkiet": "Türkiye", "Moçambique": "Mozambique", "Sydafrika": "South Africa",
    "Belgien": "Belgium", "Frankrike": "France", "Irland": "Ireland", "Luxemburg": "Luxembourg",
    "Nederländerna": "Netherlands", "Storbritannien": "United Kingdom", "Etiopien": "Ethiopia",
    "Sydsudan": "South Sudan", "Hongkong": "Hong Kong", "Kina": "China", "Macao": "Macau",
    "Mongoliet": "Mongolia", "Sydkorea": "South Korea", "Dominikanska republiken": "Dominican Republic",
    "Karibien (flera öar)": "Caribbean islands", "Kanalöarna": "Channel Islands", "Ryssland": "Russia",
}

NAME_EN = {
    "AGLC (PlayAlberta) / WCLC-medlem": "AGLC (PlayAlberta)",
    "WCLC-produkter via Manitoba Liquor & Lotteries (PlayNow.com/mb)": "Manitoba Liquor & Lotteries (PlayNow.com/mb)",
    "Lotería Nacional (LOTENAL) inkl. Pronósticos": "Lotería Nacional (LOTENAL) and Pronósticos",
    "Caixa (Mega-Sena m.fl.) / Sorte Online (privat återförsäljare)": "Caixa (Mega-Sena)",
    "La Banca (Quiniela m.fl.)": "La Banca (Quiniela)",
    "Provinsiella lotterier (Quiniela, Loto)": "Provincial lotteries (Quiniela, Loto)",
    "Baloto + departementslotterier": "Baloto and departmental lotteries",
    "Lotería de Caracas, Lotería del Táchira m.fl.": "Lotería de Caracas, Lotería del Táchira and others",
    "Takarakuji (prefekturer via Mizuho)": "Takarakuji (prefectures via Mizuho)",
    "National Lottery (Sizekhaya från 2026-06-01; tidigare Ithuba)": "National Lottery (Sizekhaya)",
    "SET Lotto, Premier Lotto m.fl.": "SET Lotto, Premier Lotto and others",
    "The UAE Lottery (The Game LLC, GCGRA-licens)": "The UAE Lottery",
}


def einstant_flag(v):
    v = str(v).strip().lower()
    if v.startswith("ja"):
        return "yes"
    if v.startswith("planerat"):
        return "planned"
    return "no"


def tier(status, ei):
    s = str(status).strip()
    if ei == "yes":
        return "einstants"
    if s.startswith("Live") or s.startswith("Begränsad"):
        return "online"
    if s.startswith("Planerat") or s.startswith("Under upphandling"):
        return "planned"
    return "offline"


PLATFORM_EN = {
    "NeoPollard / Aristocrat": "Aristocrat / NeoPollard",
    "Brightstar (ex-IGT)": "Brightstar",
    "Scientific Games": "Scientific Games",
    "Pollard / IWG": "Pollard / IWG",
    "Allwyn": "Allwyn",
    "Intralot": "Intralot",
    "Egen plattform / övrig": "In-house or other",
}

US_CODES = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA",
    "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE", "District of Columbia": "DC",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL",
    "Indiana": "IN", "Iowa": "IA", "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA",
    "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI",
    "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO", "Montana": "MT",
    "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ",
    "New Mexico": "NM", "New York": "NY", "North Carolina": "NC", "North Dakota": "ND",
    "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA",
    "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN",
    "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}
NO_LOTTERY = ["AL", "AK", "HI", "NV", "UT"]

CA_CODES = {
    "British Columbia": ("BC", "British Columbia"),
    "Alberta": ("AB", "Alberta"),
    "Saskatchewan / territorier": ("SK", "Saskatchewan"),
    "Manitoba": ("MB", "Manitoba"),
    "Ontario": ("ON", "Ontario"),
    "Québec": ("QC", "Québec"),
    "Atlantic Canada (NB, NS, PEI, NL)": ("ATL", "Atlantic Canada"),
}

# eInstant launch month per lottery (lottery_einstant_launch.csv), keyed to map codes
LAUNCH_KEYS = {
    "AGLC (PlayAlberta)": "AB", "BCLC (PlayNow)": "BC", "DC Lottery": "DC",
    "Georgia Lottery": "GA", "Kentucky Lottery": "KY", "Loto-Québec": "QC",
    "Michigan Lottery": "MI", "New Hampshire Lottery": "NH",
    "North Carolina Education Lottery": "NC", "Pennsylvania Lottery": "PA",
    "Virginia Lottery": "VA", "West Virginia Lottery": "WV",
    "Massachusetts State Lottery": "MA",
}

# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def build_register(data):
    rows = read_csv(data, "lotteries_suppliers.csv")
    for r in rows:
        r["_ei"] = einstant_flag(r["einstants_online"])
        r["_tier"] = tier(r["ilottery_status"], r["_ei"])

    regions = []
    for sv, en in REGION_EN.items():
        rr = [r for r in rows if r["region"] == sv]
        counts = {t: sum(1 for r in rr if r["_tier"] == t) for t in TIERS}
        regions.append({"region": en, "n": len(rr), **counts})
    regions.sort(key=lambda x: (-x["einstants"], -x["n"]))

    totals = {t: sum(1 for r in rows if r["_tier"] == t) for t in TIERS}
    grades = {g: sum(1 for r in rows if r["confidence_grade"] == g) for g in "ABCD"}

    # One unit per lottery for the overview chart: name, place, region, status only
    order = {reg["region"]: i for i, reg in enumerate(regions)}
    units = sorted(
        ({"name": NAME_EN.get(r["lottery_operator"], r["lottery_operator"]),
          "place": PLACE_EN.get(r["country_state"], r["country_state"]),
          "region": REGION_EN[r["region"]], "tier": r["_tier"]} for r in rows),
        key=lambda u: (order[u["region"]], TIERS.index(u["tier"]), u["place"], u["name"]))

    launch = {}
    for r in read_csv(data, "history_tables/lottery_einstant_launch.csv"):
        code = LAUNCH_KEYS.get(r["lottery"])
        if code:
            precision = {"dag": "day", "månad": "month", "år": "year"}.get(r["precision"], r["precision"])
            launch[code] = {"date": r["einstant_launch"], "precision": precision, "grade": r["grade"]}

    tiles = []
    for r in rows:
        place = r["country_state"]
        if r["sub_region"] == "USA" and place in US_CODES:
            code, country, name = US_CODES[place], "US", place
        elif r["sub_region"] == "Kanada" and place in CA_CODES:
            (code, name), country = CA_CODES[place], "CA"
        else:
            continue
        tiles.append({
            "code": code, "country": country, "name": name,
            "lottery": NAME_EN.get(r["lottery_operator"], r["lottery_operator"]),
            "tier": r["_tier"],
            "platform": PLATFORM_EN.get(r["platform_group"]),
            "sales_fy24_m": money_m(r["fy2024_sales_usd"]),
            "launch": launch.get(code),
            "grade": r["confidence_grade"],
        })
    for code in NO_LOTTERY:
        name = next(k for k, v in US_CODES.items() if v == code)
        tiles.append({"code": code, "country": "US", "name": name, "lottery": None,
                      "tier": "none", "platform": None, "sales_fy24_m": None,
                      "launch": None, "grade": None})

    us = [t for t in tiles if t["country"] == "US" and t["tier"] != "none"]
    us_total = sum(t["sales_fy24_m"] or 0 for t in us)
    ein = [t for t in us if t["tier"] == "einstants"]
    ein_sales = sum(t["sales_fy24_m"] or 0 for t in ein)
    biggest = sorted(us, key=lambda t: -(t["sales_fy24_m"] or 0))[:4]
    big4_offline = [t for t in biggest if t["tier"] != "einstants"]

    vendors = {}
    for t in tiles:
        if t["platform"] and t["tier"] in ("einstants", "online", "planned"):
            v = vendors.setdefault(t["platform"], {"vendor": t["platform"], "einstants": [], "other": []})
            (v["einstants"] if t["tier"] == "einstants" else v["other"]).append(t["code"])
    vendor_list = sorted(vendors.values(), key=lambda v: (-len(v["einstants"]), -len(v["other"]), v["vendor"]))

    return {
        "lotteries": len(rows),
        "jurisdictions": len({r["country_state"] for r in rows}),
        "totals": totals,
        "grades": grades,
        "regions": regions,
        "units": units,
        "tiles": tiles,
        "vendors": vendor_list,
        "us": {
            "lotteries": len(us),
            "einstant_jurisdictions": len(ein),
            "online_other": sum(1 for t in us if t["tier"] == "online"),
            "planned": sum(1 for t in us if t["tier"] == "planned"),
            "offline": sum(1 for t in us if t["tier"] == "offline"),
            "sales_total_m": round(us_total),
            "einstant_sales_m": round(ein_sales),
            "einstant_sales_share_pct": r1(100 * ein_sales / us_total) if us_total else None,
            "biggest_four": [{"code": t["code"], "name": t["name"], "sales_m": t["sales_fy24_m"], "tier": t["tier"]} for t in biggest],
            "biggest_four_offline_sales_m": round(sum(t["sales_fy24_m"] or 0 for t in big4_offline)),
            "biggest_four_offline": len(big4_offline),
        },
        "canada_einstant_provinces": sum(1 for t in tiles if t["country"] == "CA" and t["tier"] == "einstants"),
    }


GROWTH = [
    # id, label, lottery, metric prefix, public metric
    ("va", "Virginia", "Virginia Lottery", "Instants (iLottery) försäljning", "Online instant ticket sales"),
    ("nc", "North Carolina", "North Carolina Education Lottery", "Digital Instants försäljning", "Digital instant sales"),
    ("ky", "Kentucky", "Kentucky Lottery", "iLottery instant play-försäljning", "Instant play sales"),
    ("ga", "Georgia", "Georgia Lottery", "Diggi eInstant-försäljning", "eInstant sales (Diggi)"),
    ("pa", "Pennsylvania", "Pennsylvania Lottery", "eInstant-försäljning (brutto)", "Gross eInstant sales"),
    ("nh", "New Hampshire", "New Hampshire Lottery", "iLottery nettovinst (net wins)", "iLottery net win, all games"),
    ("mi", "Michigan", "Michigan Lottery", "iLottery instants nettovinst (net win)", "eInstant net win"),
]


# A first year that only covers part of the fiscal year ("Start nov 2023 (delår)",
# "endast ~2 mån"): shown on the chart, never used as the base of a growth multiple
PARTIAL = re.compile(r"delår|endast ~?\d+ mån|partial", re.I)


def fy_num(fy):
    m = re.match(r"FY(\d{4})$", fy.strip())
    return int(m.group(1)) if m else None


def build_growth(data):
    rows = read_csv(data, "history_tables/eInstant_sales_by_lottery_year.csv")
    series = []
    for sid, label, lottery, prefix, metric in GROWTH:
        pts, urls = [], []
        for r in rows:
            if r["lottery"] != lottery or not r["metric"].startswith(prefix):
                continue
            if r["grade"] == "D":  # derived estimates stay in the data pack
                continue
            y = fy_num(r["fiscal_year"])
            v = num(r["value_millions"])
            if y is None or v is None:
                continue
            pts.append({
                "fy": y, "v": v, "grade": r["grade"],
                "derived": str(r["is_estimate"]).lower().startswith("ja"),
                "floor": "milstolpe" in r["metric"],
                "partial": bool(PARTIAL.search(r.get("note") or "")),
            })
            if r["source_url"] and r["source_url"] not in urls:
                urls.append(r["source_url"])
        pts.sort(key=lambda p: p["fy"])
        if not pts:
            continue
        by = {p["fy"]: p["v"] for p in pts if not p["floor"] and not p["partial"]}
        base = 2022 if 2022 in by else min(by)
        end = 2025 if 2025 in by else max(by)
        series.append({
            "id": sid, "label": label, "lottery": lottery, "metric": metric,
            "currency": "USD", "points": pts, "sources": urls[:3],
            "multiple": {"from": base, "to": end, "x": round(by[end] / by[base], 2)} if end > base else None,
            "first_full": min(by),
            "peak": max(pts, key=lambda p: p["v"])["fy"],
        })
    return series


def build_uk(data):
    rows = read_csv(data, "history_tables/digital_instant_revenue_by_market_year.csv")
    uk = [r for r in rows if r["market"] == "Storbritannien" and r["metric"].startswith("Interactive Instant Win")]
    pts = []
    for r in uk:
        pts.append({"year": int(r["period"][2:]), "sales_m": num(r["value_millions"]),
                    "share_pct": num(r["share_pct"]), "grade": r["grade"]})
    pts.sort(key=lambda p: p["year"])
    return {"points": pts, "currency": "GBP", "source": uk[0]["source_url"] if uk else None}


def build_alc(data):
    rows = read_csv(data, "history_tables/eInstant_sales_by_lottery_year.csv")
    alc = [r for r in rows if r["lottery"].startswith("Atlantic Lottery") and r["grade"] != "D"]

    def pick(prefix, fy):
        for r in alc:
            if r["metric"].startswith(prefix) and r["fiscal_year"] == fy:
                return num(r["value_millions"]), r["source_url"]
        return None, None

    # Only digital instants: the iGames total is restated between reports, so its
    # growth is described in words on the page, not computed here.
    di_prev, _ = pick("Digital Instants nettointäkt", "FY2024/25")
    di_now, src = pick("Digital Instants nettointäkt", "FY2025/26")
    return {
        "currency": "CAD", "period": "2025/26",
        "digital_instants_m": [di_prev, di_now],
        "digital_instants_change_pct": r1(100 * (di_now / di_prev - 1)) if di_prev and di_now else None,
        "source": src,
    }


RTP_LABELS = {
    "Svenska Spel": ("Svenska Spel", "SE"),
    "Lotto Baden-Württemberg": ("Lotto Baden-Württemberg", "DE"),
    "Sachsenlotto GAMES (DE-SN)": ("Sachsenlotto", "DE"),
    "Eesti Loto": ("Eesti Loto", "EE"),
    "LOTTO Rheinland-Pfalz": ("Lotto Rheinland-Pfalz", "DE"),
    "win2day (Österreichische Lotterien)": ("win2day", "AT"),
    "LOTTO Berlin": ("Lotto Berlin", "DE"),
    "LOTTO Hessen": ("Lotto Hessen", "DE"),
    "LOTTO Niedersachsen": ("Lotto Niedersachsen", "DE"),
    "Lotto NZ": ("Lotto NZ", "NZ"),
    "Swisslos Clix (CH)": ("Swisslos", "CH"),
    "Loterie Nationale Luxembourg": ("Loterie Nationale", "LU"),
    "Santa Casa (PT)": ("Santa Casa", "PT"),
    "FDJ United (Illiko)": ("FDJ", "FR"),
    "The National Lottery (Allwyn UK)": ("The National Lottery", "UK"),
    "Danske Spil (Quick)": ("Danske Spil", "DK"),
    "Nationale Loterij / Loterie Nationale": ("Nationale Loterij", "BE"),
    "Georgia Lottery": ("Georgia Lottery", "US"),
    "Lotterie Nazionali – Gratta e Vinci online": ("Lotterie Nazionali", "IT"),
    "Rhode Island Lottery": ("Rhode Island Lottery", "US"),
    "Kentucky Lottery": ("Kentucky Lottery", "US"),
    "New Hampshire Lottery": ("New Hampshire Lottery", "US"),
    "North Carolina Education Lottery": ("North Carolina Lottery", "US"),
    "Michigan Lottery": ("Michigan Lottery", "US"),
    "Pennsylvania Lottery": ("Pennsylvania Lottery", "US"),
    "Loto-Québec (Espacejeux)": ("Loto-Québec", "CA"),
}
RTP_MIN_GAMES = 5


def quantile(xs, q):
    xs = sorted(xs)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def build_catalog(data):
    rows = read_csv(data, "einstant_games_catalog.csv")
    by = {}
    for r in rows:
        v = num(r["rtp_pct"])
        if v is not None:
            by.setdefault(r["lottery"], []).append(v)
    rtp = []
    for lottery, xs in by.items():
        if len(xs) < RTP_MIN_GAMES:
            continue
        name, cc = RTP_LABELS.get(lottery, (lottery, ""))
        region = "North America" if cc in ("US", "CA") else ("Asia-Pacific" if cc == "NZ" else "Europe")
        rtp.append({"lottery": name, "cc": cc, "region": region, "n": len(xs),
                    "median": r1(statistics.median(xs)), "p25": r1(quantile(xs, .25)),
                    "p75": r1(quantile(xs, .75)), "min": r1(min(xs)), "max": r1(max(xs))})
    rtp.sort(key=lambda x: (x["median"], x["lottery"]))

    retrieved = max((r["retrieved_at"][:10] for r in rows if r.get("retrieved_at")), default=None)
    known = [r for r in rows if r["studio_normalized"] and not re.match(r"(?i)^(unknown|okänd|ej )", r["studio_normalized"])]

    # Three sample rows for the data-pack preview (public lobby facts)
    want = ["Michigan Lottery", "Loterie Nationale Luxembourg", "Lotto NZ"]
    sample = []
    for lottery in want:
        cand = sorted((r for r in rows if r["lottery"] == lottery and r["confidence"] == "A"
                       and num(r["rtp_pct"]) and num(r["top_prize"]) and num(r["price_max"]) and r["studio_normalized"]),
                      key=lambda r: r["game"].strip())
        if cand:
            r = cand[0]
            lo, hi = num(r["price_min"]), num(r["price_max"])
            price = f"{lo:g}–{hi:g}" if lo and lo != hi else f"{hi:g}"
            sample.append({"game": r["game"].strip(), "lottery": RTP_LABELS.get(lottery, (lottery,))[0],
                           "studio": r["studio_normalized"].split(" (")[0],
                           "price": f'{r["currency"]} {price}',
                           "top_prize": f'{r["currency"]} {num(r["top_prize"]):,.0f}',
                           "rtp": f'{num(r["rtp_pct"]):.1f}%'})

    return {
        "games": len(rows),
        "unique_titles": len({r["game"].strip().lower() for r in rows}),
        "lotteries": len({r["lottery"] for r in rows}),
        "countries": len({r["country"].split(" - ")[0] for r in rows if r["country"]}),
        "fields": len(rows[0]) if rows else 0,
        "rtp_games": sum(1 for r in rows if num(r["rtp_pct"]) is not None),
        "studio_known_pct": r1(100 * len(known) / len(rows)),
        "grade_a_pct": r1(100 * sum(1 for r in rows if r["confidence"] == "A") / len(rows)),
        "retrieved": retrieved,
        "rtp": rtp,
        "sample": sample,
    }


STUDIO_EN = {
    "IWG (Instant Win Gaming)": "IWG",
    "NeoGames Studio": "NeoGames (Aristocrat)",
    "Brightstar Lottery (fd. IGT)": "Brightstar (ex-IGT)",
    "Scientific Games": "Scientific Games",
    "Fennica Gaming": "Fennica Gaming",
    "Danske Spil (egen)": "Danske Spil, in-house",
    "Svenska Spel (egen)": "Svenska Spel, in-house",
    "FDJ Gaming Solutions": "FDJ Gaming Solutions",
    "ONCE (egen)": "ONCE, in-house",
    "Pariplay": "Pariplay",
    "EQL Games": "EQL Games",
    "Pollard Banknote": "Pollard Banknote",
}
STUDIO_REGIONS = [("Nordamerika", "North America"), ("Norden", "Nordics"), ("Europa (övrigt)", "Rest of Europe")]
TOP_STUDIOS = 5


def build_studios(data):
    rows = read_csv(data, "studio_market_share_by_region.csv")
    regions = []
    for sv, en in STUDIO_REGIONS:
        rr = sorted((r for r in rows if r["region"] == sv), key=lambda r: int(r["rank"]))
        if not rr:
            continue
        top = [{"studio": STUDIO_EN.get(r["studio"], r["studio"]), "titles": int(r["games_live"]),
                "share": num(r["share_of_attributed_titles_pct"])} for r in rr[:TOP_STUDIOS]]
        rest = rr[TOP_STUDIOS:]
        if rest:
            top.append({"studio": "Other studios", "titles": sum(int(r["games_live"]) for r in rest),
                        "share": r1(sum(num(r["share_of_attributed_titles_pct"]) or 0 for r in rest)), "other": True})
        regions.append({"region": en, "titles": int(rr[0]["region_titles_total"]),
                        "attributed_pct": num(rr[0]["region_attributed_pct"]),
                        "lotteries": int(rr[0]["lotteries_in_region"]), "studios": top})

    master = read_csv(data, "studio_master.csv")
    reach = sorted(master, key=lambda r: (-int(r["lotteries_n"] or 0), -int(r["games_live"] or 0)))[:6]
    reach = [{"studio": STUDIO_EN.get(r["studio"], r["studio"]), "lotteries": int(r["lotteries_n"]),
              "titles": int(r["games_live"]), "hq": r["hq"]} for r in reach]

    ps = read_csv(data, "history_tables/michigan/michigan_provider_share_month.csv")
    years = {}
    for r in ps:
        tot = num(r["instants_bet_total"]) or 0
        if tot <= 0:
            continue
        y = years.setdefault(r["month"][:4], {"iwg": 0.0, "total": 0.0, "months": 0, "last": r["month"]})
        y["iwg"] += num(r["iwg_bet"]) or 0
        y["total"] += tot
        y["months"] += 1
        y["last"] = max(y["last"], r["month"])
    mi = [{"year": int(k), "iwg_share": r1(100 * v["iwg"] / v["total"]), "months": v["months"],
           "wagers_m": round(v["total"] / 1e6)} for k, v in sorted(years.items())]

    verified = sum(1 for r in master if r["type"] != "ej verifierat")   # the rest are unconfirmed feed labels
    return {"count": len(master), "verified": verified, "regions": regions, "reach": reach, "michigan_share": mi}


def build_launch_curve(data):
    rows = read_csv(data, "history_tables/michigan/michigan_launch_curves.csv")
    first_report = min(r["month"] for r in rows)
    games = {}
    for r in rows:
        if r["first_month"] <= first_report:  # launch month must be inside the reports
            continue
        games.setdefault(r["game"], []).append(r)
    curve, raw = [], {}
    for m in range(0, 19):
        xs = [num(r["pct_of_peak"]) for g in games.values() for r in g
              if int(r["months_since_launch"]) == m and num(r["pct_of_peak"]) is not None]
        if len(xs) >= 10:
            raw[m] = statistics.median(xs)
            curve.append({"m": m, "median": r1(statistics.median(xs)), "p25": r1(quantile(xs, .25)),
                          "p75": r1(quantile(xs, .75)), "n": len(xs)})
    peaks = []
    for g in games.values():
        best = max(g, key=lambda r: num(r["bet_amount"]) or 0)
        peaks.append(int(best["months_since_launch"]))
    return {
        "games": len(games),
        "window": [min(r["month"] for r in rows), max(r["month"] for r in rows)],
        "peak_launch_month": sum(1 for p in peaks if p == 0),
        "peak_within_two": sum(1 for p in peaks if p <= 1),
        "curve": curve,
        "_raw": raw,
    }


# Verified 2026 market moves, written for the public page. Each entry must match a
# row in ilottery_contracts.csv (lottery + vendor substrings); unmatched entries
# are dropped with a warning so the page never shows an unsourced claim.
MOVES = [
    ("2026-01", "LEIA", "SG Studios", "LEIA alliance (Denmark, Finland, France, Norway, Sweden)",
     "Scientific Games", "Content agreement for eInstants across the alliance's lotteries", "content"),
    ("2026-01", "Loto-Québec", "Fennica", "Loto-Québec",
     "Fennica Gaming", "Fennica eInstants go live in Québec", "content"),
    ("2026-02", "PCSO", "Pacific Online", "PCSO, Philippines",
     "Pacific Online Systems", "Online draw sales stopped under the government's policy on online gambling", "market"),
    ("2026-02", "Eesti Loto", "Fennica", "Eesti Loto",
     "Fennica Gaming", "eInstant contract awarded in public procurement", "content"),
    ("2026-04", "BCLC", "Intralot", "BCLC, British Columbia",
     "Bally's Intralot", "Shared-services platform agreement", "platform"),
    ("2026-05", "LOTTO24", "NeoGames", "LOTTO24, Germany",
     "Aristocrat Interactive", "NeoGames Studio eInstants agreed for all 16 German states; launch expected later in 2026", "content"),
    ("2026-06", "National Lottery (NLC)", "Sizekhaya", "National Lottery, South Africa",
     "Sizekhaya", "New national licence starts; eInstants sold online for the first time", "market"),
    ("2026-06", "Colorado", "Pollard", "Colorado Lottery",
     "Pollard Banknote", "Selected to build a new iLottery platform; not yet live", "platform"),
    ("2026-06", "Virginia", "upphandling", "Virginia Lottery",
     "Open tender", "iLottery RFP published; bids were due in September", "platform"),
    ("2026-07", "Michigan", "Aristocrat", "Michigan Lottery",
     "Aristocrat Interactive", "Platform contract renewed for six years, extending a partnership that began in 2014", "platform"),
    ("2026-07", "Massachusetts", "Aristocrat Interactive (NeoGames)", "Massachusetts State Lottery",
     "Aristocrat Interactive", "iLottery launches on 27 July with more than 20 eInstants", "platform"),
    ("2026-07", "Lotterie Nazionali", "Fennica", "Lotterie Nazionali, Italy",
     "Fennica Gaming via Brightstar", "Fennica eInstants live on Gratta e Vinci online", "content"),
    ("2026-10", "Kentucky", "NeoGames Studio", "Kentucky Lottery",
     "Aristocrat Interactive", "NeoGames Studio eInstants added on the Brightstar platform, starting with The Lamp", "content"),
    ("2026-10", "Massachusetts", "Inspired", "Massachusetts State Lottery",
     "Inspired Entertainment", "Virtual sports added through Aristocrat Fusion, the first third-party supplier", "content"),
]


SOURCE_NAMES = {
    "aristocratinteractive.com": "Aristocrat Interactive",
    "business.inquirer.net": "Philippine Daily Inquirer",
    "cdnprodpaasmedia-valottery-com.azureedge.net": "Virginia Lottery RFP",
    "entity.ee": "Estonian procurement register via entity.ee",
    "gamingamerica.com": "Gaming America",
    "inseinc.com": "Inspired Entertainment",
    "canadiangamingbusiness.com": "Canadian Gaming Business",
    "fennicagaming.com": "Fennica Gaming",
    "lotteryusa.com": "Lottery USA",
    "nlcsa.org.za": "National Lotteries Commission",
    "scientificgames.com": "Scientific Games",
}


def source_name(url):
    host = re.sub(r"^www\.", "", url.split("/")[2]) if "://" in url else url
    return SOURCE_NAMES.get(host, host)


# Where each move happened, for the world map (ISO 3166-1 numeric)
MOVE_ISO = {
    "LEIA": ["208", "246", "250", "578", "752"], "Loto-Québec": ["124"], "PCSO": ["608"],
    "Eesti Loto": ["233"], "BCLC": ["124"], "LOTTO24": ["276"], "National Lottery (NLC)": ["710"],
    "Colorado": ["840"], "Virginia": ["840"], "Michigan": ["840"], "Massachusetts": ["840"],
    "Lotterie Nazionali": ["380"], "Kentucky": ["840"],
}


def build_moves(data):
    rows = read_csv(data, "ilottery_contracts.csv")
    out = []
    for month, lot_key, ven_key, lottery, vendor, text, kind in MOVES:
        match = next((r for r in rows if lot_key in r["lottery"] and ven_key in r["vendor"]
                      and r["confidence"].startswith("Verifierad")), None)
        if not match:
            print(f"  ! move skipped, no verified source row: {lottery} / {vendor}", file=sys.stderr)
            continue
        out.append({"month": month, "lottery": lottery, "vendor": vendor, "text": text,
                    "kind": kind, "url": match["source_url"], "source": source_name(match["source_url"]),
                    "iso": MOVE_ISO.get(lot_key, [])})
    return out


# ---------------------------------------------------------------------------
# World map: one entry per country, keyed by ISO 3166-1 numeric (the world-atlas ids)
# ---------------------------------------------------------------------------

PLACE_ISO = {
    "Algeria": "012", "Argentina": "032", "Australia": "036", "Austria": "040", "Azerbaijan": "031",
    "Barbados": "052", "Belgium": "056", "Bhutan": "064", "Bolivia": "068", "Bosnia and Herzegovina": "070",
    "Brazil": "076", "Bulgaria": "100", "Caribbean islands": "CAR", "Catalonia, Spain": "724",
    "Channel Islands": "CHI", "Chile": "152", "China": "156", "Colombia": "170", "Costa Rica": "188",
    "Croatia": "191", "Czechia": "203", "Denmark": "208", "Dominican Republic": "214", "Ecuador": "218",
    "Egypt": "818", "El Salvador": "222", "Estonia": "233", "Ethiopia": "231", "Finland": "246",
    "France": "250", "Germany": "276", "Ghana": "288", "Greece": "300", "Honduras": "340",
    "Hong Kong": "344", "Hungary": "348", "Iceland": "352", "Ireland": "372", "Israel": "376",
    "Italy": "380", "Jamaica": "388", "Japan": "392", "Kenya": "404", "Laos": "418", "Latvia": "428",
    "Lebanon": "422", "Liechtenstein": "438", "Lithuania": "440", "Luxembourg": "442", "Macau": "446",
    "Malaysia": "458", "Malta": "470", "Mauritius": "480", "Mexico": "484", "Mongolia": "496",
    "Montenegro": "499", "Morocco": "504", "Mozambique": "508", "Myanmar": "104", "Netherlands": "528",
    "New Zealand": "554", "Nigeria": "566", "North Macedonia": "807", "Norway": "578", "Panama": "591",
    "Peru": "604", "Philippines": "608", "Poland": "616", "Portugal": "620", "Puerto Rico": "630",
    "Romania": "642", "Russia": "643", "Serbia": "688", "Singapore": "702", "Slovakia": "703",
    "Slovenia": "705", "South Africa": "710", "South Korea": "410", "South Sudan": "728", "Spain": "724",
    "Sri Lanka": "144", "Sweden": "752", "Switzerland": "756", "Taiwan": "158", "Thailand": "764",
    "Türkiye": "792", "U.S. Virgin Islands": "850", "Uganda": "800", "Ukraine": "804",
    "United Arab Emirates": "784", "United Kingdom": "826", "Uruguay": "858", "Venezuela": "862",
    "Vietnam": "704", "Zimbabwe": "716",
}
COUNTRY_NAME = {"840": "United States", "124": "Canada", "724": "Spain"}
# Places too small for a 1:110m map are drawn as points (lat, lon)
MARKERS = {
    "470": [35.9, 14.45], "702": [1.35, 103.82], "344": [22.32, 114.17], "446": [22.2, 113.55],
    "480": [-20.2, 57.5], "052": [13.19, -59.54], "438": [47.16, 9.55], "CHI": [49.35, -2.35],
    "CAR": [15.5, -61.5], "850": [18.34, -64.9], "442": [49.61, 6.13], "630": [18.22, -66.5],
}
CATALOG_ISO = {"USA": "840", "Canada": "124", "Switzerland (FR)": "756"}
# Verified studios only; feed codes and unattributed rows stay out of the public map
STUDIO_RULES = [
    (r"iwg|instant win gaming", "IWG"), (r"pariplay", "Pariplay"), (r"neogames", "NeoGames"),
    (r"brightstar|\bigt\b", "Brightstar"), (r"scientific games|sg studios", "Scientific Games"),
    (r"fennica", "Fennica Gaming"), (r"pollard", "Pollard"), (r"fdj united", "FDJ United"),
    (r"fdj gaming", "FDJ Gaming Solutions"), (r"danske spil", "Danske Spil (in-house)"),
    (r"svenska spel", "Svenska Spel (in-house)"), (r"\bonce\b", "ONCE (in-house)"),
    (r"concepci", "Lotería de Concepción (in-house)"), (r"allodium", "Allodium"),
    (r"synot", "Synot Interactive"), (r"nettrek", "netTrek"), (r"inspired", "Inspired Entertainment"),
    (r"pragmatic", "Pragmatic Play"), (r"\bags\b|playags", "PlayAGS"),
    (r"premier lotteries", "Premier Lotteries Ireland (in-house)"),
]
LENS_STUDIOS = ["IWG", "NeoGames", "Brightstar", "Scientific Games", "Fennica Gaming", "Pariplay", "Pollard"]


def canon_studio(raw):
    s = (raw or "").strip().lower()
    if not s or s.startswith(("unknown", "okänd", "ej ")):
        return None
    return next((name for pattern, name in STUDIO_RULES if re.search(pattern, s)), None)


def build_world(data):
    reg = read_csv(data, "lotteries_suppliers.csv")
    order = {t: i for i, t in enumerate(TIERS)}
    countries = {}
    for r in reg:
        if r["sub_region"] == "USA":
            iso = "840"
        elif r["sub_region"] == "Kanada":
            iso = "124"
        else:
            place = PLACE_EN.get(r["country_state"], r["country_state"])
            iso = PLACE_ISO.get(place)
            if not iso:
                print(f"  ! no ISO code for {place}", file=sys.stderr)
                continue
        place = PLACE_EN.get(r["country_state"], r["country_state"])
        c = countries.setdefault(iso, {"iso": iso, "name": COUNTRY_NAME.get(iso, place),
                                       "region": REGION_EN[r["region"]], "lotteries": []})
        ei = einstant_flag(r["einstants_online"])
        c["lotteries"].append({"name": NAME_EN.get(r["lottery_operator"], r["lottery_operator"]),
                               "tier": tier(r["ilottery_status"], ei)})
    for c in countries.values():
        c["lotteries"].sort(key=lambda l: (order[l["tier"]], l["name"]))
        c["tier"] = c["lotteries"][0]["tier"]

    cat = read_csv(data, "einstant_games_catalog.csv")
    per = {}
    footprints = {s: set() for s in LENS_STUDIOS}
    for r in cat:
        country = r["country"].split(" - ")[0]
        iso = CATALOG_ISO.get(country) or PLACE_ISO.get(country)
        if not iso:
            continue
        p = per.setdefault(iso, {"listings": 0, "rtp": [], "studios": {}})
        p["listings"] += 1
        v = num(r["rtp_pct"])
        if v is not None:
            p["rtp"].append(v)
        studio = canon_studio(r["studio_normalized"])
        if studio:
            p["studios"][studio] = p["studios"].get(studio, 0) + 1
            if studio in footprints:
                footprints[studio].add(iso)
    for iso, p in per.items():
        c = countries.get(iso)
        if not c:
            continue
        c["listings"] = p["listings"]
        c["rtp_median"] = r1(statistics.median(p["rtp"])) if len(p["rtp"]) >= RTP_MIN_GAMES else None
        c["studios"] = [s for s, _ in sorted(p["studios"].items(), key=lambda kv: -kv[1])[:3]]

    out = sorted(countries.values(), key=lambda c: c["name"])
    return {
        "countries": out,
        "markers": {k: v for k, v in MARKERS.items() if k in countries},
        "footprints": {s: sorted(v) for s, v in footprints.items() if len(v) >= 2},
    }


def build_pack(data, catalog):
    with gzip.open(os.path.join(data, "prize_tables_all.csv.gz"), "rt", encoding="utf-8") as f:
        prize_rows = sum(1 for _ in f) - 1
    sales = read_csv(data, "history_tables/eInstant_sales_by_lottery_year.csv")
    market = read_csv(data, "history_tables/digital_instant_revenue_by_market_year.csv")
    contracts = read_csv(data, "ilottery_contracts.csv")
    mi_month = read_csv(data, "history_tables/michigan/michigan_rank_month.csv")
    return {
        "games": catalog["games"],
        "fields": catalog["fields"],
        "lotteries": catalog["lotteries"],
        "prize_rows": prize_rows,
        "sales_points": len(sales) + len(market),
        "sales_sources": len({r["lottery"] for r in sales} | {r["operator"] for r in market}),
        "contracts": len(contracts),
        "michigan_game_months": len(mi_month),
        "sample": catalog["sample"],
    }


# ---------------------------------------------------------------------------
# Page check: every data-k key used in the HTML must exist in the JSON
# ---------------------------------------------------------------------------

def lookup(obj, path):
    for part in path.split("."):
        if isinstance(obj, list):
            obj = obj[int(part)]
        elif isinstance(obj, dict) and part in obj:
            obj = obj[part]
        else:
            return None
    return obj


def check_page(atlas):
    if not os.path.isfile(PAGE):
        return 0
    html = open(PAGE, encoding="utf-8").read()
    missing = [k for k in sorted(set(re.findall(r'data-k="([^"]+)"', html))) if lookup(atlas, k) is None]
    for k in missing:
        print(f"  ! page uses data-k=\"{k}\" but atlas.json has no such value", file=sys.stderr)
    return len(missing)


# ---------------------------------------------------------------------------
# Static numbers: write the current values into the page, so readers without
# JavaScript and search engines see the same figures as the charts
# ---------------------------------------------------------------------------

def js_round(x):
    """Math.round: halves go up, as in the page script."""
    return math.floor(x + 0.5)


def js_fixed(x, digits):
    """Number.prototype.toFixed for the values used here (halves go up)."""
    q = Decimal(repr(x)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
    return f"{q:.{digits}f}"


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fmt_value(v, fmt):
    """Python twin of FMT in insights/ilottery/index.html. Keep the two in step."""
    if fmt == "int":
        return f"{js_round(v):,}"
    if fmt == "x":
        return js_fixed(v, 1)
    if fmt == "bn":
        return js_fixed(v / 1000, 1)
    if fmt == "date":
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00")) if "T" in str(v) else datetime.fromisoformat(str(v))
        return f"{d.day} {MONTHS[d.month - 1]} {d.year}"
    if fmt == "abs0":
        return str(abs(js_round(v)))
    if fmt == "pct0":
        return str(js_round(v))
    if fmt == "k":
        return f"{js_round(v / 1000)}k"
    return f"{js_round(v):,}" if isinstance(v, (int, float)) else str(v)


def render_page_numbers(html, atlas):
    def swap(m):
        tag, attrs, text = m.group(1), m.group(2), m.group(3)
        key = re.search(r'data-k="([^"]+)"', attrs).group(1)
        fmt = re.search(r'data-fmt="([^"]+)"', attrs)
        value = lookup(atlas, key)
        if value is None:
            return m.group(0)
        return f"<{tag}{attrs}>{fmt_value(value, fmt.group(1) if fmt else None)}</{tag}>"
    return re.sub(r'<(span|dd)(\s[^>]*data-k="[^"]+"[^>]*)>([^<]*)</\1>', swap, html)


# Verified rows left out of the page on purpose, so update reports stop suggesting them
MOVES_SKIPPED = [
    ("New York Lottery", "Brightstar", "central-system extension; New York sells no eInstants"),
    ("Virginia Lottery", "Random State", "Adam's own studio: left out, see the disclosure on the page"),
]


def candidate_moves(data):
    """Verified 2026 contract rows that MOVES does not publish yet: they need English copy."""
    known = [(lot_key, ven_key) for _, lot_key, ven_key, *_ in MOVES] + [(lk, vk) for lk, vk, _ in MOVES_SKIPPED]
    out = []
    for r in read_csv(data, "ilottery_contracts.csv"):
        if not r["confidence"].startswith("Verifierad") or "2026" not in r["start_or_award"]:
            continue
        if any(lk in r["lottery"] and vk in r["vendor"] for lk, vk in known):
            continue
        out.append({"lottery": r["lottery"], "vendor": r["vendor"], "when": r["start_or_award"],
                    "status": r["status"], "url": r["source_url"]})
    return out


class BuildRefused(Exception):
    pass


def build(data):
    """Everything the page needs, from the research folder. Raises BuildRefused on bad data."""
    catalog = build_catalog(data)
    atlas = {
        "meta": {
            "title": "iLottery Atlas",
            "status": "beta",
            "built": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
            "data_retrieved": catalog["retrieved"],
            "note": "Public aggregates only. Game-level data, prize tables, daily scans and estimates are available on request.",
        },
        "register": build_register(data),
        "catalog": {k: v for k, v in catalog.items() if k not in ("sample",)},
        "growth": build_growth(data),
        "uk": build_uk(data),
        "alc": build_alc(data),
        "studios": build_studios(data),
        "launch": build_launch_curve(data),
        "moves": build_moves(data),
        "world": build_world(data),
        "pack": build_pack(data, catalog),
    }

    # Named values for the page copy, so every number in a sentence comes from the build
    g = {s["id"]: s for s in atlas["growth"]}
    mi = [p["v"] for p in g["mi"]["points"]]
    atlas["copy"] = {
        "us_einstant_jurisdictions": atlas["register"]["us"]["einstant_jurisdictions"],
        "us_einstant_sales_m": atlas["register"]["us"]["einstant_sales_m"],
        "us_big4_sales_m": atlas["register"]["us"]["biggest_four_offline_sales_m"],
        "ky_x": g["ky"]["multiple"]["x"], "ga_x": g["ga"]["multiple"]["x"],
        "va_x": g["va"]["multiple"]["x"],
        "nc_first_full_m": next(p["v"] for p in g["nc"]["points"] if p["fy"] == g["nc"]["first_full"]),
        "mi_drop_pct": r1(100 * (mi[-1] / max(mi) - 1)),
        "alc_drop_pct": atlas["alc"]["digital_instants_change_pct"],
        "rtp_lotteries": len(catalog["rtp"]),
        "rtp_share_pct": r1(100 * catalog["rtp_games"] / catalog["games"]),
        "games_more": catalog["games"] - len(catalog["sample"]),
        # integers rounded once from the unrounded medians, used by the copy and the chart labels
        "launch_m3": round(atlas["launch"]["_raw"][3]),
        "launch_m12": round(atlas["launch"]["_raw"][12]),
    }
    del atlas["launch"]["_raw"]
    rtp = {r["lottery"]: r["median"] for r in catalog["rtp"]}
    na = next((r for r in atlas["studios"]["regions"] if r["region"] == "North America"), None)
    atlas["copy"].update({
        "rtp_se_pct": rtp.get("Svenska Spel"),
        "rtp_pa_pct": rtp.get("Pennsylvania Lottery"),
        # games a budget buys when every win is staked again: budget / (1 - RTP), Pennsylvania over Sweden
        "play_pa_se_x": round((100 - rtp["Svenska Spel"]) / (100 - rtp["Pennsylvania Lottery"]), 3)
                        if {"Svenska Spel", "Pennsylvania Lottery"} <= rtp.keys() else None,
        "rtp_min_pct": min(rtp.values()),
        "rtp_max_pct": max(rtp.values()),
        "rtp_na_min_pct": min(r["median"] for r in catalog["rtp"] if r["region"] == "North America"),
        "rtp_na_count": sum(1 for r in catalog["rtp"] if r["region"] == "North America"),
        "na_top3_pct": r1(sum(s["share"] for s in na["studios"][:3])) if na else None,
        "world_countries": len(atlas["world"]["countries"]),
        "world_einstant_countries": sum(1 for c in atlas["world"]["countries"] if c["tier"] == "einstants"),
    })

    # Guard rails: refuse to publish a broken or suspiciously small build
    problems = []
    if atlas["catalog"]["games"] < 1000:
        problems.append("catalogue has fewer than 1,000 games")
    if atlas["register"]["lotteries"] < 100:
        problems.append("register has fewer than 100 lotteries")
    if len(atlas["growth"]) < 5:
        problems.append("fewer than five growth series")
    if len(json.dumps(atlas)) > 200_000:
        problems.append("atlas.json is larger than 200 KB: game-level data may have leaked in")
    problems += [f"{n} data-k keys missing"] if (n := check_page(atlas)) else []
    if problems:
        raise BuildRefused("; ".join(problems))
    return atlas


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", help="path to the fonsica-data folder")
    ap.add_argument("--check", action="store_true", help="build and validate, but do not write")
    args = ap.parse_args()
    data = find_data_dir(args.data)
    try:
        atlas = build(data)
    except BuildRefused as e:
        sys.exit(f"Build refused: {e}")

    import claims  # same folder; kept apart because it mirrors the page copy
    for failure in claims.check(atlas):
        print(f"  ! copy no longer holds: {failure}", file=sys.stderr)

    reg, cat = atlas["register"], atlas["catalog"]
    print(f"register  {reg['lotteries']} lotteries · {reg['totals']}")
    print(f"catalogue {cat['games']} games · {cat['lotteries']} lotteries · RTP {cat['rtp_games']} · studio known {cat['studio_known_pct']}%")
    print(f"US        {reg['us']['einstant_jurisdictions']} eInstant jurisdictions · {reg['us']['einstant_sales_share_pct']}% of FY24 sales")
    print(f"growth    " + ", ".join(f"{s['label']} x{s['multiple']['x']}" for s in atlas["growth"] if s["multiple"]))
    print(f"moves     {len(atlas['moves'])} · pack {atlas['pack']['prize_rows']:,} prize rows")
    if args.check:
        print("check only, nothing written")
        return
    write(atlas)
    print(f"wrote {os.path.relpath(OUT, REPO)} ({os.path.getsize(OUT) / 1024:.1f} KB) and the page's static numbers")


def write(atlas):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(atlas, f, ensure_ascii=False, separators=(",", ":"))
    html = open(PAGE, encoding="utf-8").read()
    updated = render_page_numbers(html, atlas)
    if updated != html:
        open(PAGE, "w", encoding="utf-8").write(updated)


if __name__ == "__main__":
    main()
