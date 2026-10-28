"""Serves the console and runs the agent on preloaded samples, streaming each turn (server-sent events).
python -m catchlength.server [--port 8000]   Samples: data/samples/<id>/ holding frames/*.jpg or clip.mp4.
Public use is limited to these samples: no uploads, no URLs. Repeat runs replay cached model responses for free."""
import argparse
import json
import os
import threading
import time
from datetime import date
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2

from .agent import Run, run_agent
from .api import BudgetExceeded, Client, NoKey
from .cli import load_frames, save

ROOT = Path(__file__).parent.parent
SAMPLES = ROOT / "data/samples"
OUT = ROOT / "runs/live"
WEB = ROOT / "web"
DAILY_USD = float(os.environ.get("CATCHLENGTH_DAILY_USD", "3"))
PER_IP = int(os.environ.get("CATCHLENGTH_RUNS_PER_IP", "6"))
_lock = threading.Lock()
_ledger = {"day": None, "usd": 0.0, "ips": {}}


def sample_frames(sid: str, n: int = 6):
    d = SAMPLES / sid
    if not d.is_dir() or "/" in sid or sid.startswith("."):
        raise KeyError(sid)
    frames = sorted((d / "frames").glob("*.jpg"))
    if frames:
        return [cv2.imread(str(f)) for f in frames[:n]]
    clip = next(iter(sorted(d.glob("clip.*"))), None)
    if clip is None:
        raise KeyError(sid)
    return load_frames(str(clip), n)


def allow(ip: str) -> str | None:
    """None if this run may start, else the reason it may not."""
    with _lock:
        if _ledger["day"] != date.today():
            _ledger.update(day=date.today(), usd=0.0, ips={})
        if _ledger["usd"] >= DAILY_USD:
            return f"Today's ${DAILY_USD:.0f} budget for live runs is spent. The recorded runs still replay."
        if _ledger["ips"].get(ip, 0) >= PER_IP:
            return "You've used today's live runs. The recorded runs still replay."
        _ledger["ips"][ip] = _ledger["ips"].get(ip, 0) + 1
    return None


def run_sample(sid: str, emit, client: Client | None = None, budget: float = 0.60) -> dict:
    """Run the agent on one preloaded sample; emit(event, data) is called per turn and at the end."""
    client = client or Client(budget)
    run = Run(sample_frames(sid), client, sid)
    try:
        run_agent(run, on_turn=lambda t: emit("turn", t))
    except NoKey as e:
        print(f"live run {sid}: {e}")  # the detail stays in the server log; visitors get a plain sentence
        emit("error", {"message": "The live models aren't connected right now."})
        return {"status": "error"}
    except BudgetExceeded:
        emit("error", {"message": "This run hit its spending cap and was stopped."})
        return {"status": "error"}
    finally:
        with _lock:
            _ledger["usd"] += client.spent
    save(run, OUT / sid)
    result = json.loads((OUT / sid / "run.json").read_text())
    emit("done", {"status": run.status, "dir": f"live/{sid}/"})
    return result


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(WEB), **k)

    def translate_path(self, path):
        if path.startswith("/live/"):  # finished live runs; never let ".." climb out of runs/live
            p = (OUT / path[len("/live/"):].split("?")[0].split("#")[0]).resolve()
            return str(p) if p.is_relative_to(OUT.resolve()) else str(WEB / "__missing__")
        return super().translate_path(path)

    def do_POST(self):
        if self.path != "/api/run":
            return self.send_error(404)
        try:
            body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 2048)) or b"{}")
            sid = str(body.get("sample", ""))
            sample_frames(sid)
        except (ValueError, KeyError):
            return self.send_error(400, "unknown sample")
        ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()
        why = allow(ip)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def emit(event, data):
            self.wfile.write(f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n".encode())
            self.wfile.flush()
        if why:
            return emit("error", {"message": why})
        t0 = time.time()
        run_sample(sid, emit)
        self.log_message("run %s in %.1fs", sid, time.time() - t0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    a = ap.parse_args()
    print(f"CatchLength console on http://{a.host}:{a.port}")
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
