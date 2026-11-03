# Build log

What was built each day of the hackathon, from the commit history (dates in Sri Lanka time).

## Tue 27 Oct

- Start the Meta Global AI entry: MIT licence, gitignore

## Wed 28 Oct

- Marker mat generator and detection, museum fish cut-outs (written this day, committed on 29 Oct)

## Thu 29 Oct

- Ignore private notes, caches and local tooling
- Marker tiles, plane geometry and the printable A4 tile set
- Museum reference fish for tests (Smithsonian USNM, public domain)
- SAM 3.1 and Muse Spark calls, cached and budget-capped
- The sampling agent: checks inside its tools, escalation, cited rules
- Benchmark grader against tape measurements the agent never sees
- Agent console: replays recorded runs; a labelled simulated sample
- Run server: live agent runs on preloaded samples, streamed turn by turn
- Console polish: verdict in figures, a live stage strip, fork lines on every fish

## Fri 30 Oct

- Agent loop sends tool_choice "auto" (the Meta API rejects "required") and nudges a reply that calls no tool
- Printable ground-truth sheet for the market shoot; frigate and bullet tuna added to the species list
- Audit screen: the geometry error floor before the shoot; pass marks, limits of agreement, largest errors and per-clip counts once the tape data is in
- SAM masks placed as box-local rasters, stretched over the box when coarser
- .env.example lists the one key live runs need

## Sun 1 Nov

- Tighter cross-checks: the outline must sit within 3% of the species' published TL-from-FL (frigate and bullet tuna), and a length may drift at most 1 cm across frames
- Freeze script: code and thresholds tagged before the field shoot; receipts print the tag
- Field-day runner works end to end on a clip: ground-truth validation, the held-out bias split, tape repeatability and the stopwatch comparison
- Ground-truth sheet: a second fork length column for the repeat measurements
- Muse Spark's snout and fork points snapped onto SAM 3.1's outline; how far they sat from it is a check in every receipt
- README: prior art (FishNet, MatsyaMetri, FishSense Lite) with their published numbers; the minimum-size claim limited to the sources reviewed

## Tue 3 Nov

- First real Meta calls: smoke test passed; the three console samples recorded on Muse Spark 1.3 and SAM 3.1
- Spark's first look no longer stops a job on its own: on real runs it called separated fish "stacked" or "cut off", so its worries go to the officer and the deterministic checks decide
- Every parallel tool call gets an answer (a real run returned two at once, which the API then rejected)
- Point-snap limit in millimetres on the sheet (1 cm, one length bin) instead of 8 image pixels; on the clean sample accepted fish went from 0 of 5 to 4 of 5, and the fish whose snout point sat 2 cm out in open water is still flagged
- Re-frozen as freeze-2026-11-03 before the field shoot; the tag lists every change since the first freeze
- Seller's size receipt, benchmark led by held-out bias against NARA's photo method, open-weights auditor path

Before 27 October: the idea and the application text only.
