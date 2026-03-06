import { useState, useEffect, useRef } from 'react';
import { Wifi, WifiOff, Shield, Zap } from 'lucide-react';
import { useUIStore } from '@/stores/uiStore';
import { useSettingsStore, type ModelProvider } from '@/stores/settingsStore';
import gsap from 'gsap';
import clsx from 'clsx';

const providerLabels: Record<ModelProvider, string> = {
  openai: 'GPT-4o',
  claude: 'Claude',
  glm: 'GLM-4',
  gemini: 'Gemini',
  stark_protocol: 'Stark',
};

const providerColors: Record<ModelProvider, string> = {
  openai: '#39ff14',
  claude: '#ff8c00',
  glm: '#a855f7',
  gemini: '#3b82f6',
  stark_protocol: '#ef4444',
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
        {/* Hex logo */}
        <div
          className="w-5 h-5 flex items-center justify-center flex-shrink-0"
          style={{
            clipPath: 'polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%)',
            background: 'linear-gradient(135deg, rgba(0, 212, 255, 0.25), rgba(0, 128, 255, 0.15))',
          }}
        >
          <span className="text-[8px] font-display font-bold text-jarvis-blue">J</span>
        </div>

        <span className="font-display text-[11px] font-bold tracking-[0.2em] text-jarvis-blue glow-text hidden sm:block">
          J.A.R.V.I.S.
        </span>

        <div className="w-px h-4 bg-white/[0.06]" />

        <div className="flex items-center gap-1.5">
          <div className={clsx('status-dot', statusClass)} />
          <span className="text-[10px] font-mono text-gray-400 tracking-wider">{status}</span>
        </div>

        <div className="w-px h-4 bg-white/[0.06] hidden sm:block" />

        {/* Activity indicator */}
        <div className="hidden sm:flex items-center gap-1.5">
          <MiniSpectrum active={activity > 0.3} />
          <span className="text-[9px] font-mono text-jarvis-blue/40 tabular-nums">
            {Math.round(activity * 100)}%
          </span>
        </div>

        {/* Security badge */}
        <div className="hidden sm:flex items-center gap-1">
          <Shield size={10} className="text-hud-green/50" />
          <span className="text-[8px] font-mono text-hud-green/40">SEC</span>
        </div>
      </div>

      {/* Center label — subtle floating text */}
      <div className="hidden lg:flex items-center gap-2 mt-3 opacity-0 boot-1" style={{ animation: 'floatIn 0.5s cubic-bezier(0.16, 1, 0.3, 1) 0.4s both' }}>
        <Zap size={8} className="text-jarvis-blue/20" />
        <span className="text-[7px] font-mono tracking-[0.3em] text-jarvis-blue/15 uppercase">
          STARK INDUSTRIES DEFENSE SYSTEM
        </span>
        <Zap size={8} className="text-jarvis-blue/20" />
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
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] font-mono text-gray-600 tracking-wider hidden sm:block">
            {date}
          </span>
          <span className="font-mono text-[11px] text-gray-400 tracking-wider tabular-nums">
            {time}
          </span>
        </div>

        <div className="w-px h-4 bg-white/[0.06]" />

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
