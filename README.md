# CatchLength

A fish-sampling agent that measures every fish in a phone clip and can't skip checking its own work.

Sri Lanka already measures coastal tuna from photographs: field staff lay fish on a board, take a photo, then click the snout and the tail fork of each fish by hand and name its species. CatchLength does the clicking. You film about 20 seconds of fish laid next to printed marker sheets, and an agent built on Meta's models plans the job, finds every fish, measures each one twice, hands anything it can't settle to a person, and files a length-frequency report that cites the rule behind every check.

Built for the Meta Global AI Developer Hackathon (Indie track), theme Build for Your World. All code in this repository was written from 27 October 2026.

## How it checks itself

The checks sit inside the agent's tools, so the model can't skip them.

- Calibration refuses a clip when the marker tiles are missing or bent (corner error over 1.5 px).
- If SAM 3.1 finds fewer fish than Muse Spark expects, Spark returns boxes for the missed or merged fish, and they go back to SAM as box prompts with negative points on the neighbouring fish. A new mask is kept only if its size looks like one fish and it doesn't overlap one already found.
- Each fish is measured twice: an outline length on the sheet's plane and a snout-to-fork length from Spark's points. If the two disagree, the fish is flagged for the officer.
- Spark's snout and fork points are moved onto the outline SAM drew, and the fork length is measured between the moved points. A point that sat more than 8 px from the outline, inside or outside the fish, means the two models disagree about where the fish ends, so the fish is flagged instead of snapped.
- The fish are measured again in two other frames, and a length that moves by more than 1 cm is flagged.
- For species with a published length-length relationship (frigate and bullet tuna, IOTC-2021-WPNT11-14), the outline must be within 3% of the total length that relationship predicts from the fork length, or the fish is flagged.
- No minimum landing size for the tunas and mackerel sampled here was found in the sources we reviewed (Sri Lanka's gazetted fisheries regulations, `data/rules.json`), and the report says "no rule found" for each of them. Rules come only from a pack with a source for each, and model-written text that cites any other rule is refused.
- A tool refused three times hands the job to the officer, and a filed report waits for the officer's sign-off.
- A benchmark compares the agent's lengths with the same fish measured by hand on a measuring board. The agent never sees those numbers.

Every run ends with an audit receipt: the clip's hash, the models used, the calibration error, which fish were rescued, the frames checked, how far Spark's points sat from SAM's outlines (median, worst fish, how many over the limit), the cost, the code version and the hash of the CSV. The code version names the freeze tag (`scripts/freeze.py`, made before the field shoot) and says whether the code and thresholds still match it; the thresholds themselves are printed too.

## Meta models

| Model | Job |
|---|---|
| Muse Spark 1.3 | Runs the agent loop (one tool per turn); plans the clip; finds missed and merged fish; places snout and fork points; names the species from a closed list |
| SAM 3.1 | Segments every fish from the concept "fish", then again from Spark's boxes and negative points |

## Prior art

Measuring fish from images isn't new. The closest tools we know of:

| Tool | How it works | Published numbers |
|---|---|---|
| FishNet (Mots'oehli et al., IEEE COINS 2024, [arXiv 2403.10916](https://arxiv.org/abs/2403.10916)) | Mask R-CNN and length models trained on 300,000 hand-labelled images (1.2 million fish, 163 species) | 92% IoU on segmentation, 89% top-1 species accuracy on single-fish images, 2.3 cm mean absolute length error, all on its own held-out data |
| MatsyaMetri (ICAR-CMFRI, Kochi, [Sep 2026](https://www.icar.org.in/en/icar-cmfri-kochi-develops-smartphone-app-measure-fish-length-and-width-without-physical-handling)) | Augmented-reality phone app: finds a flat surface and measures length and width, exports CSV; ARCore Android phones only | No accuracy figure published that we could find |
| FishSense Lite (UC San Diego and REEF, [GCFI 77 proceedings](https://proceedings.gcfi.org/wp-content/uploads/2026/02/77-GCFI-PDF-27.pdf)) | Underwater camera (Olympus TG6) with a laser for range, carried by volunteer divers | Thousands of fish of 11 species, 37 volunteers, 230 dives (Aug 2023 to Oct 2024); lengths not statistically different from stereo-video (Kruskal-Wallis p = 0.481, n = 66) |

CatchLength differs in three ways: it isn't trained on fish at all (Meta's models are used as they ship), it needs only printed paper tiles and any phone camera (no AR support, laser or second camera), and each length is checked by a second method and other frames, with the fish handed to a person when the checks disagree. FishNet's numbers come from a much larger dataset of its own, so they can't be compared directly with our field benchmark.

The workflow it automates is Sri Lanka's own photo-board sampling, presented by NARA to the IOTC (IOTC-2025-WPM16-10).

## Benchmark

Field results from fish measured at the Peliyagoda fish market will be added here after 1 November 2026. The console's Benchmark tab reads `web/benchmark.json`.

Declared before the shoot: the ground truth is fork length on a measuring board; 10 fish are measured twice to give the tape's own error; fish tags 4, 8 … 40 are held out, so any bias correction is fitted on the other fish and scored on those 10; and the same 10 fish are timed by hand and with the agent.

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

Grade a field day (runs every clip, writes a tags file per clip to fill in from its overlay, then grades):

```bash
.venv/bin/python scripts/field_day.py data/raw/<day> --manual-s 300 --film-s 90
```

Or grade runs directly:

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
