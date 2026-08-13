import React from 'react';
import {Composition} from 'remotion';
import exampleManifestJson from '../manifests/example.json';
import ep01WishDuckJson from '../manifests/ep01-wish-duck.json';
import {Episode} from './Episode';
import {EpisodeManifestSchema, getEpisodeDurationSec} from './types';

const exampleManifest = EpisodeManifestSchema.parse(exampleManifestJson);
const ep01WishDuck = EpisodeManifestSchema.parse(ep01WishDuckJson);

const durationFrames = (manifest: typeof exampleManifest) =>
  Math.max(1, Math.round(getEpisodeDurationSec(manifest) * manifest.fps));

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="Episode"
        component={Episode}
        width={exampleManifest.width}
        height={exampleManifest.height}
        fps={exampleManifest.fps}
        durationInFrames={durationFrames(exampleManifest)}
        defaultProps={exampleManifest}
        schema={EpisodeManifestSchema}
        calculateMetadata={({props}) => {
          const manifest = EpisodeManifestSchema.parse(props);
          return {
            width: manifest.width,
            height: manifest.height,
            fps: manifest.fps,
            durationInFrames: durationFrames(manifest),
          };
        }}
      />
      <Composition
        id="EP01WishDuck"
        component={Episode}
        width={ep01WishDuck.width}
        height={ep01WishDuck.height}
        fps={ep01WishDuck.fps}
        durationInFrames={durationFrames(ep01WishDuck)}
        defaultProps={ep01WishDuck}
        schema={EpisodeManifestSchema}
        calculateMetadata={({props}) => {
          const manifest = EpisodeManifestSchema.parse(props);
          return {
            width: manifest.width,
            height: manifest.height,
            fps: manifest.fps,
            durationInFrames: durationFrames(manifest),
          };
        }}
      />
    </>
  );
};
