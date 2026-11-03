"""Optional final check by Muse Wonder 1.0, after the agent files its report: one call looks at the outlined frame and
the accepted fish and may raise doubts. Bounded: it can only add notes to the officer's queue. It never changes a
length, a species or a status, and a failed or malformed reply leaves the report as it was. Off unless --verify.
The same check with OPEN_MODEL (Muse Spark Open on Baseten, --audit-open) is the open-weights auditor: a second,
independently hosted model reading the same evidence, with the same bounds."""
import json

from .agent import Run
from .spark import _shrink
from .sam import data_url

MODEL = "muse-wonder-1.0"
OPEN_MODEL = "meta-models/muse-spark-open-1026"
SCHEMA = {"type": "json_schema", "json_schema": {"name": "verdict", "schema": {
    "type": "object", "additionalProperties": False, "required": ["doubts"],
    "properties": {"doubts": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                         "required": ["id", "reason"],
                                                         "properties": {"id": {"type": "string"}, "reason": {"type": "string"}}}}}}}}


def verify(run: Run, est_usd: float = 0.05, model: str = MODEL) -> dict:
    who = "Muse Spark Open (open-weights auditor)" if model == OPEN_MODEL else "Muse Wonder"
    fish = [f.row() for f in run.fish.values() if f.status == "measured"]
    if not fish:
        return {"model": model, "checked": 0, "doubts": []}
    rows = [{k: r[k] for k in ("id", "fork_cm", "axis_cm", "species")} for r in fish]
    prompt = ("You are auditing a fish-length report. The image shows each accepted fish with its outline, id number and a "
              "dashed snout-to-fork line. Rows: " + json.dumps(rows) + ". List only fish whose outline or line looks wrong "
              "(two fish in one outline, a tail or head cut off, the line not ending at the tail fork, the wrong species "
              "for what you see). Give a short reason for each. An empty list is a fine answer.")
    body = {"model": model, "response_format": SCHEMA, "messages": [{"role": "user", "content": [
        {"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": data_url(_shrink(run.outlined(), 1280)[0])}}]}]}
    try:
        out = json.loads(run.client.call("chat", body, est_usd)["choices"][0]["message"]["content"])
        doubts = [d for d in out["doubts"] if d["id"] in {r["id"] for r in fish}]  # ids it invented are dropped
    except Exception as e:  # the verifier is advisory: its failure never blocks or alters the report
        return {"model": model, "checked": len(fish), "doubts": [], "error": f"{type(e).__name__}: {e}"[:200]}
    for d in doubts:
        run.reviews.append({"what": d["id"], "reason": f"{who} doubts it: " + d["reason"][:300], "by": "verifier"})
    return {"model": model, "checked": len(fish), "doubts": doubts}
