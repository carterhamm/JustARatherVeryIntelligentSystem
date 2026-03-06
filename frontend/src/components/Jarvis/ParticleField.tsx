import { useEffect, useState } from 'react';
import Particles, { initParticlesEngine } from '@tsparticles/react';
import { loadSlim } from '@tsparticles/slim';
import type { ISourceOptions } from '@tsparticles/engine';

const particleConfig: ISourceOptions = {
  fullScreen: false,
  fpsLimit: 60,
  particles: {
    number: {
      value: 80,
      density: { enable: true, width: 1920, height: 1080 },
    },
    color: { value: ['#00d4ff', '#0080ff', '#00f0ff'] },
    shape: { type: 'circle' },
    opacity: {
      value: { min: 0.05, max: 0.25 },
      animation: { enable: true, speed: 0.3, sync: false },
    },
    size: {
      value: { min: 0.5, max: 2 },
      animation: { enable: true, speed: 1, sync: false },
    },
    move: {
      enable: true,
      speed: { min: 0.2, max: 0.6 },
      direction: 'none' as const,
      random: true,
      straight: false,
      outModes: { default: 'out' as const },
    },
    links: {
      enable: true,
      distance: 120,
      color: '#00d4ff',
      opacity: 0.06,
      width: 0.5,
    },
  },
  interactivity: {
    events: {
      onHover: { enable: true, mode: 'grab' },
    },
    modes: {
      grab: { distance: 140, links: { opacity: 0.15 } },
    },
  },
  detectRetina: true,
};

export default function ParticleField() {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    initParticlesEngine(async (engine) => {
      await loadSlim(engine);
    }).then(() => setReady(true));
  }, []);

  if (!ready) return null;

  return (
    <div className="absolute inset-0 z-0 pointer-events-none">
      <Particles
        id="jarvis-particles"
        options={particleConfig}
        className="w-full h-full"
      />
    </div>
  );
}
