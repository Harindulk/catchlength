"""The cited rule pack: deterministic checks, and a validator so model-written text can only cite real rules."""
import json
import re
from pathlib import Path

RULES = {r["id"]: r for r in json.loads((Path(__file__).parent.parent / "data/rules.json").read_text())["rules"]}
CITE = re.compile(r"\[rule:([a-z0-9-]+)\]")


def for_species(species: str) -> list[dict]:
    return [r for r in RULES.values() if species in r["species"] or "*" in r["species"]]


def check_size(species: str, length_cm: float) -> list[dict]:
    """One result per applicable size rule: pass, below_minimum, or no_minimum (stated, never guessed)."""
    out = []
    for r in for_species(species):
        if r["measure"] == "sampling coverage":
            continue
        if r["threshold_cm"] is None:
            out.append({"rule": r["id"], "result": "no_minimum" if "*" not in r["species"] else "info", "quote": r["quote"]})
        else:
            out.append({"rule": r["id"], "result": "pass" if length_cm >= r["threshold_cm"] else "below_minimum",
                        "threshold_cm": r["threshold_cm"], "quote": r["quote"]})
    if not any(x["result"] != "info" for x in out):
        out.append({"rule": None, "result": "no_rule_in_pack", "quote": f"No rule in the pack covers {species}."})
    return out


def bad_citations(text: str) -> list[str]:
    """Rule ids cited as [rule:id] in model text that aren't in the pack."""
    return [c for c in CITE.findall(text) if c not in RULES]
