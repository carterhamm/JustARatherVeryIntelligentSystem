import { useState, useEffect, useRef } from 'react';
import { Wifi, WifiOff, Shield } from 'lucide-react';
import { useUIStore } from '@/stores/uiStore';
import { useSettingsStore, type ModelProvider } from '@/stores/settingsStore';
import gsap from 'gsap';
import clsx from 'clsx';
import arcReactorIcon from '@/assets/arc-reactor-icon.png';

const providerLabels: Record<ModelProvider, string> = {
  claude: 'Claude',
  gemini: 'Gemini',
  stark_protocol: 'Stark',
};

const providerColors: Record<ModelProvider, string> = {
  claude: '#ff8c00',
  gemini: '#4285F4',
  stark_protocol: '#00d4ff',
};

function MiniSpectrum({ active }: { active: boolean }) {
  return (
    <div className="flex items-center gap-[1px] h-3">
      {Array.from({ length: 5 }).map((_, i) => (
        <div
          key={i}
          className="w-[2px] rounded-full transition-all duration-500"
          style={{
            height: active ? `${40 + Math.sin(Date.now() / 300 + i) * 40}%` : '20%',
            background: active ? 'rgba(0, 212, 255, 0.5)' : 'rgba(255,255,255,0.08)',
            animationDelay: `${i * 0.1}s`,
          }}
        />
      ))}
    </div>
  );
}

