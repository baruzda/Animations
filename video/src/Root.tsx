import React from 'react';
import {Composition} from 'remotion';
import exampleManifestJson from '../manifests/example.json';
import {Episode} from './Episode';
import {EpisodeManifestSchema, getEpisodeDurationSec} from './types';

const defaultManifest = EpisodeManifestSchema.parse(exampleManifestJson);

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Episode"
      component={Episode}
      width={defaultManifest.width}
      height={defaultManifest.height}
      fps={defaultManifest.fps}
      durationInFrames={Math.max(
        1,
        Math.round(getEpisodeDurationSec(defaultManifest) * defaultManifest.fps),
      )}
      defaultProps={defaultManifest}
      schema={EpisodeManifestSchema}
      calculateMetadata={({props}) => {
        const manifest = EpisodeManifestSchema.parse(props);
        return {
          width: manifest.width,
          height: manifest.height,
          fps: manifest.fps,
          durationInFrames: Math.max(
            1,
            Math.round(getEpisodeDurationSec(manifest) * manifest.fps),
          ),
        };
      }}
    />
  );
};
