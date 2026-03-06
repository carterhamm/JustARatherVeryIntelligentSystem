import { Suspense } from 'react';
import { Canvas } from '@react-three/fiber';
import { EffectComposer, Bloom, Vignette, ChromaticAberration } from '@react-three/postprocessing';
import { BlendFunction } from 'postprocessing';
import { Vector2 } from 'three';
import { useUIStore } from '@/stores/uiStore';
import GlowingCore from './GlowingCore';
import WireframeSpheres from './WireframeSpheres';
import ParticleSystem from './ParticleSystem';
import ConnectionNetwork from './ConnectionNetwork';
import OrbitalRings from './OrbitalRings';
import HolographicGrid from './HolographicGrid';
import HUDOverlay3D from './HUDOverlay3D';

function JarvisScene() {
  const isListening = useUIStore((s) => s.isListening);
  const isSpeaking = useUIStore((s) => s.isSpeaking);
  const isThinking = useUIStore((s) => s.isThinking);
  const activity = useUIStore((s) => s.jarvisActivity);

  return (
    <>
      {/* Ambient light */}
      <ambientLight intensity={0.08} color="#0040ff" />

      {/* Core visualization elements */}
      <GlowingCore
        isListening={isListening}
        isSpeaking={isSpeaking}
        isThinking={isThinking}
        activity={activity}
      />
      <WireframeSpheres activity={activity} />
      <ParticleSystem activity={activity} count={10000} />
      <ConnectionNetwork activity={activity} />
      <OrbitalRings activity={activity} />
      <HolographicGrid activity={activity} />
      <HUDOverlay3D activity={activity} />

      {/* Post-processing */}
      <EffectComposer>
        <Bloom
          luminanceThreshold={0.1}
          luminanceSmoothing={0.9}
          intensity={1.8}
          mipmapBlur
        />
        <ChromaticAberration
          blendFunction={BlendFunction.NORMAL}
          offset={new Vector2(0.0005, 0.0005)}
          radialModulation={true}
          modulationOffset={0.5}
        />
        <Vignette
          darkness={0.5}
          offset={0.3}
          blendFunction={BlendFunction.NORMAL}
        />
      </EffectComposer>
    </>
  );
}

export default function JarvisCore() {
  return (
    <div className="w-full h-full absolute inset-0">
      <Canvas
        camera={{
          position: [0, 0, 7],
          fov: 60,
          near: 0.1,
          far: 100,
        }}
        gl={{
          antialias: true,
          alpha: true,
          powerPreference: 'high-performance',
        }}
        style={{ background: 'transparent' }}
      >
        <fog attach="fog" args={['#050510', 8, 25]} />
        <Suspense fallback={null}>
          <JarvisScene />
        </Suspense>
      </Canvas>
    </div>
  );
}
