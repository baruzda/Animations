import {z} from 'zod';

const MediaSourceSchema = z.string().min(1);

export const CameraSchema = z.enum([
  'static',
  'push-in',
  'push-out',
  'pan-left',
  'pan-right',
]);

export const ProductionClassSchema = z.enum([
  'limited',
  'limited-fx',
  'full-ai-video',
  'reuse',
  'sound-led',
]);

export const AssetSchema = z.object({
  type: z.enum(['image', 'video', 'audio']),
  status: z.enum(['missing', 'draft', 'approved']).default('missing'),
  src: MediaSourceSchema.optional(),
  sourceOfTruth: z.string().optional(),
  notes: z.string().optional(),
});

const AssetSlotVisualSchema = z.object({
  kind: z.literal('asset-slot'),
  slot: z.string().min(1),
  label: z.string().min(1),
  mediaType: z.enum(['image', 'video']).default('image'),
  fallbackColor: z.string().min(1).default('#20242b'),
});

const VisualSchema = z.discriminatedUnion('kind', [
  z.object({
    kind: z.literal('color'),
    color: z.string().min(1),
  }),
  z.object({
    kind: z.literal('image'),
    src: MediaSourceSchema,
  }),
  z.object({
    kind: z.literal('video'),
    src: MediaSourceSchema,
  }),
  AssetSlotVisualSchema,
]);

export const LayerSchema = z.object({
  id: z.string().min(1),
  slot: z.string().min(1),
  label: z.string().optional(),
  fit: z.enum(['contain', 'cover']).default('contain'),
  opacity: z.number().min(0).max(1).default(1),
  scale: z.number().positive().default(1),
  xPct: z.number().default(0),
  yPct: z.number().default(0),
  parallaxX: z.number().default(0),
  parallaxY: z.number().default(0),
  zIndex: z.number().int().default(10),
});

export const AudioEventSchema = z.object({
  id: z.string().min(1),
  kind: z.enum(['dialogue', 'sfx']),
  slot: z.string().min(1),
  atSec: z.number().nonnegative(),
  durationSec: z.number().positive().optional(),
  volume: z.number().min(0).max(2).default(1),
});

export const SceneSchema = z.object({
  id: z.string().min(1),
  durationSec: z.number().positive(),
  visual: VisualSchema,
  camera: CameraSchema.default('static'),
  productionClass: ProductionClassSchema.default('limited'),
  sourceSpec: z.string().optional(),
  beat: z.string().optional(),
  text: z.string().optional(),
  layers: z.array(LayerSchema).default([]),
  audioEvents: z.array(AudioEventSchema).default([]),
  voice: MediaSourceSchema.optional(),
  sfx: z.array(MediaSourceSchema).default([]),
});

export const CaptionSchema = z.object({
  id: z.string().min(1),
  startSec: z.number().nonnegative(),
  endSec: z.number().positive(),
  text: z.string().min(1),
}).refine((caption) => caption.endSec > caption.startSec, {
  message: 'caption.endSec must be greater than caption.startSec',
});

export const MusicSchema = z.object({
  src: MediaSourceSchema,
  volume: z.number().min(0).max(1).default(0.18),
}).optional();

export const EpisodeManifestSchema = z.object({
  id: z.string().min(1),
  title: z.string().optional(),
  width: z.number().int().positive().default(1080),
  height: z.number().int().positive().default(1920),
  fps: z.number().int().positive().default(30),
  background: z.string().min(1).default('#101114'),
  assets: z.record(z.string(), AssetSchema).default({}),
  scenes: z.array(SceneSchema).min(1),
  captions: z.array(CaptionSchema).default([]),
  music: MusicSchema,
});

export type EpisodeManifest = z.infer<typeof EpisodeManifestSchema>;
export type Scene = z.infer<typeof SceneSchema>;
export type Layer = z.infer<typeof LayerSchema>;
export type Asset = z.infer<typeof AssetSchema>;

export const getEpisodeDurationSec = (manifest: EpisodeManifest): number =>
  manifest.scenes.reduce((total, scene) => total + scene.durationSec, 0);
