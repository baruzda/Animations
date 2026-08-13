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

Expected output:

`video/out/example.mp4`

## Real episode

Create a manifest based on an approved shot list and assets, then:

```bash
npm run render -- --props=manifests/<episode>.json
```

Local media paths in manifests resolve from `video/public/`. Absolute `http(s)`, `data:` and `blob:` sources are passed through.

## Manifest principles

- scene order is manifest order;
- scene timing is stored in seconds;
- frame counts are derived from manifest FPS;
- image scenes can use deterministic limited camera motion;
- video scenes use approved motion clips;
- voice and SFX are attached to their scenes;
- captions are global timed data;
- missing approvals should remain diagnostic placeholders, not invented assets.

See `technical/REMOTION_INTEGRATION.md` and `.agents/skills/video-production/SKILL.md` for the repository policy.
