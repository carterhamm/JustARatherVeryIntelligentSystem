import { useState, useEffect } from 'react';
import { Settings, Wifi, WifiOff } from 'lucide-react';
import { useUIStore } from '@/stores/uiStore';
import { useSettingsStore } from '@/stores/settingsStore';
import clsx from 'clsx';

const providerLabels: Record<string, { label: string; tag: string }> = {
  openai: { label: 'GPT-4o', tag: 'UPLINK' },
  claude: { label: 'Claude', tag: 'UPLINK' },
  gemini: { label: 'Gemini', tag: 'UPLINK' },
  stark_protocol: { label: 'Stark', tag: 'LOCAL' },
};

export default function HUDStatusBar() {
  const wsConnected = useUIStore((s) => s.wsConnected);
  const isThinking = useUIStore((s) => s.isThinking);
  const isSpeaking = useUIStore((s) => s.isSpeaking);
  const isListening = useUIStore((s) => s.isListening);
  const { modelPreference } = useSettingsStore();
  const provider = providerLabels[modelPreference] || providerLabels.openai;

  const [time, setTime] = useState('');

  useEffect(() => {
    const update = () => {
      const now = new Date();
      setTime(now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }));
    };
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, []);

  const status = isThinking ? 'PROCESSING' : isSpeaking ? 'SPEAKING' : isListening ? 'LISTENING' : 'STANDBY';

  return (
    <div className="flex items-center justify-between px-4 py-1.5 border-b border-jarvis-blue/10 bg-hud-panel backdrop-blur-hud flex-shrink-0 hud-boot-1">
      {/* Left: Logo + Status */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 flex items-center justify-center" style={{
            clipPath: 'polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%)',
            background: 'linear-gradient(135deg, rgba(0, 212, 255, 0.3), rgba(0, 128, 255, 0.2))',
          }}>
            <span className="text-[8px] font-display font-bold text-jarvis-blue">J</span>
          </div>
          <span className="font-display text-[11px] font-bold tracking-[0.2em] text-jarvis-blue glow-text">
            J.A.R.V.I.S.
          </span>
        </div>

        <div className="h-3 w-px bg-jarvis-blue/15" />

        {/* Status indicator */}
        <div className="flex items-center gap-1.5">
          <div className={clsx('hud-status-dot', {
            'online': status === 'STANDBY',
            'warning': status === 'PROCESSING',
            'error': status === 'SPEAKING',
          })} style={status === 'LISTENING' ? { background: '#00d4ff', boxShadow: '0 0 6px rgba(0,212,255,0.5)' } : undefined} />
          <span className="hud-label text-[9px]">{status}</span>
        </div>
      </div>

      {/* Center: Provider badge */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5 px-2 py-0.5 border border-jarvis-blue/15 bg-jarvis-blue/5"
          style={{ clipPath: 'polygon(0 3px, 3px 0, calc(100% - 3px) 0, 100% 3px, 100% calc(100% - 3px), calc(100% - 3px) 100%, 3px 100%, 0 calc(100% - 3px))' }}>
          <span className="hud-label text-[8px] text-gray-500">{provider.tag}</span>
          <span className="text-[10px] font-mono font-semibold text-jarvis-cyan">{provider.label}</span>
        </div>
      </div>

      {/* Right: Vitals + Time + Controls */}
      <div className="flex items-center gap-4">
        {/* Connection */}
        <div className="flex items-center gap-1.5">
          {wsConnected ? (
            <Wifi size={11} className="text-hud-green" />
          ) : (
            <WifiOff size={11} className="text-gray-600" />
          )}
          <span className="hud-label text-[8px]" style={{ color: wsConnected ? '#39ff14' : '#666' }}>
            {wsConnected ? 'ONLINE' : 'OFFLINE'}
          </span>
        </div>

        <div className="h-3 w-px bg-jarvis-blue/15" />

        {/* Time */}
        <span className="font-mono text-[10px] text-gray-400 tracking-wider tabular-nums">{time}</span>

        {/* Settings button */}
        <button
          onClick={() => window.dispatchEvent(new CustomEvent('jarvis-settings-toggle', { detail: { open: true } }))}
          className="w-6 h-6 flex items-center justify-center text-gray-500 hover:text-jarvis-blue transition-colors"
          aria-label="Settings"
        >
          <Settings size={13} />
        </button>
      </div>
    </div>
  );
}
