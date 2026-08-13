# REMOTION INTEGRATION v0.2

## Purpose

Remotion is the deterministic assembly and rendering layer for the animation production workspace. It sits after approved shot planning and between asset production and QC/master export.

It does not replace the niche-research pipeline, series canon, shot approval, image/video generators, voice generation, or human creative approval.

## Architecture

```text
idea / script
  -> storyboard / animatic plan
  -> shot approval
  -> episode manifest + asset slots
  -> asset production
     - layered stills
     - generated motion clips
     - voice / SFX / music
  -> Remotion assembly
     - timing
     - asset resolution / diagnostic slates
     - limited camera + parallax
     - captions
     - timed audio events
  -> QC
  -> master render
  -> platform derivatives
```

The manifest can exist before every asset is ready. Missing media stays explicit as a slot and renders as a diagnostic slate. This allows timing/structure review without contaminating canon or triggering premature expensive generation.

## Repository layout

```text
video/
  manifests/
    example.json
    ep01-wish-duck.json
  public/                    # render-safe approved/draft media
  EP01_ASSET_SLOTS.md        # first real asset checklist
  src/
    Episode.tsx              # manifest-driven assembly
    Root.tsx                 # compositions and metadata
    types.ts                 # manifest/asset/layer/audio schema
  out/                       # renders; ignored
```

Local production policy lives at `.agents/skills/video-production/SKILL.md`.
Official Remotion skills remain upstream dependencies and should be installed with `npm run skills:install`.

## Data contract

### Episode

- stable ID and optional title;
- width/height/FPS;
- global asset registry;
- ordered scene list;
- timed captions;
- optional music.

### Asset registry

Each asset slot has:

- `type`: image / video / audio;
- `status`: missing / draft / approved;
- optional `src`;
- optional source-of-truth reference;
- optional production note.

Safety behavior:

- `missing` visual assets render as diagnostic slates;
- `draft` visual assets can render for review but receive a visible DRAFT marker;
- `approved` assets render cleanly;
- missing audio events are skipped rather than replaced with invented sounds.

### Scene

Each scene stores:

- stable shot ID;
- duration in seconds;
- production class;
- source shot spec;
- story beat;
- base visual or asset slot;
- deterministic camera treatment;
- optional transparent layers with parallax;
- optional scene text;
- timed audio events;
- backward-compatible direct voice/SFX fields.

### Layered limited animation

Layer transforms are intentionally conservative. Approved full-frame transparent PNG/video layers can receive:

- scale;
- x/y offset;
- opacity;
- z-index;
- contain/cover fitting;
- independent x/y parallax;
- the scene-level camera move.

This is the default way to create motion from approved still assets before requesting fresh generated video.

## First real composition: EP01 «Хочу уточку»

`video/manifests/ep01-wish-duck.json` mirrors the approved 11-shot, 50-second storyboard.

Production split:

- SH010: full AI-video, 3 sec;
- SH020–SH070: limited / limited+FX;
- SH080: full AI-video, 6 sec;
- SH090: reuse/edit of the cold-open material plus continuation;
- SH100: limited+FX;
- SH110: sound-led limited punchline.

Unique new expensive motion target remains approximately 9 seconds. Remotion must not turn SH090 into hidden fresh-generation scope.

## Rendering

From `video/`:

```bash
npm install
npm run check
npm run render:example
npm run render:ep01
```

`render:example` is the dependency/toolchain smoke composition.
`render:ep01` is the real structural animatic and should render even while approved media is missing because unresolved slots become diagnostic slates.

## Cost rule

Remotion should reduce expensive generation, not increase it. Limited animation, reframing, parallax, captions, overlays and audio timing should be handled in code whenever acceptable quality can be reached from approved assets.

`technical/PRODUCTION_PIPELINE.md` remains authoritative: expensive generated video is reserved for moments where motion is the visual event and only after animatic/shot approval.

## Versioning

All `remotion` and `@remotion/*` packages must use one exact version. The current scaffold pins `4.0.509`. Upgrades should use the official `remotion-upgrade` skill plus typecheck and smoke render.

## Next engineering priorities

Only add these after the EP01 structural render is validated:

1. production caption presets and speaker-safe positioning;
2. audio buses / loudness policy / ducking;
3. explicit transition presets where hard cuts are insufficient;
4. asset-registry validator that reports unresolved required slots;
5. frame/contact-sheet QC for safe areas and missing media;
6. render queue when batch volume justifies remote infrastructure.
