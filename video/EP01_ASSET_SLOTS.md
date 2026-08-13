# EP01 «Хочу уточку» — Remotion asset slots

Source timeline: `series/Бойся своих желаний/storyboards/EP01_WISH_DUCK.md`.
Canon priority remains `series/Бойся своих желаний/canon/CANON_INDEX.md`.

This file is an assembly checklist, not a new visual authority.

## What is already deterministic

- 11 shots: SH010–SH110;
- master duration: exactly 50 seconds;
- 9:16, 1080×1920, 30 fps;
- production class per shot;
- scene order and timing;
- dialogue/caption windows;
- camera treatment for limited shots;
- layer/parallax slots;
- timed SFX cues;
- fallback animatic slates for unresolved assets.

## Expensive motion budget

Only two slots require new full AI-video generation:

1. `EP01_SH010_AI_VIDEO` — 3 sec cold open;
2. `EP01_SH080_AI_VIDEO` — 6 sec escalation.

`EP01_SH090_CALLBACK_EDIT` is explicitly **reuse/edit**, built from SH010 material plus an approved continuation/crop. It must not silently become another 8 seconds of fresh expensive generation.

Target unique full-AI motion therefore remains approximately **9 seconds**, matching the production script.

## Limited-animation visual slots

### Workshop camera masters

- `BG_WORKSHOP_WIDE`
- `BG_WORKSHOP_TWO_SHOT`
- `BG_WORKSHOP_MACHINE_MEDIUM`
- `BG_WORKSHOP_KLEPP_CLOSE`
- `BG_WORKSHOP_FINCH_CLOSE`
- `BG_WORKSHOP_PLUG_INSERT`

These must derive from `WORKSHOP_MASTER`; do not rebuild the workshop layout shot-by-shot.

### Klepp layers

- `CHAR_KLEPP_PRESENTING`
- `CHAR_KLEPP_CONFIDENT`
- `CHAR_KLEPP_FAKE_CALM`
- `CHAR_KLEPP_DELIGHT`
- `CHAR_KLEPP_SURPRISE`

All derived Klepp assets must preserve the approved model sheet, left-eye telescopic monocle and right mechanical hand with exactly three fingers.

### Finch layers

- `CHAR_FINCH_NOTEBOOK`
- `CHAR_FINCH_SKEPTICAL`
- `CHAR_FINCH_CONCERN`
- `CHAR_FINCH_BACKPACK_OPEN`

All Finch layers must preserve the approved adult proportions, brass round glasses, red-orange scarf and mustard backpack-cabinet.

### Machine / prop layers

- `WISH_MACHINE_IDLE`
- `WISH_MACHINE_ACCEPT`
- `PROP_SANDWICH`
- `PROP_COINS_10`
- `PROP_MULTIPLIER`
- `PROP_DUCK_SAMPLE_184`
- `PROP_DUCK_SINGLE`
- `PROP_DUCK_PILES`
- `PROP_POWER_PLUG`

## Audio slots currently needed

- `AUD_MACHINE_PUFF`
- `AUD_COIN_MONOCLE`
- `AUD_DUCK_DROP`
- `AUD_POWER_UNPLUG`
- `AUD_DUCK_SQUEAK`
- `AUD_QUACK_SINGLE`
- `AUD_QUACK_MASS`

The manifest already stores the intended in-shot offsets. Audio files can be attached later without changing edit timing.

## How to attach an approved asset

1. Put/export the render-safe file under `video/public/`, for example `video/public/ep01/sh010.mp4`.
2. In `video/manifests/ep01-wish-duck.json`, find the matching asset slot.
3. Set `src` to a path relative to `video/public/`, e.g. `ep01/sh010.mp4`.
4. Use `status: "draft"` while reviewing it in Studio.
5. Change to `status: "approved"` only after the existing canon/shot gate passes.

Never point an `approved` slot at an old/non-canon image merely to remove a placeholder.

## Definition of animatic-ready

The structural animatic is ready when the manifest parses and the 50-second composition renders, even if visual slates remain.

## Definition of master-ready

- no required visual/audio slot remains `missing`;
- no production asset remains `draft`;
- SH010 and SH080 passed their shot gates;
- SH090 is verified as reuse/edit rather than new hidden generation;
- captions and action survive the 9:16 safe-area check;
- final render passes QC.
