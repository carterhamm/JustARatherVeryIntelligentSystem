import { useState, useEffect, useRef } from 'react';
import { Wifi, WifiOff, ChevronDown, Lock } from 'lucide-react';
import { useUIStore } from '@/stores/uiStore';
import { useSettingsStore, type ModelProvider } from '@/stores/settingsStore';
import { api } from '@/services/api';
import clsx from 'clsx';

interface ProviderOption {
  id: ModelProvider;
  label: string;
  tag: string;
}

const providers: ProviderOption[] = [
  { id: 'openai', label: 'GPT-4o', tag: 'UPLINK' },
  { id: 'claude', label: 'Claude', tag: 'UPLINK' },
  { id: 'glm', label: 'GLM-4', tag: 'UPLINK' },
  { id: 'gemini', label: 'Gemini', tag: 'UPLINK' },
  { id: 'stark_protocol', label: 'Stark', tag: 'LOCAL' },
];

export default function StatusBar() {
  const wsConnected = useUIStore((s) => s.wsConnected);
  const isThinking = useUIStore((s) => s.isThinking);
  const isSpeaking = useUIStore((s) => s.isSpeaking);
  const isListening = useUIStore((s) => s.isListening);
  const { modelPreference, setModelPreference } = useSettingsStore();

  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const [time, setTime] = useState('');
  const [availableProviders, setAvailableProviders] = useState<Set<string>>(
    new Set(providers.map((p) => p.id)),
  );

  const currentProvider = providers.find((p) => p.id === modelPreference) || providers[0];

  useEffect(() => {
    const update = () => {
      const now = new Date();
      setTime(
        now.toLocaleTimeString([], {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: false,
        }),
      );
    };
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    api
      .get<{ id: string; available: boolean }[]>('/providers')
      .then((data) => {
        const available = new Set(data.filter((p) => p.available).map((p) => p.id));
        setAvailableProviders(available);
        if (!available.has(modelPreference)) {
          const fallback = providers.find((p) => available.has(p.id));
          if (fallback) setModelPreference(fallback.id);
        }
      })
      .catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    if (menuOpen) document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [menuOpen]);

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

  return (
    <div className="fixed top-4 left-4 right-4 z-30 flex justify-between items-start pointer-events-none">
      {/* Left capsule — Logo + Status */}
      <div className="glass-capsule pointer-events-auto px-5 py-2.5 flex items-center gap-3 boot-1">
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
      <div className="glass-capsule pointer-events-auto px-4 py-2.5 flex items-center gap-3 boot-1 relative" ref={menuRef}>
        {/* Model badge (clickable) */}
        <button
          onClick={() => setMenuOpen(!menuOpen)}
          className="flex items-center gap-1.5 hover:opacity-80 transition-opacity"
        >
          <span className="text-[8px] font-mono text-gray-500 uppercase tracking-wider">
            {currentProvider.tag}
          </span>
          <span className="text-[11px] font-mono font-semibold text-jarvis-cyan">
            {currentProvider.label}
          </span>
          <ChevronDown
            size={10}
            className={clsx('text-gray-500 transition-transform', { 'rotate-180': menuOpen })}
          />
        </button>

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

        {/* Provider dropdown */}
        {menuOpen && (
          <div className="absolute top-full right-0 mt-2 w-56 glass-heavy rounded-2xl overflow-hidden shadow-glass-lg z-50">
            <div className="px-4 py-2.5 border-b border-white/[0.05]">
              <span className="hud-label text-[8px]">SELECT PROVIDER</span>
            </div>
            {providers.map((p) => {
              const isAvailable = availableProviders.has(p.id);
              return (
                <button
                  key={p.id}
                  disabled={!isAvailable}
                  onClick={() => {
                    if (isAvailable) {
                      setModelPreference(p.id);
                      setMenuOpen(false);
                    }
                  }}
                  className={clsx(
                    'w-full text-left px-4 py-2.5 flex items-center justify-between transition-all',
                    {
                      'bg-jarvis-blue/[0.08] text-jarvis-cyan': modelPreference === p.id,
                      'text-gray-400 hover:bg-white/[0.03] hover:text-gray-300':
                        modelPreference !== p.id && isAvailable,
                      'text-gray-700 cursor-not-allowed opacity-40': !isAvailable,
                    },
                  )}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-[8px] font-mono text-gray-600 uppercase">
                      {p.tag}
                    </span>
                    <span className="text-[12px] font-mono font-semibold">{p.label}</span>
                    {!isAvailable && <Lock size={9} className="text-gray-600" />}
                  </div>
                  {modelPreference === p.id && isAvailable && (
                    <div className="w-2 h-2 rounded-full bg-jarvis-cyan shadow-[0_0_6px_rgba(0,212,255,0.5)]" />
                  )}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
