# CatchLength

A fish-sampling agent that measures every fish in a phone clip and can't skip checking its own work.

Sri Lanka already measures coastal tuna from photographs: field staff lay fish on a board, take a photo, then click the snout and the tail fork of each fish by hand and name its species. CatchLength does the clicking. You film about 20 seconds of fish laid next to printed marker sheets, and an agent built on Meta's models plans the job, finds every fish, measures each one twice, hands anything it can't settle to a person, and files a length-frequency report that cites the rule behind every check.

Built for the Meta Global AI Developer Hackathon (Indie track), theme Build for Your World. All code in this repository was written from 27 October 2026.

## How it checks itself

The checks sit inside the agent's tools, so the model can't skip them.

- Calibration refuses a clip when the marker tiles are missing or bent (corner error over 1.5 px).
- If SAM 3.1 finds fewer fish than Muse Spark expects, Spark returns boxes for the missed or merged fish, and they go back to SAM as box prompts with negative points on the neighbouring fish. A new mask is kept only if its size looks like one fish and it doesn't overlap one already found.
- Each fish is measured twice: an outline length on the sheet's plane and a snout-to-fork length from Spark's points. If the two disagree, or the points fall off the fish, the fish is flagged for the officer.
- The fish are measured again in two other frames, and a length that moves by more than 2 cm is flagged.
- Sri Lanka gazettes no minimum landing size for the tunas sampled here, and the report states that for each of them. Rules come only from a pack with a source for each, and model-written text that cites any other rule is refused.
- A tool refused three times hands the job to the officer, and a filed report waits for the officer's sign-off.
- A benchmark compares the agent's lengths with the same fish measured by hand with a tape. The agent never sees those numbers.

Every run ends with an audit receipt: the clip's hash, the models used, the calibration error, which fish were rescued, the frames checked, the cost, the code version and the hash of the CSV.

## Meta models

| Model | Job |
|---|---|
| Muse Spark 1.3 | Runs the agent loop (one tool per turn); plans the clip; finds missed and merged fish; places snout and fork points; names the species from a closed list |
| SAM 3.1 | Segments every fish from the concept "fish", then again from Spark's boxes and negative points |

## Benchmark

Field results from fish measured at the Peliyagoda fish market will be added here after 1 November 2026. The console's Benchmark tab reads `web/benchmark.json`.

How much error the camera and the marker tiles add on their own, before any model is involved: on 112 synthetic fish in 30 scenes degraded like a 1080p phone frame from about 1 m (blur, sensor noise, JPEG), measured from each fish's true outline, the mean length error is 0.16 cm (90th percentile 0.31 cm, worst 0.53 cm). This is a synthetic test of the geometry only (`scripts/geometry_budget.py`); the field benchmark measures the whole agent.

## Run it

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
echo "MODEL_API_KEY=..." > .env          # a Meta Model API key; never commit it
.venv/bin/python -m catchlength.cli path/to/clip.mp4     # writes runs/<clip>/run.json, catch.csv, frame.jpg
.venv/bin/python -m catchlength.server                    # the console at http://127.0.0.1:8000
.venv/bin/python -m pytest -q                             # tests (no key needed)
```

Print `print/catchlength_A4_tiles.pdf` at 100% and check that each sheet's bar measures 100 mm. Lay at least two tiles flat on the same surface as the fish.

Grade runs against tape measurements:

```bash
.venv/bin/python -m catchlength.audit ground_truth.csv runs/clip1/ runs/clip2/ --out web/benchmark.json
```

## Cost and limits

Estimated at under $0.40 per clip at standard prices (SAM 3.1 is $2.50 per 1,000 images; Muse Spark 1.3 is $1.25 and $4.25 per million input and output tokens). Each run stops at $0.60. The public server runs only preloaded samples, a few per visitor per day, under a daily cap; repeat runs replay cached model responses.

Limits: a closed list of five coastal species (skipjack, kawakawa, Indian mackerel, frigate and bullet tuna), anything else is "unknown"; fish laid flat on a flat surface; daylight; no Sinhala voice input (Muse Voice Transcribe doesn't support Sinhala).

## Before the hackathon

The idea and the application text. The museum fish photographs in `data/sources/` are Smithsonian (USNM) specimens, public domain via Wikimedia Commons (each file and its source is listed in `data/sources/sources.txt`). They are used only for tests and the simulated sample, which is labelled wherever it appears.

## Licence

MIT
