import JarvisCore from '@/components/JarvisCore/JarvisCore';
import StatusBar from '@/components/Jarvis/StatusBar';
import FloatingChat from '@/components/Jarvis/FloatingChat';
import CommandDock from '@/components/Jarvis/CommandDock';
import SessionsPanel from '@/components/Jarvis/SessionsPanel';
import DiagnosticsPanel from '@/components/Jarvis/DiagnosticsPanel';
import SettingsPanel from '@/components/SettingsPanel';
import DataImportPanel from '@/components/DataImportPanel';
import KnowledgePanel from '@/components/KnowledgePanel';

export default function MainPage() {
  return (
    <div className="h-screen w-screen bg-black overflow-hidden relative">
      {/* 3D Background — fills entire viewport */}
      <div className="absolute inset-0 z-0 pointer-events-none">
        <JarvisCore />
      </div>

      {/* Scanline overlay */}
      <div className="scanline-overlay" />

      {/* Floating UI Layer */}
      <StatusBar />
      <FloatingChat />
      <CommandDock />

      {/* Panel overlays */}
      <SessionsPanel />
      <DiagnosticsPanel />
      <SettingsPanel />
      <DataImportPanel />
      <KnowledgePanel />
    </div>
  );
}
