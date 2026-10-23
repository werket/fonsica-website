"""The sentences on insights/ilottery/index.html, as checks against a fresh build.

Numbers inside the copy follow the data on their own (data-k). What cannot follow is the
wording around them: "the four biggest lotteries do not", "roughly tripled", "only Italy".
Each check below guards one such sentence. When the data moves past what a sentence says,
the check fails and update_atlas.py stops publishing until the copy has been rewritten.

Keep this file in step with the page: change a sentence there, change its check here.
"""


def _growth(atlas, sid):
    return next(s for s in atlas["growth"] if s["id"] == sid)


def check(atlas):
    """Return a list of human-readable failures; empty means every sentence still holds."""
    fails = []

    def need(ok, sentence, detail):
        if not ok:
            fails.append(f'"{sentence}": {detail}')

    us = atlas["register"]["us"]
    big4 = us["biggest_four"]

    # 01 "13 US jurisdictions sell eInstants online. The four biggest lotteries do not."
    need(us["biggest_four_offline"] == 4, "The four biggest lotteries do not",
         f"{4 - us['biggest_four_offline']} of the four largest now sell eInstants online")
    need([b["code"] for b in big4] == ["CA", "NY", "FL", "TX"], "California, New York, Florida and Texas",
         f"the four largest are now {', '.join(b['code'] for b in big4)}")
    share = us["einstant_sales_share_pct"] or 0
    need(30 <= share <= 37, "account for a third of US lottery sales", f"the share is {share}%")
    ein, off = us["einstant_sales_m"], us["biggest_four_offline_sales_m"]
    need(ein and abs(off - ein) / ein <= .05, "sell the same amount again",
         f"${off / 1000:.1f}bn against ${ein / 1000:.1f}bn")

    # 02 "In Kentucky, Georgia and Virginia, eInstant sales roughly tripled in three years"
    leaders = []
    for sid in ("ky", "ga", "va"):
        m = _growth(atlas, sid)["multiple"]
        leaders.append(m["x"] if m else 0)
        need(m and (m["from"], m["to"]) == (2022, 2025), "From FY2022 to FY2025",
             f"{sid.upper()} now runs FY{m['from'] if m else '?'} to FY{m['to'] if m else '?'}")
        need(m and 2.5 <= m["x"] <= 3.6, "roughly tripled in three years", f"{sid.upper()} grew {m['x'] if m else 0} times")
    nc = _growth(atlas, "nc")["multiple"]
    need(nc and nc["to"] - nc["from"] == 1 and nc["x"] > 2, "North Carolina grew ... times in a single year",
         f"North Carolina now covers FY{nc['from']} to FY{nc['to']}" if nc else "no multiple")
    slow = {sid: (_growth(atlas, sid)["multiple"] or {}).get("x", 0) for sid in ("pa", "nh", "mi")}
    need(max(slow["pa"], slow["nh"]) < min(leaders), "Pennsylvania and New Hampshire grew more slowly",
         f"PA {slow['pa']}, NH {slow['nh']} against {min(leaders)}")
    need(slow["mi"] < 1, "and Michigan shrank", f"Michigan is at {slow['mi']} times")
    need(_growth(atlas, "mi")["peak"] == 2021, "Michigan, since its FY2021 peak",
         f"the peak is now FY{_growth(atlas, 'mi')['peak']}")
    need((atlas["alc"]["digital_instants_change_pct"] or 0) < 0, "Digital instant revenue fell",
         f"the change is {atlas['alc']['digital_instants_change_pct']}%")
    uk = atlas["uk"]["points"]
    need(30 <= uk[-1]["share_pct"] <= 37, "digital instants are now a third of all instant sales",
         f"{uk[-1]['share_pct']}% in {uk[-1]['year']}")
    need(uk[0]["year"] <= 2015, "back to 2015", f"the UK series starts in {uk[0]['year']}")

    # 03 "A Swedish eInstant pays back 50%. A Pennsylvanian one pays back 89%." and the dek
    rtp = atlas["catalog"]["rtp"]
    lowest = min(rtp, key=lambda r: r["median"])
    need(lowest["lottery"] == "Svenska Spel", "the median game pays back between 50% (Sweden)",
         f"the lowest median is now {lowest['lottery']}")
    need(any(r["lottery"] == "Pennsylvania Lottery" for r in rtp), "A Pennsylvanian one", "Pennsylvania has no RTP row")
    europe_high = [r["lottery"] for r in rtp if r["region"] == "Europe" and r["median"] > 74 and r["lottery"] != "Lotterie Nazionali"]
    need(not europe_high, "In Europe, only Italy goes above 74%", f"also {', '.join(europe_high)}")

    # 04 "Three studios make 88% of the eInstants in North American lobbies"
    regions = {r["region"]: r for r in atlas["studios"]["regions"]}
    na = regions.get("North America")
    top3 = [s["studio"] for s in na["studios"][:3]] if na else []
    need(top3 == ["IWG", "NeoGames (Aristocrat)", "Brightstar (ex-IGT)"], "IWG, NeoGames and Brightstar",
         f"the top three are now {', '.join(top3)}")
    nordics = regions.get("Nordics")
    first = nordics["studios"][0] if nordics else {"studio": None, "share": 0}
    need(first["studio"] == "Fennica Gaming" and first["share"] > 50, "Fennica Gaming alone makes more than half",
         f"{first['studio']} has {first['share']}%")

    # 05 "Most eInstants sell best in their first month"
    lc = atlas["launch"]
    need(lc["peak_launch_month"] / lc["games"] > .5, "Most eInstants sell best in their first month",
         f"{lc['peak_launch_month']} of {lc['games']}")

    # 06 "Fennica Gaming stands out, with new eInstant deals in Québec, Estonia and Italy"
    fennica = {m["lottery"] for m in atlas["moves"] if m["vendor"].startswith("Fennica")}
    for place in ("Loto-Québec", "Eesti Loto", "Lotterie Nazionali, Italy"):
        need(place in fennica, "Fennica ... deals in Québec, Estonia and Italy", f"{place} is no longer in the list")

    return fails
