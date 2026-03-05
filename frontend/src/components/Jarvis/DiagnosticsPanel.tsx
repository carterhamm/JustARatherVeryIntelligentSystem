import { useState, useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { X } from 'lucide-react';
import { useUIStore } from '@/stores/uiStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useChatStore } from '@/stores/chatStore';
import clsx from 'clsx';

const modelNames: Record<string, string> = {
  openai: 'GPT-4o',
  claude: 'Claude Sonnet',
  gemini: 'Gemini Flash',
  glm: 'GLM-4',
  stark_protocol: 'Gemma 3 4B',
};

const providerTags: Record<string, string> = {
  openai: 'UPLINK',
  claude: 'UPLINK',
  gemini: 'UPLINK',
  glm: 'UPLINK',
  stark_protocol: 'LOCAL',
};

function ProgressRing({
  value,
  size = 56,
  stroke = 3,
  color = '#00d4ff',
}: {
  value: number;
  size?: number;
  stroke?: number;
  color?: string;
}) {
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (value / 100) * circumference;

  return (
    <svg width={size} height={size} className="progress-ring">
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="rgba(255,255,255,0.04)"
        strokeWidth={stroke}
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke={color}
        strokeWidth={stroke}
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        strokeLinecap="round"
        style={{ filter: `drop-shadow(0 0 6px ${color}50)` }}
      />
    </svg>
  );
}

export default function DiagnosticsPanel() {
  const [open, setOpen] = useState(false);
  const wsConnected = useUIStore((s) => s.wsConnected);
  const isThinking = useUIStore((s) => s.isThinking);
  const isSpeaking = useUIStore((s) => s.isSpeaking);
  const activity = useUIStore((s) => s.jarvisActivity);
  const { modelPreference, voiceEnabled } = useSettingsStore();
  const { messages } = useChatStore();

  const activityPct = Math.round(activity * 100);
  const errorCount = messages.filter((m) => m.id.startsWith('error-')).length;

  useEffect(() => {
    const handler = () => setOpen((prev) => !prev);
    window.addEventListener('jarvis-diagnostics-toggle', handler);
    return () => window.removeEventListener('jarvis-diagnostics-toggle', handler);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-40 panel-backdrop"
            onClick={() => setOpen(false)}
          />

          <motion.div
            initial={{ opacity: 0, x: 40, scale: 0.97 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: 40, scale: 0.97 }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
            className="fixed right-5 top-20 bottom-24 z-50 w-72 glass-heavy rounded-3xl flex flex-col overflow-hidden"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.05]">
              <span className="hud-label text-[10px]">DIAGNOSTICS</span>
              <button
                onClick={() => setOpen(false)}
                className="glass-circle w-8 h-8 flex items-center justify-center"
              >
                <X size={14} className="text-gray-400" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-5 space-y-5">
              {/* Activity Ring */}
              <div className="flex flex-col items-center">
                <div className="relative">
                  <ProgressRing
                    value={activityPct}
                    size={72}
                    stroke={3}
                    color={isThinking ? '#ffbf00' : isSpeaking ? '#f0a500' : '#00d4ff'}
                  />
                  <div className="absolute inset-0 flex items-center justify-center">
                    <span
                      className={clsx('text-[15px] font-mono font-bold', {
                        'text-hud-amber': isThinking,
                        'text-jarvis-gold': isSpeaking,
                        'text-jarvis-cyan': !isThinking && !isSpeaking,
                      })}
                    >
                      {activityPct}%
                    </span>
                  </div>
                </div>
                <span className="hud-label text-[8px] mt-2">
                  {isThinking ? 'PROCESSING' : isSpeaking ? 'SPEAKING' : 'CORE ACTIVITY'}
                </span>
              </div>

              {/* Active Model */}
              <div className="glass-subtle rounded-2xl p-4">
                <span className="hud-label text-[8px] block mb-2">ACTIVE MODEL</span>
                <div className="flex items-center gap-2">
                  <div
                    className={clsx('w-2 h-2 rounded-full', {
                      'bg-hud-green shadow-[0_0_6px_rgba(57,255,20,0.5)]': wsConnected,
                      'bg-gray-600': !wsConnected,
                    })}
                  />
                  <span className="text-[13px] font-mono text-gray-200 font-semibold">
                    {modelNames[modelPreference] || 'Unknown'}
                  </span>
                </div>
                <span
                  className={clsx('text-[9px] font-mono mt-1 block', {
                    'text-jarvis-blue': providerTags[modelPreference] === 'UPLINK',
                    'text-jarvis-gold': providerTags[modelPreference] === 'LOCAL',
                  })}
                >
                  {providerTags[modelPreference] || 'UPLINK'} PROTOCOL
                </span>
              </div>

              {/* Connection */}
              <div className="glass-subtle rounded-2xl p-4">
                <span className="hud-label text-[8px] block mb-2">CONNECTION</span>
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] text-gray-500 font-mono">WebSocket</span>
                    <span
                      className={clsx('text-[9px] font-mono', {
                        'text-hud-green': wsConnected,
                        'text-gray-600': !wsConnected,
                      })}
                    >
                      {wsConnected ? 'ACTIVE' : 'DOWN'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] text-gray-500 font-mono">Voice</span>
                    <span
                      className={clsx('text-[9px] font-mono', {
                        'text-jarvis-gold': voiceEnabled,
                        'text-gray-600': !voiceEnabled,
                      })}
                    >
                      {voiceEnabled ? 'ACTIVE' : 'STANDBY'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Session Telemetry */}
              <div className="glass-subtle rounded-2xl p-4">
                <span className="hud-label text-[8px] block mb-2">SESSION</span>
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-[10px] text-gray-500 font-mono">Messages</span>
                    <span className="text-[10px] font-mono text-gray-300 tabular-nums">
                      {messages.length}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[10px] text-gray-500 font-mono">Errors</span>
                    <span
                      className={clsx('text-[10px] font-mono tabular-nums', {
                        'text-hud-red': errorCount > 0,
                        'text-gray-600': errorCount === 0,
                      })}
                    >
                      {errorCount}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[10px] text-gray-500 font-mono">Status</span>
                    <span
                      className={clsx('text-[10px] font-mono', {
                        'text-hud-amber': isThinking,
                        'text-hud-green': !isThinking,
                      })}
                    >
                      {isThinking ? 'BUSY' : 'READY'}
                    </span>
                  </div>
                </div>
              </div>

              {/* System */}
              <div className="glass-subtle rounded-2xl p-4">
                <span className="hud-label text-[8px] block mb-2">SYSTEM</span>
                <div className="space-y-1.5">
                  <div className="flex justify-between">
                    <span className="text-[9px] text-gray-600 font-mono">Version</span>
                    <span className="text-[9px] text-gray-500 font-mono">v1.0.0</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[9px] text-gray-600 font-mono">Protocol</span>
                    <span className="text-[9px] text-gray-500 font-mono">WS/JSON</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[9px] text-gray-600 font-mono">Auth</span>
                    <span className="text-[9px] text-hud-green font-mono">JWT</span>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
