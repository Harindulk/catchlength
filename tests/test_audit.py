from catchlength.audit import grade

GT = [{"batch": "B1", "tag": str(i), "species": "balaya", "fork_cm": str(40 + i)} for i in range(1, 5)]


def run(fork, status=("measured",) * 4, species="Katsuwonus pelamis", n=4):
    return {"source": "b1.mp4", "batch": "B1", "tags": {str(i): f"B1-{i}" for i in range(1, n + 1)},
            "fish": [{"id": str(i), "fork_cm": fork[i - 1], "status": status[i - 1], "species": species} for i in range(1, n + 1)]}


def test_perfect_run():
    r = grade(GT, [run([41, 42, 43, 44])])
    assert r["length"]["mae"] == 0 and r["count"]["exact_rate"] == 1.0 and r["pass_marks"]["count"]
    assert r["pass_marks"]["length"] is False  # fewer than 40 fish never passes, however good


def test_flagged_fish_are_counted_but_kept_out_of_accepted_error():
    r = grade(GT, [run([41, 42, 43, 54], status=("measured",) * 3 + ("needs_review",))])
    assert r["length"]["mae"] == 2.5 and r["length_accepted_only"]["mae"] == 0 and r["flagged"] == 1


def test_untagged_fish_are_reported_not_dropped():
    x = run([41, 42, 43, 44])
    del x["tags"]["4"]
    r = grade(GT, [x])
    assert r["unmatched"] == [{"clip": "b1.mp4", "fish": "4"}] and r["n_matched"] == 3


def test_species_local_names_match_latin():
    assert grade(GT, [run([41, 42, 43, 44])])["species"]["accuracy"] == 1.0  # tape says "balaya"
    assert grade(GT, [run([41, 42, 43, 44], species="Euthynnus affinis")])["species"]["accuracy"] == 0.0
