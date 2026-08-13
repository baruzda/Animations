# Agent routing for Animations

This repository has two deliberately separated concerns:

- `cartoon_niche_radar/` is the empirical research pipeline.
- `technical/` and `series/` are the production memory for animated series.

Do not let research outputs silently rewrite a series canon. Treat series canon and approved references as source-of-truth inputs for production work.

## Remotion production tasks

When the task is about assembling, editing, captioning, previewing, or rendering video:

1. Read `.agents/skills/video-production/SKILL.md`.
2. Read `technical/PRODUCTION_PIPELINE.md` and `technical/REMOTION_INTEGRATION.md`.
3. Read the active series canon, approved shot list, and approved asset references before touching episode output.
4. Use official Remotion Agent Skills as upstream technical guidance. Install or refresh them with:

   `cd video && npm run skills:install`

   Do not vendor or rewrite the upstream Remotion skills into this repository; keep the local skill focused on our production rules.
5. Keep Remotion packages pinned to the same exact version in `video/package.json`.
6. Do not start expensive generative-video work from a Remotion task. Remotion is the deterministic assembly/render layer; generative assets enter only after the existing approval gates.
7. Run `npm run check` and a smoke render when the environment supports it. If assets are missing, use diagnostic placeholders rather than inventing approved references.

## Preservation rules

- Preserve user-authored changes.
- Never overwrite approved canon, character, prop, or location references without an explicit request.
- Prefer manifest-driven episode assembly over hard-coded per-episode timelines.
- Production automation must remain reproducible: the same manifest + assets + code should produce the same timeline.
