---
name: video-production
description: Assemble approved animation assets into reproducible Remotion episodes, shorts, previews, captions, audio and renders without bypassing production approval gates.
version: 0.2.0
---

# Video Production

Use this skill for Remotion-based episode assembly, animatics, edit automation, captions, audio placement, limited motion, preview and rendering in this repository.

## Role

Remotion is the deterministic production layer. It does **not** decide canon and does **not** authorize expensive AI-video generation.

Intended chain:

`approved idea/script -> approved shot plan -> manifest + asset slots -> approved/draft assets -> Remotion assembly -> QC -> render`

A manifest may be assembled before every media asset is ready. Missing slots must remain explicit diagnostic data.

## Required context

Before editing a real episode:

1. Read `technical/PRODUCTION_PIPELINE.md`.
2. Read `technical/SHOT_APPROVAL_GATE.md`.
3. Read `technical/REMOTION_INTEGRATION.md`.
4. Read the active series `canon/CANON_INDEX.md` first, then the current script/storyboard/shot specs and approved references it routes to.
5. Treat missing approvals as missing data. Do not infer a new canonical face, costume, prop, location, voice or visual style.

## Upstream Remotion knowledge

Use the official Remotion Agent Skills for current API/implementation knowledge. Install or refresh them from `video/` with:

`npm run skills:install`

Use upstream specialist skills for markup, captions, rendering, Studio, multimedia and upgrades. Do not vendor upstream skill contents into this repository.

## Manifest-first workflow

1. Convert the approved shot list into a manifest matching `video/src/types.ts`.
2. Preserve stable shot IDs and exact storyboard duration unless the creative source explicitly changes.
3. Register expected media in `manifest.assets` instead of inventing file paths.
4. Each asset slot must record type, status and source-of-truth context when available.
5. `missing` means placeholder/skip, never substitute.
6. Use `draft` only for a real review asset; visual drafts remain visibly watermarked by the renderer.
7. Use `approved` only after the repository's existing canon/shot gate passes.
8. Prefer limited-animation layers and deterministic camera/parallax for still material.
9. Use full generated motion only for shots already classified for it by the production plan.
10. Put mid-shot sounds in timed `audioEvents`; do not force every SFX to start at frame zero.
11. Keep captions as global timed data and inside mobile-safe composition.

## EP01 reference implementation

The first real manifest is:

`video/manifests/ep01-wish-duck.json`

It mirrors `series/Бойся своих желаний/storyboards/EP01_WISH_DUCK.md`:

- SH010 full AI-video, 3 sec;
- SH020–SH070 limited / limited+FX;
- SH080 full AI-video, 6 sec;
- SH090 reuse/edit;
- SH100 limited+FX;
- SH110 sound-led.

Do not turn SH090 into new hidden full-generation scope. Unique expensive motion remains approximately 9 seconds.

Asset checklist: `video/EP01_ASSET_SLOTS.md`.

## Quality gates

Before declaring an episode master-ready:

- every scene ID is stable and unique;
- timeline duration equals the intended storyboard duration;
- no required visual/audio slot remains `missing`;
- no production asset remains `draft`;
- captions stay inside mobile-safe area and do not cover critical action;
- aspect ratio and FPS match the intended master;
- no accidental intro card appears before the hook;
- render is reproducible from manifest + assets + code;
- changes do not alter canon;
- expensive generated seconds stay within the approved production plan.

A structural animatic may be considered review-ready with missing slots if they render as diagnostic slates and the missing list is reported explicitly.

## Validation

From `video/`:

- `npm install`
- `npm run check`
- `npm run studio`
- `npm run render:example`
- `npm run render:ep01` for the real EP01 structural animatic
- `npm run render -- --props=<manifest.json>` for a generic manifest

If Node/Chromium/dependencies/network access blocks validation, report the exact blocker and do not claim PASS.

## Output expectation

For each production change, report:

- manifest(s) touched;
- reusable components changed;
- validation executed;
- rendered output path when available;
- unresolved missing assets/approvals;
- expensive generative steps still required and their planned seconds.
