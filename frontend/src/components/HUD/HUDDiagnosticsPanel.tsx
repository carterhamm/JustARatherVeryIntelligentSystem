import { useUIStore } from '@/stores/uiStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useChatStore } from '@/stores/chatStore';
import clsx from 'clsx';

const modelNames: Record<string, string> = {
  claude: 'Claude Sonnet',
  gemini: 'Gemini Flash',
  stark_protocol: 'Stark Protocol',
};

const providerTags: Record<string, string> = {
  claude: 'UPLINK',
  gemini: 'UPLINK',
  stark_protocol: 'LOCAL',
};

function ProgressRing({ value, size = 44, stroke = 3, color = '#00d4ff' }: { value: number; size?: number; stroke?: number; color?: string }) {
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (value / 100) * circumference;

  return (
    <svg width={size} height={size} className="progress-ring">
      <circle
        cx={size / 2} cy={size / 2} r={radius}
        fill="none" stroke="rgba(0,212,255,0.08)"
        strokeWidth={stroke}
      />
      <circle
        cx={size / 2} cy={size / 2} r={radius}
        fill="none" stroke={color}
        strokeWidth={stroke}
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        strokeLinecap="round"
        style={{ filter: `drop-shadow(0 0 4px ${color}40)` }}
      />
    </svg>
  );
}

function DataBars({ count = 8, active = false }: { count?: number; active?: boolean }) {
  return (
    <div className="data-bars">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="data-bar"
          style={{
            height: active ? `${Math.random() * 16 + 4}px` : '4px',
            opacity: active ? 0.6 + Math.random() * 0.4 : 0.15,
            animationDelay: `${i * 0.15}s`,
          }}
        />
      ))}
    </div>
  );
}

