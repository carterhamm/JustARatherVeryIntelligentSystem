import StatusBar from '@/components/Jarvis/StatusBar';
import FloatingChat from '@/components/Jarvis/FloatingChat';
import CommandDock from '@/components/Jarvis/CommandDock';
import ModelPickerFloat from '@/components/Jarvis/ModelPickerFloat';
import SessionsPanel from '@/components/Jarvis/SessionsPanel';
import DiagnosticsPanel from '@/components/Jarvis/DiagnosticsPanel';
import SettingsPanel from '@/components/SettingsPanel';
import DataImportPanel from '@/components/DataImportPanel';
import KnowledgePanel from '@/components/KnowledgePanel';

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


      {/* Floating UI Layer */}
      <StatusBar />
      <FloatingChat />
      <CommandDock />

      {/* Panel overlays */}
      <ModelPickerFloat />
      <SessionsPanel />
      <DiagnosticsPanel />
      <SettingsPanel />
      <DataImportPanel />
      <KnowledgePanel />
    </div>
  );
}
