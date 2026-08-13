---
name: video-production
description: Assemble approved animation assets into reproducible Remotion episodes, shorts, previews, captions, audio and renders without bypassing production approval gates.
version: 0.1.0
---

# Video Production

Use this skill for Remotion-based episode assembly, edit automation, captions, audio placement, motion treatment, preview and rendering in this repository.

## Role

Remotion is the deterministic production layer. It does **not** decide canon and it does **not** authorize expensive AI-video generation.

The intended chain is:

`approved idea/script -> approved animatic/shot list -> approved assets -> episode manifest -> Remotion assembly -> QC -> render`

## Required context

Before editing a real episode:

1. Read `technical/PRODUCTION_PIPELINE.md`.
2. Read `technical/SHOT_APPROVAL_GATE.md`.
3. Read `technical/REMOTION_INTEGRATION.md`.
4. Read the active series `CANON.md`, current episode/shot material, and approved references.
5. Treat missing approvals as missing data. Do not infer a new canonical face, costume, prop, location, voice or visual style.

## Upstream Remotion knowledge

Use the official Remotion Agent Skills for API and implementation knowledge. Install or refresh them from the `video/` workspace with:

`npm run skills:install`

The upstream router is `remotion-best-practices`; use its specialist skills for markup, captions, rendering, Studio, multimedia and upgrades.

Do not copy upstream skill contents into this local skill. The local skill owns repository-specific production policy; upstream owns Remotion technical best practices.

## Manifest-first workflow

1. Convert the approved shot list into an episode manifest matching `video/src/types.ts`.
2. Keep each scene explicit: stable `id`, duration, visual source, camera treatment, optional voice/SFX, and optional scene text.
3. Prefer cheap limited-animation treatments (`push-in`, `push-out`, `pan-left`, `pan-right`) for layered/still material.
4. Use generated full-motion clips only where the approved production plan calls for them.
5. Missing media must be represented by a diagnostic color/placeholder scene. Never silently substitute an unapproved asset.
6. Keep timing in seconds in the manifest; convert to frames in Remotion using the manifest FPS.
7. Keep captions as timed data, not hand-positioned timeline fragments.
8. Keep branding/safe-area behavior in reusable components rather than repeating it per episode.

## Quality gates

Before declaring an episode render-ready:

- every scene ID is stable and unique;
- timeline duration equals the sum of scene durations;
- no missing referenced local media;
- captions stay inside mobile-safe area and do not cover critical action;
- voice/SFX paths resolve;
- aspect ratio and FPS match the intended master;
- no accidental intro card before the hook;
- render is reproducible from the manifest;
- changes do not alter series canon.

## Validation

From `video/`:

- `npm install`
- `npm run check`
- `npm run studio` for interactive preview
- `npm run render:example` for a dependency-free smoke composition
- `npm run render -- --props=<manifest.json>` for a real manifest

If a command cannot run because the environment lacks Node/Chromium/dependencies, report the blocker precisely and do not claim the render passed.

## Output expectation

For each production change, report:

- manifest(s) touched;
- reusable components changed;
- validation executed;
- rendered output path when available;
- unresolved missing assets/approvals;
- whether any expensive generative step is still required.
