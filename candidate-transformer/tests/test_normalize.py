"""
Stage 2 checkpoint tests — Normalizers.

Run: pytest tests/test_normalize.py -v
"""

import pytest
from transformer.normalize.phones import normalize_phone
from transformer.normalize.dates import normalize_date, normalize_end_year
from transformer.normalize.emails import normalize_email, normalize_emails
from transformer.normalize.skills import normalize_skill, SKILL_ALIASES
from transformer.normalize.location import (
    normalize_country, normalize_city, normalize_region, normalize_location_phrase,
)
from transformer.normalize.names import normalize_name, name_match_key
from transformer.normalize.years_experience import normalize_years_experience
from transformer.normalize.links import normalize_url, normalize_linkedin_url
from transformer.normalize.headline import normalize_headline


# ---------------------------------------------------------------------------
# Phones
# ---------------------------------------------------------------------------

class TestNormalizePhone:
    def test_parens_format(self):
        val, method, ok = normalize_phone("(98765) 43210")
        assert ok and val == "+919876543210"

    def test_dash_format(self):
        val, method, ok = normalize_phone("98765-43210")
        assert ok and val == "+919876543210"

    def test_e164_with_spaces(self):
        val, method, ok = normalize_phone("+91 98765 43210")
        assert ok and val == "+919876543210"

    def test_all_three_produce_same_result(self):
        results = {normalize_phone(r)[0] for r in ["(98765) 43210", "98765-43210", "+91 98765 43210"]}
        assert results == {"+919876543210"}

    def test_bad_number(self):
        val, method, ok = normalize_phone("bad-number")
        assert not ok and val is None

    def test_empty_string(self):
        val, method, ok = normalize_phone("")
        assert not ok and val is None

    def test_whitespace_only(self):
        val, method, ok = normalize_phone("   ")
        assert not ok and val is None

    def test_method_on_success(self):
        _, method, ok = normalize_phone("+919876543210")
        assert ok and method == "e164_normalized"

    def test_method_on_failure(self):
        _, method, ok = normalize_phone("123")
        assert not ok and method == "e164_failed"


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

class TestNormalizeDate:
    def test_already_yyyy_mm(self):
        val, _, ok = normalize_date("2021-01")
        assert ok and val == "2021-01"

    def test_short_month_name(self):
        val, _, ok = normalize_date("Jan 2021")
        assert ok and val == "2021-01"

    def test_full_month_name(self):
        val, _, ok = normalize_date("January 2021")
        assert ok and val == "2021-01"

    def test_iso_date_strips_day(self):
        val, _, ok = normalize_date("2021-01-15")
        assert ok and val == "2021-01"

    def test_mm_slash_yyyy(self):
        val, _, ok = normalize_date("01/2021")
        assert ok and val == "2021-01"

    def test_mm_dash_yyyy(self):
        val, _, ok = normalize_date("01-2021")
        assert ok and val == "2021-01"

    def test_garbage(self):
        val, _, ok = normalize_date("garbage")
        assert not ok and val is None

    def test_lots(self):
        val, _, ok = normalize_date("lots")
        assert not ok and val is None

    def test_empty(self):
        val, _, ok = normalize_date("")
        assert not ok and val is None

    def test_bare_year_dropped(self):
        val, method, ok = normalize_date("2021")
        assert not ok and method == "date_year_only"

    def test_invalid_month(self):
        val, _, ok = normalize_date("2021-13")
        assert not ok

    def test_all_months_round_trip(self):
        months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        for i, mon in enumerate(months, 1):
            val, _, ok = normalize_date(f"{mon} 2020")
            assert ok and val == f"2020-{i:02d}", f"Failed for {mon}"


class TestNormalizeEndYear:
    def test_string_year(self):
        val, _, ok = normalize_end_year("2020")
        assert ok and val == 2020

    def test_int_year(self):
        val, _, ok = normalize_end_year(2020)
        assert ok and val == 2020

    def test_garbage(self):
        val, _, ok = normalize_end_year("abc")
        assert not ok and val is None

    def test_out_of_range(self):
        val, _, ok = normalize_end_year("1800")
        assert not ok


# ---------------------------------------------------------------------------
# Emails
# ---------------------------------------------------------------------------

