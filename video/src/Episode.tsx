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
import type {EpisodeManifest, Layer, Scene} from './types';

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

type AssetMap = EpisodeManifest['assets'];

const getAsset = (assets: AssetMap, slot: string) => assets[slot];

const MissingAssetSlate: React.FC<{
  scene: Scene;
  missingSlots: string[];
  fallbackColor: string;
}> = ({scene, missingSlots, fallbackColor}) => (
  <AbsoluteFill
    style={{
      backgroundColor: fallbackColor,
      color: 'white',
      fontFamily: 'Arial, sans-serif',
      padding: 64,
      justifyContent: 'space-between',
    }}
  >
    <div>
      <div style={{fontSize: 34, opacity: 0.65, letterSpacing: 2}}>{scene.id}</div>
      <div style={{fontSize: 26, marginTop: 12, opacity: 0.75}}>
        {scene.productionClass.toUpperCase()}
      </div>
    </div>

    <div>
      <div style={{fontSize: 54, fontWeight: 800, lineHeight: 1.05}}>
        {scene.visual.kind === 'asset-slot' ? scene.visual.label : 'Production asset'}
      </div>
      {scene.beat ? (
        <div style={{fontSize: 30, lineHeight: 1.25, marginTop: 24, opacity: 0.84}}>
          {scene.beat}
        </div>
      ) : null}
    </div>

    <div style={{fontSize: 24, lineHeight: 1.35, opacity: 0.72}}>
      {missingSlots.length > 0 ? (
        <>
          <div style={{fontWeight: 700}}>MISSING ASSET SLOTS</div>
          {missingSlots.slice(0, 6).map((slot) => (
            <div key={slot}>{slot}</div>
          ))}
          {missingSlots.length > 6 ? <div>+{missingSlots.length - 6} more</div> : null}
        </>
      ) : (
        <div>Asset slot is ready for review.</div>
      )}
      {scene.sourceSpec ? <div style={{marginTop: 18}}>Spec: {scene.sourceSpec}</div> : null}
    </div>
  </AbsoluteFill>
);

const AssetLayer: React.FC<{
  layer: Layer;
  assets: AssetMap;
  progress: number;
  camera: Scene['camera'];
}> = ({layer, assets, progress, camera}) => {
  const asset = getAsset(assets, layer.slot);
  if (!asset?.src || asset.type === 'audio' || asset.status === 'missing') {
    return null;
  }

  const x = layer.xPct + layer.parallaxX * (progress - 0.5);
  const y = layer.yPct + layer.parallaxY * (progress - 0.5);
  const transform = `${cameraTransform(camera, progress)} translate(${x}%, ${y}%) scale(${layer.scale})`;
  const style: React.CSSProperties = {
    width: '100%',
    height: '100%',
    objectFit: layer.fit,
    opacity: layer.opacity,
    transform,
    transformOrigin: 'center center',
  };

  return (
    <AbsoluteFill style={{zIndex: layer.zIndex, pointerEvents: 'none'}}>
      {asset.type === 'video' ? (
        <OffthreadVideo src={resolveSource(asset.src)} style={style} />
      ) : (
        <Img src={resolveSource(asset.src)} style={style} />
      )}
      {asset.status === 'draft' ? (
        <div
          style={{
            position: 'absolute',
            top: 24,
            right: 24,
            padding: '10px 14px',
            backgroundColor: 'rgba(0,0,0,0.65)',
            color: 'white',
            fontFamily: 'Arial, sans-serif',
            fontSize: 20,
            fontWeight: 800,
          }}
        >
          DRAFT ASSET
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

const SceneLayer: React.FC<{scene: Scene; assets: AssetMap}> = ({scene, assets}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const sceneFrames = Math.max(1, Math.round(scene.durationSec * fps));
  const progress = interpolate(frame, [0, Math.max(1, sceneFrames - 1)], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const transform = cameraTransform(scene.camera, progress);

  const referencedSlots = [
    scene.visual.kind === 'asset-slot' ? scene.visual.slot : null,
    ...scene.layers.map((layer) => layer.slot),
    ...scene.audioEvents.map((event) => event.slot),
  ].filter((slot): slot is string => Boolean(slot));
  const missingSlots = referencedSlots.filter((slot) => {
    const asset = getAsset(assets, slot);
    return !asset?.src || asset.status === 'missing';
  });

  let baseVisual: React.ReactNode;
  if (scene.visual.kind === 'color') {
    baseVisual = <AbsoluteFill style={{backgroundColor: scene.visual.color}} />;
  } else if (scene.visual.kind === 'image') {
    baseVisual = (
      <Img
        src={resolveSource(scene.visual.src)}
        style={{width: '100%', height: '100%', objectFit: 'cover', transform}}
      />
    );
  } else if (scene.visual.kind === 'video') {
    baseVisual = (
      <OffthreadVideo
        src={resolveSource(scene.visual.src)}
        style={{width: '100%', height: '100%', objectFit: 'cover', transform}}
      />
    );
  } else {
    const asset = getAsset(assets, scene.visual.slot);
    if (!asset?.src || asset.status === 'missing' || asset.type === 'audio') {
      baseVisual = (
        <MissingAssetSlate
          scene={scene}
          missingSlots={missingSlots}
          fallbackColor={scene.visual.fallbackColor}
        />
      );
    } else if (asset.type === 'video') {
      baseVisual = (
        <OffthreadVideo
          src={resolveSource(asset.src)}
          style={{width: '100%', height: '100%', objectFit: 'cover', transform}}
        />
      );
    } else {
      baseVisual = (
        <Img
          src={resolveSource(asset.src)}
          style={{width: '100%', height: '100%', objectFit: 'cover', transform}}
        />
      );
    }
  }

  return (
    <AbsoluteFill style={{overflow: 'hidden', backgroundColor: '#111'}}>
      {baseVisual}

      {scene.layers.map((layer) => (
        <AssetLayer
          key={layer.id}
          layer={layer}
          assets={assets}
          progress={progress}
          camera={scene.camera}
        />
      ))}

      {scene.text ? (
        <AbsoluteFill
          style={{
            zIndex: 100,
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

      {scene.audioEvents.map((event) => {
        const asset = getAsset(assets, event.slot);
        if (!asset?.src || asset.type !== 'audio' || asset.status === 'missing') {
          return null;
        }
        const from = Math.round(event.atSec * fps);
        const durationInFrames = event.durationSec
          ? Math.max(1, Math.round(event.durationSec * fps))
          : undefined;
        return (
          <Sequence key={event.id} from={from} durationInFrames={durationInFrames}>
            <Audio src={resolveSource(asset.src)} volume={event.volume} />
          </Sequence>
        );
      })}
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
                zIndex: 200,
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
            <SceneLayer scene={scene} assets={manifest.assets} />
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
