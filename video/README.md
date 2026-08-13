# Remotion video workspace

Deterministic assembly/render workspace for approved animation assets.

## Setup

```bash
cd video
npm install
npm run check
npm run studio
```

Install or refresh official Remotion Agent Skills:

```bash
npm run skills:install
```

## Smoke render

The bundled example uses only color slates and text, so it can validate the Remotion toolchain without production media:

```bash
npm run render:example
```

Expected output: `video/out/example.mp4`.

## EP01 animatic

The first real episode manifest is `manifests/ep01-wish-duck.json`. It mirrors the approved 50-second storyboard for «Хочу уточку» and intentionally starts with unresolved asset slots.

```bash
npm run render:ep01
```

Expected output: `video/out/ep01-wish-duck-animatic.mp4`.

When an asset slot has no approved media, the composition renders a diagnostic slate instead of inventing a substitute. This means the whole 50-second timeline can be reviewed before expensive generation is complete.

## Asset slots

`manifest.assets` is the bridge between canon/shot specs and renderable media.

Each slot stores:

- media type: image / video / audio;
- status: `missing`, `draft`, or `approved`;
- optional `src` relative to `video/public/` (or an absolute URL);
- source-of-truth reference back to the series docs.

Draft visual assets may be previewed with a visible `DRAFT ASSET` marker. Missing assets remain slates. Approved assets render normally.

The EP01 slot inventory is documented in `EP01_ASSET_SLOTS.md`.

## Limited animation

Scenes can contain reusable transparent media layers. Each layer supports:

- scale and XY offsets;
- opacity and z-index;
- cover/contain fitting;
- independent X/Y parallax;
- the scene camera presets `static`, `push-in`, `push-out`, `pan-left`, `pan-right`.

This is the default path for shots that do not need new full-motion AI video.

## Audio events

Scene-local SFX/dialogue cues can reference audio asset slots with a precise offset in seconds. This avoids the old limitation where every SFX had to begin at the start of the shot.

## Generic rendering

Create or modify a manifest based on an approved shot list and assets, then:

```bash
npm run render -- --props=manifests/<episode>.json
```

Local media paths resolve from `video/public/`. Absolute `http(s)`, `data:` and `blob:` sources are passed through.

## Manifest principles

- scene order is manifest order;
- scene timing is stored in seconds;
- frame counts are derived from manifest FPS;
- image scenes can use deterministic limited camera/parallax motion;
- video scenes use approved motion clips;
- missing media is represented explicitly through asset slots;
- timed SFX are scene data;
- captions are global timed data;
- missing approvals remain diagnostic placeholders, not invented assets.

See `technical/REMOTION_INTEGRATION.md` and `.agents/skills/video-production/SKILL.md` for repository policy.