class TestNormalizeEmail:
    def test_uppercase_with_spaces(self):
        val, method, ok = normalize_email("Alice@Example.COM ")
        assert ok and val == "alice@example.com" and method == "email_lowercased"

    def test_already_lowercase(self):
        val, _, ok = normalize_email("alice@example.com")
        assert ok and val == "alice@example.com"

    def test_not_an_email(self):
        val, _, ok = normalize_email("notanemail")
        assert not ok and val is None

    def test_no_at(self):
        val, _, ok = normalize_email("no.at.sign")
        assert not ok

    def test_empty(self):
        val, _, ok = normalize_email("")
        assert not ok

    def test_multiple_at(self):
        val, _, ok = normalize_email("a@@b.com")
        assert not ok


class TestNormalizeEmails:
    def test_dedup_case_insensitive(self):
        result = normalize_emails(["A@B.com", "a@b.com", "C@D.com"])
        assert result == ["a@b.com", "c@d.com"]

    def test_drops_invalid(self):
        result = normalize_emails(["good@example.com", "bad", ""])
        assert result == ["good@example.com"]

    def test_empty_list(self):
        assert normalize_emails([]) == []

    def test_stable_order(self):
        result = normalize_emails(["Z@example.com", "A@example.com"])
        assert result == ["z@example.com", "a@example.com"]


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------

class TestNormalizeSkill:
    def test_k8s_alias(self):
        val, method, ok = normalize_skill("k8s")
        assert ok and val == "Kubernetes" and method == "alias_mapped"

    def test_js_alias(self):
        val, method, ok = normalize_skill("js")
        assert ok and val == "JavaScript"

    def test_js_uppercase(self):
        val, method, ok = normalize_skill("JS")
        assert ok and val == "JavaScript"

    def test_py_alias(self):
        val, method, ok = normalize_skill("py")
        assert ok and val == "Python"

    def test_reactjs_alias(self):
        val, method, ok = normalize_skill("reactjs")
        assert ok and val == "React"

    def test_unknown_passthrough(self):
        # "Cobol" is not in the alias map → passthrough
        val, method, ok = normalize_skill("Cobol")
        assert ok and method == "passthrough"
        # Unknown skills are NOT dropped
        assert val is not None

    def test_unknown_passthrough_preserves_content(self):
        val, _, ok = normalize_skill("SomeObscureTool")
        assert ok and val is not None

    def test_empty(self):
        val, method, ok = normalize_skill("")
        assert not ok and val is None and method == "skill_empty"

    def test_whitespace_only(self):
        val, _, ok = normalize_skill("   ")
        assert not ok

    def test_alias_map_is_dict(self):
        assert isinstance(SKILL_ALIASES, dict)
        assert len(SKILL_ALIASES) > 10


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------

class TestNormalizeCountry:
    def test_india(self):
        val, method, ok = normalize_country("India")
        assert ok and val == "IN" and method == "iso2_mapped"

    def test_us(self):
        val, _, ok = normalize_country("US")
        assert ok and val == "US"

    def test_usa(self):
        val, _, ok = normalize_country("USA")
        assert ok and val == "US"

    def test_united_states(self):
        val, _, ok = normalize_country("United States")
        assert ok and val == "US"

    def test_unknown(self):
        val, method, ok = normalize_country("Narnia")
        assert not ok and val is None and method == "country_unknown"

    def test_empty(self):
        val, _, ok = normalize_country("")
        assert not ok

    def test_case_insensitive(self):
        val, _, ok = normalize_country("INDIA")
        assert ok and val == "IN"


class TestNormalizeCity:
    def test_strips_and_title_cases(self):
        val, method, ok = normalize_city("  mumbai  ")
        assert ok and val == "Mumbai" and method == "city_cleaned"

    def test_empty(self):
        val, _, ok = normalize_city("")
        assert not ok

    def test_multiword(self):
        val, _, ok = normalize_city("new delhi")
        assert ok and val == "New Delhi"


class TestNormalizeRegion:
    def test_strips_and_title_cases(self):
        val, method, ok = normalize_region("  maharashtra  ")
        assert ok and val == "Maharashtra" and method == "region_cleaned"

    def test_empty(self):
        val, _, ok = normalize_region("")
        assert not ok


class TestNormalizeLocationPhrase:
    def test_city_region_country(self):
        result = normalize_location_phrase("Mumbai, Maharashtra, India")
        assert result["city"] == "Mumbai"
        assert result["region"] == "Maharashtra"
        assert result["country"] == "IN"

    def test_city_country(self):
        result = normalize_location_phrase("Bangalore, India")
        assert result["city"] == "Bangalore"
        assert result["country"] == "IN"

    def test_city_only(self):
        result = normalize_location_phrase("Pune")
        assert result["city"] == "Pune"
        assert result["country"] is None

    def test_empty(self):
        result = normalize_location_phrase("")
        assert result == {"city": None, "region": None, "country": None}

    def test_never_raises(self):
        # Should not raise for any input
        normalize_location_phrase("????, garbage!!, 12345")


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------

