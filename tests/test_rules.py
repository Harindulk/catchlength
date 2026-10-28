from catchlength.rules import RULES, bad_citations, check_size


def test_finfish_says_no_minimum_never_a_number():
    res = check_size("Katsuwonus pelamis", 31.0)
    assert {r["result"] for r in res} == {"no_minimum", "info"}
    assert not any("threshold_cm" in r for r in res)


def test_lobster_threshold():
    assert check_size("Panulirus homarus", 5.5)[0]["result"] == "below_minimum"
    assert check_size("Panulirus homarus", 6.0)[0]["result"] == "pass"


def test_unknown_species_is_flagged_not_passed():
    assert check_size("Thunnus albacares", 50)[-1]["result"] == "no_rule_in_pack"


def test_citation_validator():
    assert bad_citations("Below minimum [rule:lk-lobster-2000]; bins ok [rule:iotc-length-interval]") == []
    assert bad_citations("Legal size is 30 cm [rule:lk-tuna-min]") == ["lk-tuna-min"]


def test_every_rule_has_a_source():
    for r in RULES.values():
        assert r["url"].startswith("http") and r["quote"] and r["status"] in {"opened", "reported"}
