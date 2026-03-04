import { useState, useEffect } from 'react';
import { Wifi, WifiOff } from 'lucide-react';
import { useUIStore } from '@/stores/uiStore';
import { useSettingsStore, type ModelProvider } from '@/stores/settingsStore';
import clsx from 'clsx';

const providerLabels: Record<ModelProvider, string> = {
  openai: 'GPT-4o',
  claude: 'Claude',
  glm: 'GLM-4',
  gemini: 'Gemini',
  stark_protocol: 'Stark',
};

export default function StatusBar() {
  const wsConnected = useUIStore((s) => s.wsConnected);
  const isThinking = useUIStore((s) => s.isThinking);
  const isSpeaking = useUIStore((s) => s.isSpeaking);
  const isListening = useUIStore((s) => s.isListening);
  const modelPreference = useSettingsStore((s) => s.modelPreference);
  const use24HourTime = useSettingsStore((s) => s.use24HourTime);

  const [time, setTime] = useState('');

  useEffect(() => {
    const update = () => {
      const now = new Date();
      setTime(
        now.toLocaleTimeString([], {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: !use24HourTime,
        }),
      );
    };
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, [use24HourTime]);

  const status = isThinking
    ? 'PROCESSING'
    : isSpeaking
      ? 'SPEAKING'
      : isListening
        ? 'LISTENING'
        : 'STANDBY';

  const statusClass = isThinking
    ? 'processing'
    : isSpeaking
      ? 'warning'
      : isListening
        ? 'processing'
        : 'online';

  const modelLabel = providerLabels[modelPreference] || modelPreference;

  return (
    <div className="fixed top-4 left-4 right-4 z-30 flex justify-between items-start pointer-events-none">
      {/* Left capsule — Logo + Status */}
      <div className="glass-capsule pointer-events-auto px-5 py-2.5 flex items-center gap-3 boot-1 ml-14">
        {/* Hex logo */}
        <div
          className="w-7 h-7 flex items-center justify-center flex-shrink-0"
          style={{
            clipPath: 'polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%)',
            background: 'linear-gradient(135deg, rgba(0, 212, 255, 0.25), rgba(0, 128, 255, 0.15))',
          }}
        >
          <span className="text-[9px] font-display font-bold text-jarvis-blue">J</span>
        </div>

        <span className="font-display text-[11px] font-bold tracking-[0.2em] text-jarvis-blue glow-text hidden sm:block">
          J.A.R.V.I.S.
        </span>

        <div className="w-px h-5 bg-white/[0.06]" />

        <div className="flex items-center gap-1.5">
          <div className={clsx('status-dot', statusClass)} />
          <span className="text-[10px] font-mono text-gray-400 tracking-wider">{status}</span>
        </div>
      </div>

      {/* Right capsule — Model + Time + Connection */}
      <div className="glass-capsule pointer-events-auto px-4 py-2.5 flex items-center gap-3 boot-1">
        {/* Current model badge — passive display */}
        <div className="flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-jarvis-cyan shadow-[0_0_4px_rgba(0,212,255,0.4)]" />
          <span className="text-[10px] font-mono text-jarvis-cyan tracking-wider">
            {modelLabel}
          </span>
        </div>

        <div className="w-px h-5 bg-white/[0.06]" />

        {/* Time */}
        <span className="font-mono text-[11px] text-gray-400 tracking-wider tabular-nums">
          {time}
        </span>

        <div className="w-px h-5 bg-white/[0.06]" />

        {/* Connection */}
        <div className="flex items-center gap-1.5">
          {wsConnected ? (
            <Wifi size={12} className="text-hud-green" />
          ) : (
            <WifiOff size={12} className="text-gray-600" />
          )}
          <span
            className="text-[9px] font-mono tracking-wider"
            style={{ color: wsConnected ? '#39ff14' : '#666' }}
          >
            {wsConnected ? 'ONLINE' : 'OFFLINE'}
          </span>
        </div>
      </div>
    </div>
  );
}
