import { ErrorBoundary } from '@/App';
import JarvisCore from '@/components/JarvisCore/JarvisCore';
import HUDStatusBar from '@/components/HUD/HUDStatusBar';
import HUDNavPanel from '@/components/HUD/HUDNavPanel';
import HUDDiagnosticsPanel from '@/components/HUD/HUDDiagnosticsPanel';
import ChatArea from '@/components/HUD/ChatArea';
import SettingsPanel from '@/components/SettingsPanel';
import DataImportPanel from '@/components/DataImportPanel';
import KnowledgePanel from '@/components/KnowledgePanel';

export default function MainPage() {
  return (
    <div className="relative h-screen w-screen overflow-hidden bg-jarvis-darker hud-scanlines">
      {/* 3D Background — isolated so WebGL errors don't break the UI */}
      <div className="fixed inset-0 z-0">
        <ErrorBoundary fallback={<div className="w-full h-full bg-jarvis-darker" />}>
          <JarvisCore />
        </ErrorBoundary>
      </div>

      {/* HUD Overlay */}
      <div className="relative z-10 flex flex-col h-full">
        {/* Top status bar */}
        <HUDStatusBar />

        {/* Main content area */}
        <div className="flex flex-1 min-h-0">
          {/* Left nav */}
          <HUDNavPanel />

          {/* Center chat (transparent over 3D) */}
          <ChatArea />

          {/* Right diagnostics (hidden on small screens) */}
          <div className="hidden lg:flex">
            <HUDDiagnosticsPanel />
          </div>
        </div>
      </div>

      {/* Panel overlays */}
      <SettingsPanel />
      <DataImportPanel />
      <KnowledgePanel />
    </div>
  );
}
