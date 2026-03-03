import { useState, useEffect, useRef } from 'react';
import { Settings, Wifi, WifiOff, ChevronDown } from 'lucide-react';
import { useUIStore } from '@/stores/uiStore';
import { useSettingsStore, type ModelProvider } from '@/stores/settingsStore';
import { useChatStore } from '@/stores/chatStore';
import clsx from 'clsx';

interface ProviderOption {
  id: ModelProvider;
  label: string;
  tag: string;
  description: string;
}

const providers: ProviderOption[] = [
  { id: 'openai', label: 'GPT-4o', tag: 'UPLINK', description: 'OpenAI flagship' },
  { id: 'claude', label: 'Claude', tag: 'UPLINK', description: 'Anthropic Sonnet' },
  { id: 'glm', label: 'GLM-4', tag: 'UPLINK', description: 'ZhipuAI Coding Pro' },
  { id: 'gemini', label: 'Gemini', tag: 'UPLINK', description: 'Google DeepMind' },
  { id: 'stark_protocol', label: 'Stark', tag: 'LOCAL', description: 'Gemma 3 (LM Studio)' },
];

export default function HUDStatusBar() {
  const wsConnected = useUIStore((s) => s.wsConnected);
  const isThinking = useUIStore((s) => s.isThinking);
  const isSpeaking = useUIStore((s) => s.isSpeaking);
  const isListening = useUIStore((s) => s.isListening);
  const { modelPreference, setModelPreference } = useSettingsStore();
  const messages = useChatStore((s) => s.messages);

  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const [time, setTime] = useState('');

  // Count recent error messages for the stacked badge
  const errorCount = messages.filter((m) => m.role === 'system' && m.id.startsWith('error-')).length;

  const currentProvider = providers.find((p) => p.id === modelPreference) || providers[0];

  useEffect(() => {
    const update = () => {
      const now = new Date();
      setTime(now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }));
    };
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, []);

  // Close menu on outside click
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    if (menuOpen) document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [menuOpen]);

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

        {/* Error count badge */}
        {errorCount > 0 && (
          <div className="flex items-center gap-1 px-1.5 py-0.5 bg-red-500/10 border border-red-500/20 rounded-sm">
            <span className="text-[9px] font-mono text-red-400">{errorCount} ERROR{errorCount > 1 ? 'S' : ''}</span>
          </div>
        )}
      </div>

      {/* Center: Provider badge (clickable) */}
      <div className="relative" ref={menuRef}>
        <button
          onClick={() => setMenuOpen(!menuOpen)}
          className="flex items-center gap-1.5 px-2.5 py-1 border border-jarvis-blue/15 bg-jarvis-blue/5 hover:bg-jarvis-blue/10 transition-colors cursor-pointer"
          style={{ clipPath: 'polygon(0 3px, 3px 0, calc(100% - 3px) 0, 100% 3px, 100% calc(100% - 3px), calc(100% - 3px) 100%, 3px 100%, 0 calc(100% - 3px))' }}
        >
          <span className="hud-label text-[8px] text-gray-500">{currentProvider.tag}</span>
          <span className="text-[10px] font-mono font-semibold text-jarvis-cyan">{currentProvider.label}</span>
          <ChevronDown size={10} className={clsx('text-gray-500 transition-transform', { 'rotate-180': menuOpen })} />
        </button>

        {/* Dropdown */}
        {menuOpen && (
          <div className="absolute top-full left-1/2 -translate-x-1/2 mt-1 w-52 border border-jarvis-blue/20 bg-jarvis-darker/95 backdrop-blur-xl shadow-lg shadow-black/50 z-50"
            style={{ clipPath: 'polygon(0 4px, 4px 0, calc(100% - 4px) 0, 100% 4px, 100% calc(100% - 4px), calc(100% - 4px) 100%, 4px 100%, 0 calc(100% - 4px))' }}
          >
            <div className="px-2 py-1.5 border-b border-jarvis-blue/10">
              <span className="hud-label text-[8px]">SELECT PROVIDER</span>
            </div>
            {providers.map((p) => (
              <button
                key={p.id}
                onClick={() => {
                  setModelPreference(p.id);
                  setMenuOpen(false);
                }}
                className={clsx(
                  'w-full text-left px-3 py-2 flex items-center justify-between transition-colors',
                  {
                    'bg-jarvis-blue/10 text-jarvis-cyan': modelPreference === p.id,
                    'text-gray-400 hover:bg-white/[0.03] hover:text-gray-300': modelPreference !== p.id,
                  }
                )}
              >
                <div className="flex flex-col gap-0.5">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[8px] font-mono text-gray-600 uppercase">{p.tag}</span>
                    <span className="text-[11px] font-mono font-semibold">{p.label}</span>
                  </div>
                  <span className="text-[9px] text-gray-600">{p.description}</span>
                </div>
                {modelPreference === p.id && (
                  <div className="w-1.5 h-1.5 rounded-full bg-jarvis-cyan shadow-[0_0_4px_rgba(0,212,255,0.5)]" />
                )}
              </button>
            ))}
          </div>
        )}
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
