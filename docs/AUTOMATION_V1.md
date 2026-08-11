# CARTOON FACTORY — AUTOMATION V1

## Goal

Turn evidence-gated CARTOON NICHE RADAR output into a guarded, resumable production pipeline for short AI animation.

V1 intentionally stops before publication. Human approval is required before paid render and before an episode becomes READY.

## Boundary

`cartoon_niche_radar/` remains the research bounded context.

`cartoon_factory/` is the production bounded context.

The only supported bridge is:

`data/reports/production_candidates.json`

Run:

```bash
cnr production-candidates
```

The export is fail-closed. It is blocked when the latest Radar run is synthetic/sample data, when evidence gates failed, when a niche has insufficient data, or when confidence is below the configured threshold.

## V1 lifecycle

```text
IDEA
  -> SCRIPTING
  -> STORYBOARDING
  -> AWAITING_PRODUCTION_APPROVAL
  -> RENDER_QUEUED
  -> RENDERING
  -> ASSEMBLING
  -> QC
  -> AWAITING_FINAL_APPROVAL
  -> READY
```

Exceptional terminal/pause states:

- `FAILED`
- `PAUSED_BUDGET`
- `REJECTED`

Transitions are explicitly validated in `cartoon_factory/domain/states.py`.

## Structured script contract

LLM output must validate as `EpisodeScript` / `SceneScript`. Scenes have contiguous indices and a duration envelope. Invalid structured output is rejected rather than completed by guesswork.

A scene carries at least:

- duration
- location
- characters
- action
- camera
- emotion
- dialogue
- video prompt
- optional negative prompt
- SFX cues
- transition

## Provider isolation

Production code depends on provider interfaces, not vendor-specific request payloads:

- `TextProvider`
- `ImageProvider`
- `VideoProvider`
- `VoiceProvider`
- `SoundProvider`
- `ObjectStore`

Every paid provider exposes an estimate method before generation. Fake providers implement the same contracts and are the only providers used by CI.

## Budget guard

Default policy:

```yaml
episode_soft_cap_usd: 4.50
episode_hard_cap_usd: 6.00
scene_retry_limit: 2
max_parallel_video_jobs: 3
```

Before any paid call:

1. estimate cost;
2. reserve a CostEvent;
3. compare projected spend with hard cap;
4. call the provider only if allowed;
5. reconcile actual cost.

If the projected spend exceeds the hard cap, the provider is not called and a rendering episode is placed in `PAUSED_BUDGET`.

## Asset rule

Every generated artifact becomes an `Asset` with provider/model/job metadata, cost and SHA-256 checksum.

Provider output must be copied into owned storage. Temporary provider URLs are not treated as durable assets.

V1 ships an in-memory fake object store and a local filesystem object store. R2/S3 is the production adapter target.

## Assembly

`cartoon_factory/ffmpeg/compose.py` owns deterministic video assembly.

Target V1 master:

- 720×1280
- 30 fps
- H.264
- yuv420p
- faststart

The fake CI path creates an assembly manifest instead of pretending fake bytes are valid media.

## QC V1

Current core QC verifies scene video completeness and attributes missing assets to a concrete scene.

The real-media adapter phase must extend this with:

- ffprobe validation;
- duration tolerance;
- aspect ratio;
- blank frames;
- audio presence;
- clipping/loudness;
- corruption checks.

Semantic/visual character-consistency QC is V2.

## Commands

```bash
# Existing research pipeline
cnr run-all --use-sample --stage A

# This MUST fail closed for sample data
cnr production-candidates

# Production core, no external APIs and no real spend
caf smoke-fake

# Local prerequisites, no paid calls
caf doctor

caf status
```

## CI

`.github/workflows/factory-ci.yml` runs:

- Factory unit tests;
- scoped Ruff;
- scoped mypy;
- `caf smoke-fake`.

No external generation API is called in CI.

## Current V1 implementation status

Implemented:

- Radar/Factory boundary;
- synthetic/evidence production gate;
- production state machine;
- structured script schema;
- provider protocols;
- deterministic fake providers;
- asset checksums/storage contract;
- budget guard and CostEvents;
- preproduction -> human gate;
- render -> assembly manifest -> QC -> final human gate;
- FFmpeg deterministic assembly helper;
- `caf` CLI;
- Factory-scoped CI.

Not yet enabled:

- persistent SQLAlchemy repository for Factory entities;
- job queue/worker recovery;
- FastAPI/n8n webhooks;
- Runway/OpenAI real provider adapters;
- R2 adapter;
- real FFmpeg media integration in the orchestrator;
- Streamlit Factory dashboard;
- YouTube publishing/analytics loop.

These are subsequent V1 slices, not silently simulated capabilities.

## First paid smoke after provider adapter

The first real paid smoke should be exactly one portrait scene, with an explicit cost confirmation flag and a hard cap below one US dollar. The command must never run merely because an API key exists.

No automatic publication or deployment is part of V1.
