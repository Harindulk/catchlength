"""Meta Model API client with a response cache (reruns are free) and a cost ledger with a hard cap."""
import hashlib
import json
import os
from pathlib import Path

CACHE = Path(os.environ.get("CATCHLENGTH_CACHE", Path(__file__).parent.parent / "data/cache"))
# Standard-mode prices, dev.meta.ai/docs/pricing-rate-limits (29 Oct 2026), USD per 1M tokens
TOKEN_USD = {"muse-spark-1.3": (1.25, 4.25), "muse-wonder-1.0": (4.0, 20.0)}


class BudgetExceeded(RuntimeError):
    pass


class NoKey(RuntimeError):
    pass


def _env_key(name: str = "MODEL_API_KEY") -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    env = Path(__file__).parent.parent / ".env"
    for line in env.read_text().splitlines() if env.exists() else []:
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip().strip('"') or None
    return None


class Client:
    """kind='chat' -> chat.completions, kind='responses' -> responses (SAM). Every call goes through the cache."""

    def __init__(self, budget_usd: float = 0.60, transport=None):
        self.budget, self.spent, self.ledger = budget_usd, 0.0, []
        self._transport = transport  # tests inject a fake: (kind, body) -> dict

    def _live(self, kind: str, body: dict) -> dict:
        # open-weights Muse models are served by Baseten's OpenAI-compatible Model APIs under the meta-models/ prefix
        name, base = (("BASETEN_API_KEY", "https://inference.baseten.co/v1") if body["model"].startswith("meta-models/")
                      else ("MODEL_API_KEY", "https://api.meta.ai/v1"))
        key = _env_key(name)
        if not key:
            raise NoKey(f"{name} missing: add it to .env (live calls only; cached runs replay without it)")
        from openai import OpenAI
        c = OpenAI(base_url=base, api_key=key)
        r = c.chat.completions.create(**body) if kind == "chat" else c.responses.create(**body)
        return r.model_dump()

    def call(self, kind: str, body: dict, est_usd: float = 0.0) -> dict:
        h = hashlib.sha256(json.dumps([kind, body], sort_keys=True).encode()).hexdigest()[:24]
        f = CACHE / f"{h}.json"
        if f.exists():
            out, cached = json.loads(f.read_text()), True
        else:
            if self.spent + est_usd > self.budget:
                raise BudgetExceeded(f"run would pass ${self.budget:.2f} (spent ${self.spent:.3f})")
            out = (self._transport or self._live)(kind, body)
            CACHE.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(out))
            cached = False
        usd = 0.0 if cached else cost(body["model"], out, est_usd)
        self.spent += usd
        self.ledger.append({"model": body["model"], "cached": cached, "usd": round(usd, 5), "hash": h})
        return out


def cost(model: str, out: dict, fallback: float) -> float:
    u = out.get("usage") or {}
    if model in TOKEN_USD:
        i, o = TOKEN_USD[model]
        return (u.get("prompt_tokens", u.get("input_tokens", 0)) * i + u.get("completion_tokens", u.get("output_tokens", 0)) * o) / 1e6
    return fallback  # SAM bills per image/frame; the caller passes the price
