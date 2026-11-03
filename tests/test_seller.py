from catchlength.seller import as_text, size_receipt, weight_kg


def test_weight_from_published_curve():
    w, _ = weight_kg("Auxis thazard", 30.0)  # 1.7e-5 * 30^3
    assert w == 0.46
    assert weight_kg("Rastrelliger kanagurta", 22.0) == (None, "no published fork-length weight curve for this species")
    assert weight_kg("Auxis thazard", 60.0)[0] is None  # outside the range the curve was fitted on


def test_flagged_fish_get_no_length_and_text_says_not_a_price():
    run = {"status": "awaiting_signoff", "receipt": {"clip_sha256": "ab" * 32},
           "fish": [{"id": "0", "species": "Katsuwonus pelamis", "fork_cm": 40.0, "status": "measured"},
                    {"id": "1", "species": "Auxis thazard", "fork_cm": 31.0, "status": "needs_review"}]}
    r = size_receipt(run)
    assert r["fish"][1]["fork_cm"] is None and r["fish"][1]["est_weight_kg"] is None
    assert list(r["curves"]) == ["Katsuwonus pelamis"] and not r["signed_off"]
    t = as_text(r)
    assert "doesn't set a price" in t and "Not yet signed off" in t and "fork length 40.0 cm" in t and "price" not in t.replace("set a price", "")