export default function StatusBar() {
  const wsConnected = useUIStore((s) => s.wsConnected);
  const isThinking = useUIStore((s) => s.isThinking);
  const isSpeaking = useUIStore((s) => s.isSpeaking);
  const isListening = useUIStore((s) => s.isListening);
  const activity = useUIStore((s) => s.jarvisActivity);
  const modelPreference = useSettingsStore((s) => s.modelPreference);
  const voiceEnabled = useSettingsStore((s) => s.voiceEnabled);
  const use24HourTime = useSettingsStore((s) => s.use24HourTime);

  const [time, setTime] = useState('');
  const [date, setDate] = useState('');
  const leftRef = useRef<HTMLDivElement>(null);
  const rightRef = useRef<HTMLDivElement>(null);

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
      setDate(
        now.toLocaleDateString([], {
          month: 'short',
          day: 'numeric',
        }),
      );
    };
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, [use24HourTime]);

  // GSAP boot animation
  useEffect(() => {
    if (leftRef.current && rightRef.current) {
      gsap.fromTo(
        leftRef.current,
        { opacity: 0, x: -20, scale: 0.95 },
        { opacity: 1, x: 0, scale: 1, duration: 0.6, ease: 'power3.out', delay: 0.1 },
      );
      gsap.fromTo(
        rightRef.current,
        { opacity: 0, x: 20, scale: 0.95 },
        { opacity: 1, x: 0, scale: 1, duration: 0.6, ease: 'power3.out', delay: 0.15 },
      );
    }
  }, []);

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
  const modelColor = providerColors[modelPreference] || '#00d4ff';

  const openModelPicker = () => {
    window.dispatchEvent(new CustomEvent('jarvis-model-toggle'));
  };

  return (
    <div className="fixed top-4 left-4 right-4 z-30 flex justify-between items-start pointer-events-none">
      {/* Left capsule — Logo + Status + Activity */}
      <div ref={leftRef} className="glass-capsule pointer-events-auto h-10 px-4 flex items-center gap-2.5 opacity-0">
        <img
          src={arcReactorIcon}
          alt="Arc Reactor"
          className="w-5 h-5 flex-shrink-0 object-contain"
          style={{ filter: 'drop-shadow(0 0 3px rgba(0, 212, 255, 0.4))' }}
        />

        <span className="font-display text-[11px] font-bold tracking-[0.2em] text-jarvis-blue glow-text hidden sm:block">
          J.A.R.V.I.S.
        </span>

        <div className="w-px h-4 bg-white/[0.06]" />

        <div className="flex items-center gap-1.5">
          <div className={clsx('status-dot', statusClass)} />
          <span className="text-[10px] font-mono text-gray-400 tracking-wider">{status}</span>
        </div>

        <div className="w-px h-4 bg-white/[0.06] hidden sm:block" />

        {/* Activity indicator — click to open diagnostics */}
        <button
          onClick={() => window.dispatchEvent(new CustomEvent('jarvis-diagnostics-toggle'))}
          className="hidden sm:flex items-center gap-1.5 hover:opacity-80 transition-opacity cursor-pointer"
          title="Open Diagnostics"
        >
          <MiniSpectrum active={activity > 0.3} />
          <span className="text-[9px] font-mono text-jarvis-blue/40 tabular-nums">
            {Math.round(activity * 100)}%
          </span>
        </button>

        {/* Security badge */}
        <div className="hidden sm:flex items-center gap-1">
          <Shield size={10} className="text-hud-green/50" />
          <span className="text-[8px] font-mono text-hud-green/40">SEC</span>
        </div>
      </div>

      {/* Center label — subtle floating text */}
      <div className="hidden lg:flex items-center gap-2 mt-3 opacity-0 boot-1" style={{ animation: 'floatIn 0.5s cubic-bezier(0.16, 1, 0.3, 1) 0.4s both' }}>
        <Shield size={8} className="text-jarvis-blue/20" />
        <span className="text-[7px] font-mono tracking-[0.3em] text-jarvis-blue/15 uppercase">
          STARK INDUSTRIES SECURE SERVER
        </span>
        <Shield size={8} className="text-jarvis-blue/20" />
      </div>

      {/* Right capsule — Model + Time + Connection */}
      <div ref={rightRef} className="glass-capsule pointer-events-auto h-10 px-4 flex items-center gap-3 opacity-0">
        {/* Current model badge — clickable */}
        <button
          onClick={openModelPicker}
          className="flex items-center gap-1.5 hover:opacity-80 transition-opacity"
        >
          <div
            className="w-1.5 h-1.5 rounded-full"
            style={{
              backgroundColor: modelColor,
              boxShadow: `0 0 6px ${modelColor}66`,
            }}
          />
          <span className="text-[10px] font-mono tracking-wider" style={{ color: modelColor }}>
            {modelLabel}
          </span>
        </button>

        <div className="w-px h-4 bg-white/[0.06]" />

        {/* Voice indicator */}
        <div className="flex items-center gap-1">
          <div
            className={clsx('w-1 h-1 rounded-full', {
              'bg-jarvis-gold shadow-[0_0_4px_rgba(240,165,0,0.5)]': voiceEnabled,
              'bg-gray-700': !voiceEnabled,
            })}
          />
          <span className="text-[8px] font-mono text-gray-600 tracking-wider hidden sm:block">
            {voiceEnabled ? 'VOX' : 'MUTE'}
          </span>
        </div>

        <div className="w-px h-4 bg-white/[0.06]" />

        {/* Date + Time */}
        <div className="flex flex-col items-end gap-1 hidden sm:flex">
          <span className="text-[9px] font-mono text-gray-500 tracking-wider leading-none">
            {date}
          </span>
          <span className="font-mono text-[11px] text-gray-300 tracking-wider tabular-nums leading-none">
            {time}
          </span>
        </div>
        <span className="font-mono text-[11px] text-gray-300 tracking-wider tabular-nums sm:hidden">
          {time}
        </span>

        <div className="w-px h-4 bg-white/[0.06]" />

        {/* Connection — click to view active sessions */}
        <button
          onClick={() => window.dispatchEvent(new CustomEvent('jarvis-sessions-manage-toggle'))}
          className="relative group flex items-center gap-1.5 hover:opacity-80 transition-opacity cursor-pointer"
          title="View Active Sessions"
        >
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
          {/* Hover tooltip */}
          <div className="absolute top-full right-0 mt-2 px-3 py-1.5 glass hud-clip-sm whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
            <span className="text-[9px] font-mono text-gray-300">
              {wsConnected ? 'Click to view active sessions' : 'Disconnected from Stark Industries Secure Server'}
            </span>
          </div>
        </button>
      </div>
    </div>
  );
}