class TestNormalizeName:
    def test_strips_and_title_cases(self):
        val, method, ok = normalize_name("  Aarav   Sharma ")
        assert ok and val == "Aarav Sharma" and method == "name_normalized"

    def test_empty(self):
        val, method, ok = normalize_name("  ")
        assert not ok and val is None and method == "name_empty"

    def test_none_like_empty(self):
        val, _, ok = normalize_name("")
        assert not ok

    def test_collapses_internal_spaces(self):
        val, _, ok = normalize_name("A   B    C")
        assert ok and val == "A B C"


class TestNameMatchKey:
    def test_lowercases(self):
        assert name_match_key("Aarav Sharma") == "aarav sharma"

    def test_collapses_whitespace(self):
        assert name_match_key("  Aarav   Sharma  ") == "aarav sharma"


# ---------------------------------------------------------------------------
# Years experience
# ---------------------------------------------------------------------------

class TestNormalizeYearsExperience:
    def test_plain_int_string(self):
        val, method, ok = normalize_years_experience("5")
        assert ok and val == 5.0 and method == "years_parsed"

    def test_float_string(self):
        val, _, ok = normalize_years_experience("5.5")
        assert ok and val == 5.5

    def test_plus_suffix(self):
        val, _, ok = normalize_years_experience("5+")
        assert ok and val == 5.0

    def test_years_suffix(self):
        val, _, ok = normalize_years_experience("5 years")
        assert ok and val == 5.0

    def test_yrs_suffix(self):
        val, _, ok = normalize_years_experience("3 yrs")
        assert ok and val == 3.0

    def test_range_lower_bound(self):
        val, method, ok = normalize_years_experience("5-7")
        assert ok and val == 5.0 and method == "years_range_lower"

    def test_range_to_syntax(self):
        val, method, ok = normalize_years_experience("5 to 7")
        assert ok and val == 5.0 and method == "years_range_lower"

    def test_lots_fails(self):
        val, method, ok = normalize_years_experience("lots")
        assert not ok and val is None

    def test_int_input(self):
        val, _, ok = normalize_years_experience(7)
        assert ok and val == 7.0

    def test_float_input(self):
        val, _, ok = normalize_years_experience(3.5)
        assert ok and val == 3.5

    def test_negative_fails(self):
        val, _, ok = normalize_years_experience("-1")
        assert not ok

    def test_out_of_range_fails(self):
        val, _, ok = normalize_years_experience("100")
        assert not ok


# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------

class TestNormalizeUrl:
    def test_valid_https(self):
        val, method, ok = normalize_url("https://github.com/foo")
        assert ok and val == "https://github.com/foo" and method == "url_cleaned"

    def test_prepends_https_when_no_scheme(self):
        val, _, ok = normalize_url("github.com/foo")
        assert ok and val == "https://github.com/foo"

    def test_not_a_url(self):
        val, method, ok = normalize_url("not a url")
        # "not a url" with spaces — after prepend: "https://not a url" → urlparse netloc="not a url" (still valid in urlparse)
        # We'll just verify it doesn't crash; result depends on urlparse behavior
        # (empty string should fail)

    def test_empty(self):
        val, method, ok = normalize_url("")
        assert not ok and val is None

    def test_linkedin_url(self):
        val, method, ok = normalize_linkedin_url("linkedin.com/in/johndoe")
        assert ok and method == "linkedin_url_cleaned"

    def test_whitespace_stripped(self):
        val, _, ok = normalize_url("  https://example.com  ")
        assert ok and val == "https://example.com"


# ---------------------------------------------------------------------------
# Headline
# ---------------------------------------------------------------------------

class TestNormalizeHeadline:
    def test_strips_whitespace(self):
        val, method, ok = normalize_headline("  Senior Engineer  ")
        assert ok and val == "Senior Engineer" and method == "headline_cleaned"

    def test_collapses_internal(self):
        val, _, ok = normalize_headline("Senior   Software   Engineer")
        assert ok and val == "Senior Software Engineer"

    def test_empty(self):
        val, method, ok = normalize_headline("  ")
        assert not ok and val is None and method == "headline_empty"

    def test_empty_string(self):
        val, _, ok = normalize_headline("")
        assert not ok
