import { useUIStore } from '@/stores/uiStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useChatStore } from '@/stores/chatStore';
import { Activity, Cpu, Volume2, VolumeX, Wifi, WifiOff, Zap } from 'lucide-react';
import clsx from 'clsx';

const modelNames: Record<string, string> = {
  openai: 'GPT-4o',
  claude: 'Claude Sonnet 4',
  gemini: 'Gemini 2.5 Flash',
  stark_protocol: 'Gemma 3 27B',
};

export default function HUDDiagnosticsPanel() {
  const wsConnected = useUIStore((s) => s.wsConnected);
  const isThinking = useUIStore((s) => s.isThinking);
  const activity = useUIStore((s) => s.jarvisActivity);
  const { modelPreference, voiceEnabled } = useSettingsStore();
  const { currentConversation, messages } = useChatStore();

  return (
    <div className="w-48 border-l border-jarvis-blue/10 bg-hud-panel backdrop-blur-hud flex-shrink-0 flex flex-col hud-boot-3 overflow-y-auto">
      {/* Model Info */}
      <div className="px-3 py-2 border-b border-jarvis-blue/8">
        <span className="hud-label text-[8px] block mb-1.5">ACTIVE MODEL</span>
        <div className="flex items-center gap-1.5">
          <Cpu size={11} className="text-jarvis-cyan flex-shrink-0" />
          <span className="text-[11px] font-mono text-gray-300 truncate">
            {modelNames[modelPreference] || 'Unknown'}
          </span>
        </div>
      </div>

      {/* Connection */}
      <div className="px-3 py-2 border-b border-jarvis-blue/8">
        <span className="hud-label text-[8px] block mb-1.5">CONNECTION</span>
        <div className="flex items-center gap-1.5">
          {wsConnected ? (
            <Wifi size={11} className="text-hud-green" />
          ) : (
            <WifiOff size={11} className="text-gray-600" />
          )}
          <span className={clsx('text-[10px] font-mono', {
            'text-hud-green': wsConnected,
            'text-gray-600': !wsConnected,
          })}>
            {wsConnected ? 'CONNECTED' : 'DISCONNECTED'}
          </span>
        </div>
        <div className="mt-1 text-[9px] font-mono text-gray-600">
          WS {wsConnected ? 'ACTIVE' : 'INACTIVE'}
        </div>
      </div>

      {/* Voice */}
      <div className="px-3 py-2 border-b border-jarvis-blue/8">
        <span className="hud-label text-[8px] block mb-1.5">VOICE</span>
        <div className="flex items-center gap-1.5">
          {voiceEnabled ? (
            <Volume2 size={11} className="text-jarvis-gold" />
          ) : (
            <VolumeX size={11} className="text-gray-600" />
          )}
          <span className={clsx('text-[10px] font-mono', {
            'text-jarvis-gold': voiceEnabled,
            'text-gray-600': !voiceEnabled,
          })}>
            {voiceEnabled ? 'ENABLED' : 'DISABLED'}
          </span>
        </div>
      </div>

      {/* Activity */}
      <div className="px-3 py-2 border-b border-jarvis-blue/8">
        <span className="hud-label text-[8px] block mb-1.5">CORE ACTIVITY</span>
        <div className="flex items-center gap-1.5 mb-1">
          <Activity size={11} className="text-jarvis-blue" />
          <span className="text-[10px] font-mono text-gray-400">
            {Math.round(activity * 100)}%
          </span>
        </div>
        {/* Activity bar */}
        <div className="h-1 bg-jarvis-darker rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-jarvis-blue to-jarvis-cyan transition-all duration-300"
            style={{ width: `${Math.round(activity * 100)}%` }}
          />
        </div>
      </div>

      {/* Session info */}
      <div className="px-3 py-2 border-b border-jarvis-blue/8">
        <span className="hud-label text-[8px] block mb-1.5">SESSION</span>
        <div className="space-y-0.5">
          <div className="flex justify-between">
            <span className="text-[9px] text-gray-600">Messages</span>
            <span className="text-[9px] font-mono text-gray-400">{messages.length}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-[9px] text-gray-600">Status</span>
            <span className={clsx('text-[9px] font-mono', {
              'text-hud-amber': isThinking,
              'text-hud-green': !isThinking,
            })}>
              {isThinking ? 'BUSY' : 'READY'}
            </span>
          </div>
        </div>
      </div>

      {/* System vitals */}
      <div className="px-3 py-2 flex-1">
        <span className="hud-label text-[8px] block mb-1.5">SYSTEM</span>
        <div className="space-y-1">
          <div className="flex items-center gap-1.5">
            <Zap size={9} className="text-jarvis-blue/40" />
            <span className="text-[9px] text-gray-600 font-mono">v1.0.0</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="hud-status-dot online" style={{ width: 4, height: 4 }} />
            <span className="text-[9px] text-gray-600 font-mono">API ONLINE</span>
          </div>
        </div>
      </div>
    </div>
  );
}
