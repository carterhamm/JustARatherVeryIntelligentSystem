import HUDStatusBar from '@/components/HUD/HUDStatusBar';
import HUDNavPanel from '@/components/HUD/HUDNavPanel';
import HUDDiagnosticsPanel from '@/components/HUD/HUDDiagnosticsPanel';
import ChatArea from '@/components/HUD/ChatArea';
import SettingsPanel from '@/components/SettingsPanel';
import DataImportPanel from '@/components/DataImportPanel';
import KnowledgePanel from '@/components/KnowledgePanel';

export default function MainPage() {
  return (
    <div className="relative h-screen w-screen overflow-hidden bg-jarvis-darker">
      {/* HUD Layout */}
      <div className="relative z-10 flex flex-col h-full">
        {/* Top status bar */}
        <HUDStatusBar />

        {/* Main content area */}
        <div className="flex flex-1 min-h-0">
          {/* Left nav */}
          <HUDNavPanel />

          {/* Center chat */}
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
