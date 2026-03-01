import JarvisCore from '@/components/JarvisCore/JarvisCore';
import Sidebar from '@/components/Sidebar';
import ChatPanel from '@/components/ChatPanel';
import SettingsPanel from '@/components/SettingsPanel';
import DataImportPanel from '@/components/DataImportPanel';
import KnowledgePanel from '@/components/KnowledgePanel';

export default function MainPage() {
  return (
    <div className="relative h-screen w-screen overflow-hidden bg-jarvis-darker">
      {/* 3D Background */}
      <div className="fixed inset-0 z-0">
        <JarvisCore />
      </div>

      {/* UI Overlay */}
      <div className="relative z-10 flex h-full">
        <Sidebar />
        <ChatPanel />
      </div>

      {/* Panel Overlays */}
      <SettingsPanel />
      <DataImportPanel />
      <KnowledgePanel />
    </div>
  );
}
