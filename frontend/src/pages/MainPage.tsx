import { useEffect, useRef, useState, lazy, Suspense } from 'react';
import gsap from 'gsap';
import StatusBar from '@/components/Jarvis/StatusBar';
import FloatingChat from '@/components/Jarvis/FloatingChat';
import CommandDock from '@/components/Jarvis/CommandDock';
import ModelPickerFloat from '@/components/Jarvis/ModelPickerFloat';
import SessionsPanel from '@/components/Jarvis/SessionsPanel';
import DiagnosticsPanel from '@/components/Jarvis/DiagnosticsPanel';
import SettingsPanel from '@/components/SettingsPanel';
import DataImportPanel from '@/components/DataImportPanel';
import KnowledgePanel from '@/components/KnowledgePanel';
import HUDAmbient from '@/components/Jarvis/HUDAmbient';
import MiniDiagnostics from '@/components/Jarvis/MiniDiagnostics';

// Lazy-load heavy 3D + particle components
const JarvisCore = lazy(() => import('@/components/JarvisCore/JarvisCore'));
const ParticleField = lazy(() => import('@/components/Jarvis/ParticleField'));

export default function MainPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  const bootOverlayRef = useRef<HTMLDivElement>(null);
  const [booted, setBooted] = useState(false);

  useEffect(() => {
    if (booted) return;

    const tl = gsap.timeline({
      onComplete: () => setBooted(true),
    });

    // Boot sequence: overlay fades, then elements stagger in
    tl.fromTo(
      bootOverlayRef.current,
      { opacity: 1 },
      { opacity: 0, duration: 1.2, ease: 'power2.out' },
    );

    tl.to(bootOverlayRef.current, {
      display: 'none',
      duration: 0,
    });
  }, [booted]);

  return (
    <div ref={containerRef} className="h-screen w-screen bg-black overflow-hidden relative">
      {/* Layer 0: 3D Core — full-screen background */}
      <Suspense fallback={null}>
        <div className="absolute inset-0 z-0">
          <JarvisCore />
        </div>
      </Suspense>

      {/* Layer 1: Ambient particles */}
      <Suspense fallback={null}>
        <ParticleField />
      </Suspense>

      {/* Layer 2: Background grid + radial glow */}
      <div className="absolute inset-0 pointer-events-none z-[1]">
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(0,212,255,0.4) 1px, transparent 1px), linear-gradient(90deg, rgba(0,212,255,0.4) 1px, transparent 1px)',
            backgroundSize: '80px 80px',
          }}
        />
        <div
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[1000px] h-[1000px] rounded-full"
          style={{
            background:
              'radial-gradient(circle, rgba(0,212,255,0.04) 0%, rgba(0,128,255,0.015) 40%, transparent 70%)',
          }}
        />
      </div>

      {/* Layer 3: Visual overlays */}
      <div className="scanline-overlay z-[2]" />
      <div className="vignette-overlay" />
      <div className="noise-overlay" />

      {/* Layer 4: HUD ambient elements */}
      <HUDAmbient />

      {/* Layer 5: Floating UI */}
      <StatusBar />
      <FloatingChat />
      <CommandDock />
      <MiniDiagnostics />

      {/* Panel overlays */}
      <ModelPickerFloat />
      <SessionsPanel />
      <DiagnosticsPanel />
      <SettingsPanel />
      <DataImportPanel />
      <KnowledgePanel />

      {/* Boot overlay */}
      <div
        ref={bootOverlayRef}
        className="fixed inset-0 z-[100] bg-black flex items-center justify-center pointer-events-none"
      >
        <div className="flex flex-col items-center gap-4">
          {/* Boot logo */}
          <div
            className="w-12 h-12 flex items-center justify-center"
            style={{
              clipPath: 'polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%)',
              background: 'linear-gradient(135deg, rgba(0, 212, 255, 0.3), rgba(0, 128, 255, 0.2))',
            }}
          >
            <span className="text-lg font-display font-bold text-jarvis-blue glow-text">J</span>
          </div>
          <div className="flex flex-col items-center gap-1">
            <span className="text-xs font-display tracking-[0.3em] text-jarvis-blue/80 glow-text">
              J.A.R.V.I.S.
            </span>
            <span className="text-[8px] font-mono text-jarvis-blue/30 tracking-wider">
              INITIALIZING SUBSYSTEMS...
            </span>
          </div>
          {/* Boot progress bar */}
          <div className="w-48 h-[2px] bg-jarvis-blue/10 rounded-full overflow-hidden">
            <div
              className="h-full bg-jarvis-blue/60 rounded-full"
              style={{
                animation: 'bootProgress 1.2s ease-out forwards',
              }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
