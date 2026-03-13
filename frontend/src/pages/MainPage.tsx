import StatusBar from '@/components/Jarvis/StatusBar';
import FloatingChat from '@/components/Jarvis/FloatingChat';
import CommandDock from '@/components/Jarvis/CommandDock';
import WidgetPanel from '@/components/Jarvis/WidgetPanel';
import ModelPickerFloat from '@/components/Jarvis/ModelPickerFloat';
import SessionsPanel from '@/components/Jarvis/SessionsPanel';
import DiagnosticsPanel from '@/components/Jarvis/DiagnosticsPanel';
import SettingsPanel from '@/components/SettingsPanel';
import DataImportPanel from '@/components/DataImportPanel';
import KnowledgePanel from '@/components/KnowledgePanel';
import ContactsPanel from '@/components/ContactsPanel';
import HabitsPanel from '@/components/HabitsPanel';
import FocusPanel from '@/components/FocusPanel';

function HudCorner({ position }: { position: 'tl' | 'tr' | 'bl' | 'br' }) {
  const isTop = position.startsWith('t');
  const isLeft = position.endsWith('l');
  return (
    <div
      className="absolute pointer-events-none z-[5]"
      style={{
        [isTop ? 'top' : 'bottom']: '8px',
        [isLeft ? 'left' : 'right']: '8px',
      }}
    >
      <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
        <path
          d={
            isTop && isLeft
              ? 'M0 20 L0 0 L20 0'
              : isTop && !isLeft
                ? 'M28 0 L48 0 L48 20'
                : !isTop && isLeft
                  ? 'M0 28 L0 48 L20 48'
                  : 'M28 48 L48 48 L48 28'
          }
          stroke="rgba(0, 212, 255, 0.12)"
          strokeWidth="1"
        />
        {/* Inner tick mark */}
        <path
          d={
            isTop && isLeft
              ? 'M0 8 L8 0'
              : isTop && !isLeft
                ? 'M40 0 L48 8'
                : !isTop && isLeft
                  ? 'M0 40 L8 48'
                  : 'M40 48 L48 40'
          }
          stroke="rgba(0, 212, 255, 0.06)"
          strokeWidth="0.5"
        />
      </svg>
    </div>
  );
}

function HudEdgeLines() {
  return (
    <div className="absolute inset-0 pointer-events-none z-[5]">
      {/* Top edge line */}
      <div className="absolute top-0 left-[60px] right-[60px] h-px glow-line-h opacity-30" />
      {/* Bottom edge line */}
      <div className="absolute bottom-0 left-[60px] right-[60px] h-px glow-line-h opacity-20" />
      {/* Left edge line */}
      <div className="absolute left-0 top-[60px] bottom-[60px] w-px glow-line-v opacity-20" />
      {/* Right edge line */}
      <div className="absolute right-0 top-[60px] bottom-[60px] w-px glow-line-v opacity-20" />

      {/* Top-left telemetry readout */}
      <div className="absolute top-[58px] left-[60px] hidden lg:block">
        <span className="text-[7px] font-mono tracking-[0.25em] text-jarvis-blue/10">
          SYS.CORE.01
        </span>
      </div>

      {/* Bottom-right telemetry readout */}
      <div className="absolute bottom-[10px] right-[60px] hidden lg:block">
        <span className="text-[7px] font-mono tracking-[0.25em] text-jarvis-blue/10">
          MALIBU.POINT//UPLINK
        </span>
      </div>
    </div>
  );
}

export default function MainPage() {
  return (
    <div className="h-screen w-screen bg-black overflow-hidden relative">
      {/* Subtle background — grid + radial glow */}
      <div className="absolute inset-0 pointer-events-none">
        <div
          className="absolute inset-0 opacity-[0.04]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(0,212,255,0.4) 1px, transparent 1px), linear-gradient(90deg, rgba(0,212,255,0.4) 1px, transparent 1px)',
            backgroundSize: '80px 80px',
          }}
        />
        <div
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[900px] h-[900px] rounded-full"
          style={{
            background:
              'radial-gradient(circle, rgba(0,212,255,0.06) 0%, rgba(0,128,255,0.02) 40%, transparent 70%)',
          }}
        />
      </div>

      {/* HUD overlays */}
      <div className="vignette-overlay" />
      <div className="noise-overlay" />

      {/* HUD frame elements */}
      <HudCorner position="tl" />
      <HudCorner position="tr" />
      <HudCorner position="bl" />
      <HudCorner position="br" />
      <HudEdgeLines />

      {/* Floating UI Layer */}
      <StatusBar />
      <FloatingChat />
      <CommandDock />
      <WidgetPanel />

      {/* Panel overlays */}
      <ModelPickerFloat />
      <SessionsPanel />
      <DiagnosticsPanel />
      <SettingsPanel />
      <DataImportPanel />
      <KnowledgePanel />
      <ContactsPanel />
      <HabitsPanel />
      <FocusPanel />
    </div>
  );
}
