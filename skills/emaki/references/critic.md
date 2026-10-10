# Critic: an independent review before the final

The agent that wrote video.py is a kind judge of its own frames. An early 10-second test passed
QA and its builder's frame review, and the person who asked for it still called it "a
presentation, monotonous motion, the sound is off". The critic is a separate pass that sees only
the evidence and a binary rubric.

## When

Twice, at the two gates, before the user sees anything:
- **Gate 1 (style frames):** items 8, 10 (look promises only) and 14-15, on `out/frames/*.png`
  next to the reference sheets. The look is cheap to fix here and expensive after animation.
- **Gate 2 (animatic):** the whole rubric, after `mv.py preview` reports no FAIL. Fix everything
  it finds in one repair pass, run it again. If the second verdict is still FAIL on items 1-4,
  the problem is the plan, not the code: go back to stage 1, do not patch.
Never shorten or lengthen a scene to hide a defect.

## How

1. Produce the evidence:
   ```bash
   $MV timeline <dir>                       # out/timeline.png: choreography map
   $MV strips <dir> --ref <reference id>    # out/strips.png: 12 fps around P.keyframes
   ```
2. If the Agent (Task) tool is available, spawn a subagent with the prompt below. It must not get
   your reasoning, only the files. Without the tool, do the pass yourself as a separate step:
   open only the listed files and answer every item before you look at your own notes.
3. The critic writes `out/critic.md`. Fix every NO, re-run preview, timeline, strips, critic.

## Inputs (paths relative to the project)

- `brief.yaml`, `design.yaml` (concept, signature, dynamics, sound), `storyboard.md` (action chains,
  hand-offs)
- `out/qa_preview.md`, `out/timeline.png`, `out/strips.png`, `out/preview_contact*.png`
- the reference the design points to: the sheets `mv.py analyze-ref` wrote (`<file>_analysis/`),
  or with a library `<motion-lib>/references/<id>/sheet_*.png` and `breakdown.md`, and
  `<motion-lib>/references/INDEX.md` ("what the references have in common"
  is the user's taste)

## Rubric

Every item is YES or NO. "Mostly" is NO. Every answer cites evidence: a timestamp and the file
it was seen in. Any NO makes the verdict FAIL.

A. Motion design, not a presentation
1. Every change of idea is a hand-off: an element of the previous idea carries over, transforms
   or leads into the next one. Name the element and the timestamps.
2. Every lead element does at least two things (timeline: a blue bar after the green one).
3. No row of the strips ends in a finished layout that just waits (the second half of a row
   showing the same picture with only the camera drifting is a NO).
4. Every 3-4 s there is a moment worth remembering (a transformation, a hit, a reveal with a
   twist). Describe each in five words.

B. Variety and rhythm
5. Lead, support and detail elements enter differently.
6. Speed contrast is visible: at least one fast hit (<= 0.3 s) and one slow build (>= 0.8 s).
7. Actions overlap: the next starts before the previous lands (strips show two things moving
   in the same tiles).

C. Against the reference and the plan
8. Side by side with the reference at comparable moments, our lead element has comparable
   scale, the frame comparable density and finish (glow, blur, texture, depth). Name the
   biggest gap in one line.
9. The signature move from design.yaml appears on screen and repeats as promised (timestamps).
10. Every promise in design.yaml and storyboard.md is on screen. List each promise with the
    timestamp where it is seen, or "missing".

D. Craft
11. Nothing important is cut by the frame edge; no unintended overlaps; no empty frame where the
    camera lands.
12. Every phrase is readable (size, contrast, time on screen).

E. Sound (on paper: nobody in this session can listen)
13. Sound effects sit on hand-offs and the signature moment, not on every event; the bed's
    genre, tempo and spectrum match the reference type (`out/qa_preview.md` sound lines).
    Always add: "check by ear".

F. Light and finish (art_direction.md 5b; QA `look` lines)
14. Every frame has a light logic: a source you can point at (key light, gradient light, glow),
    a real dark and a real light, shadows that agree with the light. Flat grey-on-grey is NO.
15. Objects have material (soft shadow, glass, sheen, depth of field) where the reference has it;
    the accent is on screen at every key moment. Name the frame that looks most like a UI
    screenshot, or "none".

Last line, one sentence: would a motion designer post this, or does it read as an animated
slide deck?

## Output: out/critic.md

```markdown
# Critic: FAIL                       (PASS only when every item is YES)

| # | item | YES/NO | evidence (time, file) | fix (one concrete change in video.py) |
|---|---|---|---|---|
| 1 | hand-offs | NO | 2.5 s and 5.0 s, strips row 2: badges appear where the camera lands | morph the underline into the spine; pills fly out of the third badge |
...

Gestalt: ...
```

## Prompt for the subagent

> You are a senior motion designer reviewing a 10-60 s motion video before it ships. You did not
> make it and owe its maker nothing. Read `<skill>/references/critic.md` (rubric and output
> format), then open these files and nothing else: <list the inputs with absolute paths>.
> Answer every rubric item YES or NO with evidence (timestamp + file). "Mostly" is NO. For every
> NO give one concrete change to video.py. Write the result to `<project>/out/critic.md` and
> return the verdict line and the NO items.
