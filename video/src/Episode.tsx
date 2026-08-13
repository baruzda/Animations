import React from 'react';
import {Audio} from '@remotion/media';
import {
  AbsoluteFill,
  Img,
  OffthreadVideo,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import type {EpisodeManifest, Scene} from './types';

const isAbsoluteSource = (src: string) => /^(https?:|data:|blob:)/.test(src);
const resolveSource = (src: string) =>
  isAbsoluteSource(src) ? src : staticFile(src.replace(/^\/+/, ''));

const cameraTransform = (camera: Scene['camera'], progress: number): string => {
  switch (camera) {
    case 'push-in':
      return `scale(${1 + 0.08 * progress})`;
    case 'push-out':
      return `scale(${1.08 - 0.08 * progress})`;
    case 'pan-left':
      return `scale(1.06) translateX(${3 - 6 * progress}%)`;
    case 'pan-right':
      return `scale(1.06) translateX(${-3 + 6 * progress}%)`;
    default:
      return 'scale(1)';
  }
};

const SceneLayer: React.FC<{scene: Scene}> = ({scene}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const sceneFrames = Math.max(1, Math.round(scene.durationSec * fps));
  const progress = interpolate(frame, [0, Math.max(1, sceneFrames - 1)], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const transform = cameraTransform(scene.camera, progress);

  return (
    <AbsoluteFill style={{overflow: 'hidden', backgroundColor: '#111'}}>
      {scene.visual.kind === 'color' ? (
        <AbsoluteFill style={{backgroundColor: scene.visual.color}} />
      ) : scene.visual.kind === 'image' ? (
        <Img
          src={resolveSource(scene.visual.src)}
          style={{width: '100%', height: '100%', objectFit: 'cover', transform}}
        />
      ) : (
        <OffthreadVideo
          src={resolveSource(scene.visual.src)}
          style={{width: '100%', height: '100%', objectFit: 'cover', transform}}
        />
      )}

      {scene.text ? (
        <AbsoluteFill
          style={{
            justifyContent: 'center',
            alignItems: 'center',
            padding: 96,
            color: 'white',
            fontFamily: 'Arial, sans-serif',
            fontSize: 72,
            fontWeight: 700,
            textAlign: 'center',
            textShadow: '0 4px 18px rgba(0,0,0,0.65)',
          }}
        >
          {scene.text}
        </AbsoluteFill>
      ) : null}

      {scene.voice ? <Audio src={resolveSource(scene.voice)} /> : null}
      {scene.sfx.map((src, index) => (
        <Audio key={`${scene.id}-sfx-${index}`} src={resolveSource(src)} />
      ))}
    </AbsoluteFill>
  );
};

const CaptionLayer: React.FC<{manifest: EpisodeManifest}> = ({manifest}) => {
  const {fps} = useVideoConfig();

  return (
    <>
      {manifest.captions.map((caption) => {
        const from = Math.round(caption.startSec * fps);
        const durationInFrames = Math.max(1, Math.round((caption.endSec - caption.startSec) * fps));

        return (
          <Sequence key={caption.id} from={from} durationInFrames={durationInFrames}>
            <AbsoluteFill
              style={{
                justifyContent: 'flex-end',
                alignItems: 'center',
                padding: '0 72px 210px',
                pointerEvents: 'none',
              }}
            >
              <div
                style={{
                  maxWidth: 900,
                  color: 'white',
                  fontFamily: 'Arial, sans-serif',
                  fontSize: 58,
                  lineHeight: 1.08,
                  fontWeight: 800,
                  textAlign: 'center',
                  textShadow: '0 4px 16px rgba(0,0,0,0.85)',
                }}
              >
                {caption.text}
              </div>
            </AbsoluteFill>
          </Sequence>
        );
      })}
    </>
  );
};

export const Episode: React.FC<EpisodeManifest> = (manifest) => {
  const {fps} = useVideoConfig();
  let cursor = 0;

  return (
    <AbsoluteFill style={{backgroundColor: manifest.background}}>
      {manifest.scenes.map((scene) => {
        const from = cursor;
        const durationInFrames = Math.max(1, Math.round(scene.durationSec * fps));
        cursor += durationInFrames;

        return (
          <Sequence key={scene.id} from={from} durationInFrames={durationInFrames}>
            <SceneLayer scene={scene} />
          </Sequence>
        );
      })}

      {manifest.music ? (
        <Audio src={resolveSource(manifest.music.src)} volume={manifest.music.volume} loop />
      ) : null}

      <CaptionLayer manifest={manifest} />
    </AbsoluteFill>
  );
};
