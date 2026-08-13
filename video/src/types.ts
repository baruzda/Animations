import {z} from 'zod';

const MediaSourceSchema = z.string().min(1);

export const CameraSchema = z.enum([
  'static',
  'push-in',
  'push-out',
  'pan-left',
  'pan-right',
]);

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
]);

export const SceneSchema = z.object({
  id: z.string().min(1),
  durationSec: z.number().positive(),
  visual: VisualSchema,
  camera: CameraSchema.default('static'),
  text: z.string().optional(),
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
  width: z.number().int().positive().default(1080),
  height: z.number().int().positive().default(1920),
  fps: z.number().int().positive().default(30),
  background: z.string().min(1).default('#101114'),
  scenes: z.array(SceneSchema).min(1),
  captions: z.array(CaptionSchema).default([]),
  music: MusicSchema,
});

export type EpisodeManifest = z.infer<typeof EpisodeManifestSchema>;
export type Scene = z.infer<typeof SceneSchema>;

export const getEpisodeDurationSec = (manifest: EpisodeManifest): number =>
  manifest.scenes.reduce((total, scene) => total + scene.durationSec, 0);
