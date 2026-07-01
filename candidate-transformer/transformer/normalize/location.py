"""Location normalization — city/region (cleaned), country (ISO-3166 alpha-2). Stdlib only."""

from __future__ import annotations

import re

# Maps lowercase name/abbreviation → ISO-3166 alpha-2
COUNTRY_MAP: dict[str, str] = {
    "india": "IN", "in": "IN",
    "united states": "US", "usa": "US", "us": "US", "america": "US",
    "united kingdom": "GB", "uk": "GB", "gb": "GB", "england": "GB",
    "canada": "CA", "ca": "CA",
    "australia": "AU", "au": "AU",
    "germany": "DE", "de": "DE", "deutschland": "DE",
    "singapore": "SG", "sg": "SG",
    "france": "FR", "fr": "FR",
    "japan": "JP", "jp": "JP",
    "china": "CN", "cn": "CN",
    "netherlands": "NL", "nl": "NL", "holland": "NL",
    "sweden": "SE", "se": "SE",
    "norway": "NO", "no": "NO",
    "denmark": "DK", "dk": "DK",
    "finland": "FI", "fi": "FI",
    "switzerland": "CH", "ch": "CH",
    "austria": "AT", "at": "AT",
    "new zealand": "NZ", "nz": "NZ",
    "south korea": "KR", "korea": "KR", "kr": "KR",
    "brazil": "BR", "br": "BR",
    "mexico": "MX", "mx": "MX",
    "russia": "RU", "ru": "RU",
    "uae": "AE", "united arab emirates": "AE", "ae": "AE",
    "israel": "IL", "il": "IL",
    "spain": "ES", "es": "ES",
    "italy": "IT", "it": "IT",
    "portugal": "PT", "pt": "PT",
    "poland": "PL", "pl": "PL",
    "ireland": "IE", "ie": "IE",
    "belgium": "BE", "be": "BE",
    "indonesia": "ID", "id": "ID",
    "malaysia": "MY", "my": "MY",
    "philippines": "PH", "ph": "PH",
    "thailand": "TH", "th": "TH",
    "vietnam": "VN", "vn": "VN",
    "pakistan": "PK", "pk": "PK",
    "bangladesh": "BD", "bd": "BD",
    "sri lanka": "LK", "lk": "LK",
    "nepal": "NP", "np": "NP",
}


def normalize_country(raw: str) -> tuple[str | None, str, bool]:
    """
    Map a country name/abbreviation to ISO-3166 alpha-2.

    Returns (iso2_code, method, ok).
    Unknown country → (None, "country_unknown", False) — never guess.
    """
    if not raw or not raw.strip():
        return None, "country_unknown", False

    key = raw.strip().lower()
    code = COUNTRY_MAP.get(key)
    if code:
        return code, "iso2_mapped", True
    return None, "country_unknown", False


def normalize_city(raw: str) -> tuple[str | None, str, bool]:
    """
    Clean a city name: strip whitespace + title-case.

    No lookup table — city names are passed through cleaned.
    Returns (cleaned_city, "city_cleaned", ok).
    """
    if not raw or not raw.strip():
        return None, "city_empty", False

    cleaned = " ".join(raw.strip().split()).title()
    if not cleaned:
        return None, "city_empty", False
    return cleaned, "city_cleaned", True


def normalize_region(raw: str) -> tuple[str | None, str, bool]:
    """
    Clean a region/state name: strip whitespace + title-case.

    No lookup table — region names are passed through cleaned.
    Returns (cleaned_region, "region_cleaned", ok).
    """
    if not raw or not raw.strip():
        return None, "region_empty", False

    cleaned = " ".join(raw.strip().split()).title()
    if not cleaned:
        return None, "region_empty", False
    return cleaned, "region_cleaned", True


def normalize_location_phrase(raw: str) -> dict[str, str | None]:
    """
    Best-effort parse of a free-text location phrase.

    Handles:
      "City, Region, Country"
      "City, Country"
      "City"

    Returns {"city": ..., "region": ..., "country": ...} with None for unknowns.
    Never raises.
    """
    result: dict[str, str | None] = {"city": None, "region": None, "country": None}

    if not raw or not raw.strip():
        return result

    # Split on commas; strip each part
    parts = [p.strip() for p in raw.split(",") if p.strip()]

    if len(parts) == 0:
        return result

    if len(parts) == 1:
        city_val, _, city_ok = normalize_city(parts[0])
        result["city"] = city_val if city_ok else None
        return result

    if len(parts) == 2:
        # Could be "City, Country" or "City, Region"
        city_val, _, city_ok = normalize_city(parts[0])
        result["city"] = city_val if city_ok else None

        # Try to interpret second part as country first
        country_val, _, country_ok = normalize_country(parts[1])
        if country_ok:
            result["country"] = country_val
        else:
            # Treat as region
            region_val, _, region_ok = normalize_region(parts[1])
            result["region"] = region_val if region_ok else None
        return result

    # 3+ parts: "City, Region, Country" (or more — take first 3)
    city_val, _, city_ok = normalize_city(parts[0])
    result["city"] = city_val if city_ok else None

    region_val, _, region_ok = normalize_region(parts[1])
    result["region"] = region_val if region_ok else None

    country_val, _, country_ok = normalize_country(parts[2])
    result["country"] = country_val if country_ok else None

    return result
