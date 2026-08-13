# REMOTION INTEGRATION v0.1

## Purpose

Remotion is the deterministic assembly and rendering layer for the animation production workspace. It sits after approved assets and before QC/master export.

It does not replace the niche-research pipeline, series canon, shot approval, image/video generators, voice generation, or human creative approval.

## Architecture

```text
idea / script
  -> storyboard / animatic
  -> shot approval
  -> approved assets
     - layered stills
     - generated motion clips
     - voice
     - SFX / music
  -> episode manifest (data contract)
  -> Remotion
     - timing
     - composition
     - limited camera motion
     - captions
     - audio placement
     - reusable branding / safe areas
  -> QC
  -> master render
  -> platform derivatives
```

## Repository layout

```text
video/
  manifests/        # episode/short input data
  public/           # local render assets (add per production task)
  src/
    Episode.tsx     # manifest-driven assembly
    Root.tsx        # Remotion Composition and metadata
    types.ts        # manifest schema
  out/              # renders; ignored by default when local tooling is configured
```

The local agent policy lives at `.agents/skills/video-production/SKILL.md`.

Official Remotion skills are upstream dependencies for agent knowledge and should be installed with `npm run skills:install`, not copied into this repository.

## Data contract

The episode manifest is the handoff between creative/asset production and deterministic assembly.

Required principles:

- stable scene IDs;
- explicit duration per scene;
- explicit visual kind (`color`, `image`, `video`);
- explicit local path or remote URL for media;
- explicit camera treatment;
- timed captions as data;
- optional voice/SFX/music as referenced media;
- width/height/FPS belong to the manifest so master presets are reproducible.

## Missing-asset behavior

A missing approval is not permission to invent an asset. Keep a diagnostic placeholder in the manifest until the reference is approved and available.

This makes rough assembly possible without contaminating canon or silently increasing generation cost.

## Rendering strategy

### Phase 1: local/server render

Use Remotion CLI from `video/`. This is the default until render volume makes distributed infrastructure worthwhile.

### Phase 2: queue + remote render

When batch volume justifies it, add a queue and remote renderer (for example Remotion Lambda or another supported backend). Preserve the same manifest contract so infrastructure can change without changing episode semantics.

## Cost rule

Remotion itself should reduce expensive generation, not increase it. Limited animation, reframing, camera movement, captions, overlays and audio timing should be handled in code whenever acceptable quality can be reached from already-approved assets.

The existing rule in `technical/PRODUCTION_PIPELINE.md` remains authoritative: expensive generated video is reserved for moments where motion is the visual event and only after animatic/shot approval.

## Versioning

All `remotion` and `@remotion/*` packages must use one exact version. The initial scaffold pins `4.0.509`. Upgrades should be intentional and should use the official `remotion-upgrade` skill plus a smoke render.

## Next integration layer

After the scaffold is validated with a real episode, add reusable modules in this order:

1. production-safe caption presets;
2. audio buses and loudness policy;
3. scene transition presets;
4. layered-parallax scene component;
5. brand/title/end-card components;
6. manifest validator against approved asset registry;
7. automated QC checks;
8. queued batch rendering.
