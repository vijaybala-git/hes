"""ca_munis.py — California publicly owned electric utilities: service geography + gas LDC.

Phase 7 §4.1 issue 6. OpenEI's ZIP→utility files list a ZIP under every utility with customers
in it, so a municipal utility's ZIP usually ALSO lists the surrounding IOU (95814 downtown
Sacramento: PG&E + SMUD; 95050 Santa Clara: PG&E + Silicon Valley Power). Before this, only
the IOU file was read and PG&E won everywhere. Listing alone cannot decide it: Folsom (95630)
lists SMUD too but is served by PG&E; San Francisco ZIPs list only the City & County of SF,
whose Hetch Hetchy power serves municipal loads — SF homes are PG&E distribution customers.

Rule (scripts/build_zip_utility_map.py):
  • kind "full" — the muni serves (nearly) every home in its service geography. A ZIP goes to
    the muni when ≥ MUNI_SHARE of it lies in that geography (2020 Census ZCTA↔place /
    ZCTA↔county relationship files) — by land area, or, for place-listed munis, by the ZIP's
    town (Census place) land, since homes sit in towns (95380 Turlock); otherwise it goes to
    the IOU listed with it.
  • kind "partial" — serves only some loads/new developments; never wins while an IOU is
    listed; a ZIP listed ONLY under it goes to its `host` IOU (SF → PG&E).
  • A ZIP listed ONLY under munis goes to the best-covering one — unless its geography covers
    < NEIGHBOUR_MAX_SHARE of a real (land) ZIP, which then takes the neighbouring IOU (ZIP-3
    prefix, else the county's dominant IOU): OpenEI lists LADWP for Santa Monica.

Geography is curated (Census place / county names as in the 2020 relationship files). Where
the served area is not a whole city (districts), it is a county minus places served by an IOU,
or a list of places. Confidence is recorded per entry; review before relying on edge ZIPs.
"""

MUNI_SHARE = 0.5
# A ZIP listed ONLY under a muni is still given to the neighbouring IOU (ZIP prefix, else the
# county's dominant IOU) when the muni's geography covers less than this share of it — OpenEI
# lists LADWP for Santa Monica (0%), Beverly Hills (0%), Culver City (21%). Between this and
# MUNI_SHARE the listing is trusted (Mecca 39% → IID).
NEIGHBOUR_MAX_SHARE = 0.35

# eiaid -> entry.  places: Census place names (NAMELSAD, CA).  county: (GEOID, [excluded places]).
# gas: EIA-176 LDC id serving the area (used only for ZIPs with no IOU listed); None = no LDC
# in the rates DB (the muni sells gas itself, e.g. Palo Alto).
CA_MUNIS: dict[str, dict] = {
    "11208": {"short": "LADWP", "kind": "full", "places": ["Los Angeles city"],
              "gas": "17621931", "confidence": "high"},
    "16534": {"short": "SMUD", "kind": "full",
              "county": ("06067", ["Folsom city", "Isleton city", "Walnut Grove CDP",
                                   "Courtland CDP"]),
              "gas": "17610617", "confidence": "high (Folsom and the Delta are PG&E)"},
    "16655": {"short": "Silicon Valley Power", "kind": "full", "places": ["Santa Clara city"],
              "gas": "17610617", "confidence": "high"},
    "14401": {"short": "Palo Alto Utilities", "kind": "full", "places": ["Palo Alto city"],
              "gas": "17610617", "confidence": "high (Palo Alto also sells gas itself; "
                                                 "PG&E gas used as a proxy)"},
    "14534": {"short": "Pasadena Water & Power", "kind": "full", "places": ["Pasadena city"],
              "gas": "17621931", "confidence": "high"},
    "590":   {"short": "Anaheim Public Utilities", "kind": "full", "places": ["Anaheim city"],
              "gas": "17621931", "confidence": "high"},
    "16088": {"short": "Riverside Public Utilities", "kind": "full",
              "places": ["Riverside city"], "gas": "17621931", "confidence": "high"},
    "7294":  {"short": "Glendale Water & Power", "kind": "full", "places": ["Glendale city"],
              "gas": "17621931", "confidence": "high"},
    "2507":  {"short": "Burbank Water & Power", "kind": "full", "places": ["Burbank city"],
              "gas": "17621931", "confidence": "high"},
    "16295": {"short": "Roseville Electric", "kind": "full", "places": ["Roseville city"],
              "gas": "17610617", "confidence": "high"},
    "1050":  {"short": "Azusa Light & Water", "kind": "full", "places": ["Azusa city"],
              "gas": "17621931", "confidence": "high"},
    "4003":  {"short": "Colton Electric", "kind": "full", "places": ["Colton city"],
              "gas": "17621931", "confidence": "high"},
    "11124": {"short": "Lodi Electric", "kind": "full", "places": ["Lodi city"],
              "gas": "17610617", "confidence": "high"},
    "207":   {"short": "Alameda Municipal Power", "kind": "full", "places": ["Alameda city"],
              "gas": "17610617", "confidence": "high"},
    "15783": {"short": "Redding Electric", "kind": "full", "places": ["Redding city"],
              "gas": "17610617", "confidence": "high"},
    "17896": {"short": "Shasta Lake Electric", "kind": "full", "places": ["Shasta Lake city"],
              "gas": "17610617", "confidence": "high"},
    "19798": {"short": "Vernon Public Utilities", "kind": "full", "places": ["Vernon city"],
              "gas": "17621931", "confidence": "high (almost no homes)"},
    "9216":  {"short": "IID", "kind": "full",
              "county": ("06025", []),
              "places": ["Coachella city", "Indio city", "La Quinta city", "Mecca CDP",
                         "Thermal CDP", "Oasis CDP", "Vista Santa Rosa CDP"],
              "gas": "17621931", "confidence": "medium (Coachella Valley split with SCE)"},
    "12745": {"short": "Modesto ID", "kind": "full",
              "places": ["Modesto city", "Salida CDP", "Empire CDP", "Waterford city",
                         "Mountain House CDP"],
              "gas": "17610617", "confidence": "medium"},
    "19281": {"short": "Turlock ID", "kind": "full",
              "places": ["Turlock city", "Ceres city", "Hughson city", "Keyes CDP",
                         "Denair CDP", "Delhi CDP", "Hilmar-Irwin CDP"],
              "gas": "17610617", "confidence": "medium"},
    # partial — serve some loads / new developments; the IOU serves most homes
    "16612": {"short": "SFPUC", "kind": "partial", "host": "14328", "gas": "17610617",
              "confidence": "high (SF homes are PG&E distribution customers)"},
    "4390":  {"short": "Corona Utilities", "kind": "partial", "host": "17609",
              "gas": "17621931", "confidence": "medium"},
    "55787": {"short": "Moreno Valley Utility", "kind": "partial", "host": "17609",
              "gas": "17621931", "confidence": "medium"},
    "5969":  {"short": "Escondido", "kind": "partial", "host": "16609", "gas": "17611927",
              "confidence": "high (no residential electric service)"},
    "12312": {"short": "Merced ID", "kind": "partial", "host": "14328", "gas": "17610617",
              "confidence": "medium"},
}