export default function HUDDiagnosticsPanel() {
  const wsConnected = useUIStore((s) => s.wsConnected);
  const isThinking = useUIStore((s) => s.isThinking);
  const isSpeaking = useUIStore((s) => s.isSpeaking);
  const activity = useUIStore((s) => s.jarvisActivity);
  const { modelPreference, voiceEnabled } = useSettingsStore();
  const { messages } = useChatStore();

  const activityPct = Math.round(activity * 100);

  return (
    <div className="w-52 border-l border-jarvis-blue/10 bg-hud-panel backdrop-blur-hud flex-shrink-0 flex flex-col hud-boot-3 overflow-y-auto">
      {/* Header */}
      <div className="px-3 py-2 border-b border-jarvis-blue/8">
        <span className="hud-label text-[8px]">DIAGNOSTICS</span>
      </div>

      {/* Core Activity Ring */}
      <div className="px-3 py-3 border-b border-jarvis-blue/8 flex flex-col items-center">
        <div className="relative">
          <ProgressRing
            value={activityPct}
            size={64}
            stroke={3}
            color={isThinking ? '#ffbf00' : isSpeaking ? '#f0a500' : '#00d4ff'}
          />
          <div className="absolute inset-0 flex items-center justify-center">
            <span className={clsx('text-[13px] font-mono font-bold', {
              'text-hud-amber': isThinking,
              'text-jarvis-gold': isSpeaking,
              'text-jarvis-cyan': !isThinking && !isSpeaking,
            })}>
              {activityPct}%
            </span>
          </div>
        </div>
        <span className="hud-label text-[7px] mt-1.5">
          {isThinking ? 'PROCESSING' : isSpeaking ? 'SPEAKING' : 'CORE ACTIVITY'}
        </span>
      </div>

      {/* Active Model */}
      <div className="px-3 py-2.5 border-b border-jarvis-blue/8 relative hud-brackets">
        <span className="hud-label text-[7px] block mb-1.5">ACTIVE MODEL</span>
        <div className="flex items-center gap-1.5">
          <div className={clsx('w-1.5 h-1.5 rounded-full', {
            'bg-hud-green shadow-[0_0_4px_rgba(57,255,20,0.5)]': wsConnected,
            'bg-gray-600': !wsConnected,
          })} />
          <span className="text-[11px] font-mono text-gray-200 font-semibold">
            {modelNames[modelPreference] || 'Unknown'}
          </span>
        </div>
        <span className={clsx('text-[8px] font-mono mt-0.5 block', {
          'text-jarvis-blue': providerTags[modelPreference] === 'UPLINK',
          'text-jarvis-gold': providerTags[modelPreference] === 'LOCAL',
        })}>
          {providerTags[modelPreference] || 'UPLINK'} PROTOCOL
        </span>
      </div>

      {/* Connection Status */}
      <div className="px-3 py-2.5 border-b border-jarvis-blue/8">
        <span className="hud-label text-[7px] block mb-1.5">CONNECTION</span>
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="text-[9px] text-gray-500 font-mono">WebSocket</span>
            <div className="flex items-center gap-1">
              <div className={clsx('hud-status-dot', wsConnected ? 'online' : 'offline')}
                style={{ width: 4, height: 4 }} />
              <span className={clsx('text-[8px] font-mono', {
                'text-hud-green': wsConnected,
                'text-gray-600': !wsConnected,
              })}>
                {wsConnected ? 'ACTIVE' : 'DOWN'}
              </span>
            </div>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[9px] text-gray-500 font-mono">API</span>
            <div className="flex items-center gap-1">
              <div className="hud-status-dot online" style={{ width: 4, height: 4 }} />
              <span className="text-[8px] font-mono text-hud-green">ONLINE</span>
            </div>
          </div>
        </div>
      </div>

      {/* Voice Status */}
      <div className="px-3 py-2.5 border-b border-jarvis-blue/8">
        <span className="hud-label text-[7px] block mb-1.5">VOICE INTERFACE</span>
        <div className="flex items-center justify-between mb-1.5">
          <span className={clsx('text-[10px] font-mono font-semibold', {
            'text-jarvis-gold': voiceEnabled,
            'text-gray-600': !voiceEnabled,
          })}>
            {voiceEnabled ? 'ACTIVE' : 'STANDBY'}
          </span>
          <span className="text-[8px] font-mono text-gray-600">
            {modelPreference === 'stark_protocol' ? 'JARVIS TTS' : 'ELEVENLABS'}
          </span>
        </div>
        <DataBars count={10} active={isSpeaking} />
      </div>

      {/* Session Telemetry */}
      <div className="px-3 py-2.5 border-b border-jarvis-blue/8">
        <span className="hud-label text-[7px] block mb-1.5">SESSION TELEMETRY</span>
        <div className="space-y-1">
          <div className="flex justify-between items-center">
            <span className="text-[9px] text-gray-500 font-mono">Messages</span>
            <span className="text-[9px] font-mono text-gray-300 tabular-nums">{messages.length}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-[9px] text-gray-500 font-mono">Errors</span>
            <span className={clsx('text-[9px] font-mono tabular-nums', {
              'text-hud-red': messages.filter(m => m.id.startsWith('error-')).length > 0,
              'text-gray-600': messages.filter(m => m.id.startsWith('error-')).length === 0,
            })}>
              {messages.filter(m => m.id.startsWith('error-')).length}
            </span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-[9px] text-gray-500 font-mono">Status</span>
            <span className={clsx('text-[9px] font-mono', {
              'text-hud-amber': isThinking,
              'text-hud-green': !isThinking,
            })}>
              {isThinking ? 'BUSY' : 'READY'}
            </span>
          </div>
        </div>
      </div>

      {/* System Info */}
      <div className="px-3 py-2.5 flex-1">
        <span className="hud-label text-[7px] block mb-1.5">SYSTEM</span>
        <div className="space-y-1">
          <div className="flex justify-between">
            <span className="text-[8px] text-gray-600 font-mono">Version</span>
            <span className="text-[8px] text-gray-500 font-mono">v1.0.0</span>
          </div>
          <div className="flex justify-between">
            <span className="text-[8px] text-gray-600 font-mono">Protocol</span>
            <span className="text-[8px] text-gray-500 font-mono">WS/JSON</span>
          </div>
          <div className="flex justify-between">
            <span className="text-[8px] text-gray-600 font-mono">Auth</span>
            <span className="text-[8px] text-hud-green font-mono">JWT</span>
          </div>
        </div>
      </div>
    </div>
  );
}
