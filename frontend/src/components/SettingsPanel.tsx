import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, LogOut, Volume2, VolumeX, Clock, Shield, Loader2, Cpu, Settings, Info, Link2, ExternalLink, Check } from 'lucide-react';
import { QRCodeSVG } from 'qrcode.react';
import { useAuth } from '@/hooks/useAuth';
import { useSettingsStore, type ModelProvider } from '@/stores/settingsStore';
import { useUIStore, usePanelOverlay } from '@/stores/uiStore';
import { api } from '@/services/api';
import clsx from 'clsx';

const _PANEL_CLIP = 'polygon(10px 0, calc(50% - 70px) 0, calc(50% - 56px) 5px, calc(50% + 56px) 5px, calc(50% + 70px) 0, calc(100% - 10px) 0, 100% 10px, 100% calc(100% - 10px), calc(100% - 10px) 100%, 10px 100%, 0 calc(100% - 10px), 0 10px)';

const MODEL_OPTIONS: { id: ModelProvider; label: string; desc: string; tag: string; color: string }[] = [
  { id: 'claude', label: 'Claude', desc: 'Nuanced reasoning', tag: 'UPLINK', color: '#ff8c00' },
  { id: 'gemini', label: 'Gemini', desc: 'Multimodal Flash', tag: 'UPLINK', color: '#4285F4' },
  { id: 'stark_protocol', label: 'Stark Protocol', desc: 'Self-hosted LLM', tag: 'LOCAL', color: '#00d4ff' },
];

const TABS = [
  { id: 'general', label: 'General', icon: Settings },
  { id: 'model', label: 'Model', icon: Cpu },
  { id: 'connections', label: 'Links', icon: Link2 },
  { id: 'security', label: 'Security', icon: Shield },
  { id: 'system', label: 'System', icon: Info },
] as const;

type TabId = typeof TABS[number]['id'];

function ToggleRow({
  icon: Icon,
  label,
  sublabel,
  enabled,
  onToggle,
}: {
  icon: React.ElementType;
  label: string;
  sublabel?: string;
  enabled: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="glass-subtle hud-clip-sm px-4 py-3 flex items-center justify-between">
      <div className="flex items-center gap-2.5">
        <Icon size={14} className={enabled ? 'text-jarvis-gold' : 'text-gray-600'} />
        <div>
          <span className="text-xs text-gray-300">{label}</span>
          {sublabel && <p className="text-[9px] text-gray-600 font-mono">{sublabel}</p>}
        </div>
      </div>
      <button
        onClick={onToggle}
        className={clsx('relative w-10 h-6 rounded-full transition-colors', {
          'bg-jarvis-blue/20 border border-jarvis-blue/30': enabled,
          'bg-gray-800 border border-gray-700': !enabled,
        })}
      >
        <div
          className={clsx('absolute top-1/2 -translate-y-1/2 w-4 h-4 rounded-full transition-all', {
            'bg-jarvis-blue left-5': enabled,
            'bg-gray-600 left-1': !enabled,
          })}
        />
      </button>
    </div>
  );
}

function InfoCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="glass-subtle hud-clip-sm px-3 py-2.5">
      <span className="hud-label text-[7px] block mb-0.5">{label}</span>
      <p className="text-[11px] text-gray-300">{value}</p>
    </div>
  );
}

type TOTPStep = 'idle' | 'loading' | 'setup' | 'confirm' | 'disabling';

export default function SettingsPanel() {
  const { isOpen: isOpenOverlay, toggle: toggleOverlay, close: closeOverlay } = usePanelOverlay('settings', 'panel');
  const isOpen = isOpenOverlay;
  const setIsOpen = (open: boolean) => { if (open) toggleOverlay(); else closeOverlay(); };
  const [activeTab, setActiveTab] = useState<TabId>('general');
  const { user, logout, getTOTPStatus, setupTOTP, enableTOTP, disableTOTP } = useAuth();
  const { voiceEnabled, setVoiceEnabled, use24HourTime, setUse24HourTime, modelPreference, setModelPreference } = useSettingsStore();
  const [availableModels, setAvailableModels] = useState<Set<string>>(new Set(MODEL_OPTIONS.map((m) => m.id)));

  // Google connection state
  const [googleConnected, setGoogleConnected] = useState(false);

  // TOTP state
  const [totpEnabled, setTotpEnabled] = useState(false);
  const [totpStep, setTotpStep] = useState<TOTPStep>('idle');
  const [totpSecret, setTotpSecret] = useState('');
  const [totpUri, setTotpUri] = useState('');
  const [totpCode, setTotpCode] = useState('');
  const [totpError, setTotpError] = useState('');
  const [totpLoading, setTotpLoading] = useState(false);
  const wsConnected = useUIStore((s) => s.wsConnected);

  useEffect(() => {
    const handler = (e: Event) => {
      const customEvent = e as CustomEvent<{ open?: boolean }>;
      if (customEvent.detail?.open !== undefined) {
        setIsOpen(customEvent.detail.open);
      } else {
        toggleOverlay();
      }
    };
    window.addEventListener('jarvis-settings-toggle', handler);
    return () => window.removeEventListener('jarvis-settings-toggle', handler);
  }, []);

  const handleClose = useCallback(() => setIsOpen(false), []);

  // Keyboard: Escape to close, Tab to cycle tabs
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsOpen(false);
        return;
      }
      if (e.key === 'Tab') {
        e.preventDefault();
        setActiveTab((prev) => {
          const idx = TABS.findIndex((t) => t.id === prev);
          const next = e.shiftKey
            ? (idx - 1 + TABS.length) % TABS.length
            : (idx + 1) % TABS.length;
          return TABS[next].id;
        });
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen]);

  // Fetch TOTP status, provider availability, and Google status when panel opens
  useEffect(() => {
    if (isOpen && user) {
      getTOTPStatus().then((s) => setTotpEnabled(s.totp_enabled)).catch(() => {});
      api.get<{ id: string; available: boolean }[]>('/providers')
        .then((data) => setAvailableModels(new Set(data.filter((p) => p.available).map((p) => p.id))))
        .catch(() => {});
      api.get<{ connected: boolean }>('/google/status')
        .then((data) => setGoogleConnected(data.connected))
        .catch(() => {});
    }
  }, [isOpen, user, getTOTPStatus]);

  const handleTOTPSetup = async () => {
    setTotpStep('loading');
    setTotpError('');
    try {
      const { secret, otpauth_uri } = await setupTOTP();
      setTotpSecret(secret);
      setTotpUri(otpauth_uri);
      setTotpCode('');
      setTotpStep('setup');
    } catch {
      setTotpError('Failed to start TOTP setup.');
      setTotpStep('idle');
    }
  };

  const handleTOTPConfirm = async () => {
    if (totpCode.length !== 6) return;
    setTotpLoading(true);
    setTotpError('');
    try {
      await enableTOTP(totpCode, totpSecret);
      setTotpEnabled(true);
      setTotpStep('idle');
      setTotpSecret('');
      setTotpUri('');
      setTotpCode('');
    } catch (err: any) {
      setTotpError(err?.message || 'Invalid code.');
      setTotpCode('');
    } finally {
      setTotpLoading(false);
    }
  };

  const handleTOTPDisable = async () => {
    if (totpCode.length !== 6) return;
    setTotpLoading(true);
    setTotpError('');
    try {
      await disableTOTP(totpCode);
      setTotpEnabled(false);
      setTotpStep('idle');
      setTotpCode('');
    } catch (err: any) {
      setTotpError(err?.message || 'Invalid code.');
      setTotpCode('');
    } finally {
      setTotpLoading(false);
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="fixed inset-0 z-40 panel-backdrop"
            onClick={handleClose}
          />

          {/* Centered panel — wider, shorter */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            transition={{ type: 'spring', damping: 28, stiffness: 350 }}
            className="fixed inset-0 z-50 flex items-center justify-center pointer-events-none"
          >
            <div className="relative w-full max-w-lg mx-4 pointer-events-auto">
              {/* Beam border layer */}
              <div className="absolute -inset-px pointer-events-none hud-beam-border" style={{
                clipPath: _PANEL_CLIP,
              }} />
              {/* Static border layer (faint) */}
              <div className="absolute -inset-px pointer-events-none" style={{
                background: 'rgba(0, 212, 255, 0.08)',
                clipPath: _PANEL_CLIP,
              }} />
              {/* Content */}
              <div className="relative" style={{
                background: 'rgba(6, 8, 20, 0.92)',
                backdropFilter: 'blur(32px) saturate(1.4)',
                WebkitBackdropFilter: 'blur(32px) saturate(1.4)',
                clipPath: _PANEL_CLIP,
                boxShadow: '0 0 40px rgba(0, 0, 0, 0.5)',
              }}>
              {/* Header + Tabs */}
              <div className="flex items-center justify-between px-6 pt-4 pb-0">
                <span className="hud-label text-[10px]">SETTINGS</span>
                <button
                  onClick={handleClose}
                  className="glass-circle w-8 h-8 flex items-center justify-center"
                >
                  <X size={14} className="text-gray-400" />
                </button>
              </div>

              {/* Tab bar */}
              <div className="flex gap-1 px-5 pt-3 pb-1">
                {TABS.map((tab) => {
                  const Icon = tab.icon;
                  const isActive = activeTab === tab.id;
                  return (
                    <button
                      key={tab.id}
                      onClick={() => setActiveTab(tab.id)}
                      className={clsx(
                        'flex-1 flex items-center justify-center gap-1.5 px-3 py-2 hud-clip-sm text-[10px] font-mono uppercase tracking-wider transition-all',
                        isActive
                          ? 'bg-jarvis-blue/10 border border-jarvis-blue/20 text-jarvis-blue'
                          : 'border border-transparent text-gray-600 hover:text-gray-400 hover:bg-white/[0.02]',
                      )}
                    >
                      <Icon size={12} />
                      {tab.label}
                    </button>
                  );
                })}
              </div>

              {/* Tab content */}
              <div className="px-6 pb-5 pt-3 min-h-[220px]">

                {/* ── General Tab ── */}
                {activeTab === 'general' && (
                  <div className="space-y-4">
                    {/* Profile */}
                    {user && (
                      <div className="glass-subtle hud-clip-md p-4">
                        <div className="flex items-center gap-3">
                          <div
                            className="w-10 h-10 flex items-center justify-center rounded-full flex-shrink-0"
                            style={{
                              background: 'linear-gradient(135deg, rgba(0,212,255,0.15), rgba(0,128,255,0.1))',
                              border: '1px solid rgba(0,212,255,0.2)',
                            }}
                          >
                            <span className="text-sm font-display font-bold text-jarvis-blue">
                              {(user.full_name || user.username)?.charAt(0).toUpperCase() || 'U'}
                            </span>
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-gray-200 truncate">
                              {user.full_name || user.username}
                            </p>
                            <p className="text-[10px] text-gray-500 font-mono truncate">{user.email}</p>
                          </div>
                          <button
                            onClick={logout}
                            className="flex items-center gap-1.5 px-3 py-1.5 text-[9px] font-mono font-medium text-hud-red uppercase tracking-wider hud-clip-sm border border-hud-red/20 bg-hud-red/5 hover:bg-hud-red/10 transition-all flex-shrink-0"
                          >
                            <LogOut size={10} />
                            Sign Out
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Preferences */}
                    <div className="grid grid-cols-2 gap-2">
                      <button
                        onClick={() => setVoiceEnabled(!voiceEnabled)}
                        className="glass-subtle hud-clip-sm px-3 py-3 text-left"
                      >
                        <div className="flex items-center justify-between mb-2">
                          {voiceEnabled ? <Volume2 size={14} className="text-jarvis-gold" /> : <VolumeX size={14} className="text-gray-600" />}
                          <div className={clsx('relative w-8 h-[18px] rounded-full transition-colors', {
                            'bg-jarvis-blue/20 border border-jarvis-blue/30': voiceEnabled,
                            'bg-gray-800 border border-gray-700': !voiceEnabled,
                          })}>
                            <div className={clsx('absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full transition-all', {
                              'bg-jarvis-blue left-[14px]': voiceEnabled,
                              'bg-gray-600 left-0.5': !voiceEnabled,
                            })} />
                          </div>
                        </div>
                        <span className="text-[11px] text-gray-300 block leading-tight">Voice Responses</span>
                        <span className="text-[9px] text-gray-600 font-mono">
                          {modelPreference === 'stark_protocol' ? 'Local TTS' : 'ElevenLabs'}
                        </span>
                      </button>
                      <button
                        onClick={() => setUse24HourTime(!use24HourTime)}
                        className="glass-subtle hud-clip-sm px-3 py-3 text-left"
                      >
                        <div className="flex items-center justify-between mb-2">
                          <Clock size={14} className={use24HourTime ? 'text-jarvis-gold' : 'text-gray-600'} />
                          <div className={clsx('relative w-8 h-[18px] rounded-full transition-colors', {
                            'bg-jarvis-blue/20 border border-jarvis-blue/30': use24HourTime,
                            'bg-gray-800 border border-gray-700': !use24HourTime,
                          })}>
                            <div className={clsx('absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full transition-all', {
                              'bg-jarvis-blue left-[14px]': use24HourTime,
                              'bg-gray-600 left-0.5': !use24HourTime,
                            })} />
                          </div>
                        </div>
                        <span className="text-[11px] text-gray-300 block leading-tight">24-Hour Clock</span>
                        <span className="text-[9px] text-gray-600 font-mono">Time format</span>
                      </button>
                    </div>
                  </div>
                )}

                {/* ── Model Tab ── */}
                {activeTab === 'model' && (
                  <div className="space-y-1.5">
                    {MODEL_OPTIONS.map((m) => {
                      const isAvail = availableModels.has(m.id);
                      const isSelected = modelPreference === m.id;
                      return (
                        <button
                          key={m.id}
                          disabled={!isAvail}
                          onClick={() => isAvail && setModelPreference(m.id)}
                          className={clsx(
                            'w-full text-left px-4 py-3 hud-clip-sm transition-all flex items-center justify-between',
                            isSelected
                              ? 'glass-subtle border border-white/[0.08]'
                              : 'border border-transparent hover:bg-white/[0.03]',
                            !isAvail && 'opacity-30 cursor-not-allowed',
                          )}
                        >
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="text-[7px] font-mono text-gray-600 uppercase">{m.tag}</span>
                              <span className={clsx('text-xs font-semibold', isSelected ? 'text-white' : 'text-gray-400')}>
                                {m.label}
                              </span>
                            </div>
                            <p className="text-[9px] text-gray-600 font-mono mt-0.5">{m.desc}</p>
                          </div>
                          {isSelected && isAvail && (
                            <div
                              className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                              style={{ backgroundColor: m.color, boxShadow: `0 0 8px ${m.color}66` }}
                            />
                          )}
                        </button>
                      );
                    })}
                  </div>
                )}

                {/* ── Connections Tab ── */}
                {activeTab === 'connections' && (
                  <div className="space-y-2">
                    {/* Google */}
                    <div className="glass-subtle hud-clip-sm px-4 py-3 flex items-center justify-between">
                      <div className="flex items-center gap-2.5">
                        <div className="w-8 h-8 hud-clip-sm flex items-center justify-center bg-white/[0.04] border border-white/[0.06]">
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                            <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/>
                            <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                            <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                            <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
                          </svg>
                        </div>
                        <div>
                          <p className="text-xs text-gray-300">Google Workspace</p>
                          <p className="text-[9px] text-gray-600 font-mono">
                            {googleConnected ? 'Gmail, Calendar, Drive connected' : 'Gmail, Calendar, Drive'}
                          </p>
                        </div>
                      </div>
                      {googleConnected ? (
                        <div className="flex items-center gap-1.5">
                          <Check size={10} className="text-hud-green" />
                          <span className="text-[10px] text-hud-green font-mono">LINKED</span>
                        </div>
                      ) : (
                        <a
                          href="/connect/google"
                          className="flex items-center gap-1 px-3 py-1.5 text-[9px] font-mono font-medium text-jarvis-blue uppercase tracking-wider hud-clip-sm border border-jarvis-blue/20 bg-jarvis-blue/5 hover:bg-jarvis-blue/10 transition-all"
                        >
                          Connect <ExternalLink size={8} />
                        </a>
                      )}
                    </div>

                    {/* Placeholder for future connections */}
                    <div className="glass-subtle hud-clip-sm px-4 py-3 flex items-center justify-between opacity-40">
                      <div className="flex items-center gap-2.5">
                        <div className="w-8 h-8 hud-clip-sm flex items-center justify-center bg-white/[0.04] border border-white/[0.06]">
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                            <path d="M23.643 4.937c-.835.37-1.732.62-2.675.733.962-.576 1.7-1.49 2.048-2.578-.9.534-1.897.922-2.958 1.13-.85-.904-2.06-1.47-3.4-1.47-2.572 0-4.658 2.086-4.658 4.66 0 .364.042.718.12 1.06-3.873-.195-7.304-2.05-9.602-4.868-.4.69-.63 1.49-.63 2.342 0 1.616.823 3.043 2.072 3.878-.764-.025-1.482-.234-2.11-.583v.06c0 2.257 1.605 4.14 3.737 4.568-.392.106-.803.162-1.227.162-.3 0-.593-.028-.877-.082.593 1.85 2.313 3.198 4.352 3.234-1.595 1.25-3.604 1.995-5.786 1.995-.376 0-.747-.022-1.112-.065 2.062 1.323 4.51 2.093 7.14 2.093 8.57 0 13.255-7.098 13.255-13.254 0-.2-.005-.402-.014-.602.91-.658 1.7-1.477 2.323-2.41z" fill="#666"/>
                          </svg>
                        </div>
                        <div>
                          <p className="text-xs text-gray-500">X (Twitter)</p>
                          <p className="text-[9px] text-gray-700 font-mono">Coming soon</p>
                        </div>
                      </div>
                      <span className="text-[10px] text-gray-700 font-mono">SOON</span>
                    </div>
                  </div>
                )}

                {/* ── Security Tab ── */}
                {activeTab === 'security' && (
                  <div className="space-y-3">
                    {totpStep === 'idle' && !totpEnabled && (
                      <button
                        onClick={handleTOTPSetup}
                        className="w-full glass-subtle hud-clip-sm px-4 py-3 flex items-center justify-between hover:border-jarvis-blue/20 transition-all border border-transparent"
                      >
                        <div className="flex items-center gap-2.5">
                          <Shield size={14} className="text-gray-600" />
                          <div className="text-left">
                            <span className="text-xs text-gray-300">Two-Factor Authentication</span>
                            <p className="text-[9px] text-gray-600 font-mono">Disabled — tap to enable</p>
                          </div>
                        </div>
                        <span className="text-[10px] text-jarvis-blue font-mono">ENABLE</span>
                      </button>
                    )}

                    {totpStep === 'idle' && totpEnabled && (
                      <div className="glass-subtle hud-clip-sm px-4 py-3 flex items-center justify-between">
                        <div className="flex items-center gap-2.5">
                          <Shield size={14} className="text-hud-green" />
                          <div>
                            <span className="text-xs text-gray-300">Two-Factor Authentication</span>
                            <p className="text-[9px] text-hud-green font-mono">Enabled</p>
                          </div>
                        </div>
                        <button
                          onClick={() => { setTotpStep('disabling'); setTotpCode(''); setTotpError(''); }}
                          className="text-[10px] text-hud-red font-mono"
                        >
                          DISABLE
                        </button>
                      </div>
                    )}

                    {totpStep === 'loading' && (
                      <div className="glass-subtle hud-clip-sm px-4 py-8 flex items-center justify-center">
                        <Loader2 size={16} className="animate-spin text-jarvis-blue" />
                      </div>
                    )}

                    {totpStep === 'setup' && (
                      <div className="glass-subtle hud-clip-sm px-4 py-4 space-y-3">
                        <p className="text-xs text-gray-300 text-center">Scan with your authenticator app</p>
                        <div className="flex justify-center">
                          <div className="bg-white hud-clip-sm p-3">
                            <QRCodeSVG value={totpUri} size={140} level="M" />
                          </div>
                        </div>
                        <p className="text-[10px] text-gray-500 text-center">Or enter manually:</p>
                        <div className="bg-black/40 hud-clip-sm px-3 py-2 font-mono text-[10px] text-jarvis-blue break-all select-all text-center">
                          {totpSecret}
                        </div>
                        <div className="flex items-end gap-2">
                          <div className="flex-1">
                            <label className="hud-label text-[7px] block mb-1.5">VERIFICATION CODE</label>
                            <input
                              type="text"
                              inputMode="numeric"
                              maxLength={6}
                              value={totpCode}
                              onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                              placeholder="000000"
                              className="w-full jarvis-input px-3 py-2 text-center text-sm font-mono tracking-[0.4em]"
                              autoFocus
                            />
                          </div>
                          <button
                            onClick={handleTOTPConfirm}
                            disabled={totpCode.length !== 6 || totpLoading}
                            className="px-4 py-2 text-[10px] font-mono text-jarvis-blue hud-clip-sm border border-jarvis-blue/20 bg-jarvis-blue/5 hover:bg-jarvis-blue/10 transition-all disabled:opacity-40"
                          >
                            {totpLoading ? '...' : 'CONFIRM'}
                          </button>
                        </div>
                        {totpError && (
                          <p className="text-[10px] text-hud-red text-center">{totpError}</p>
                        )}
                        <button
                          onClick={() => { setTotpStep('idle'); setTotpError(''); }}
                          className="w-full text-[10px] text-gray-500 hover:text-gray-300 transition-colors"
                        >
                          Cancel
                        </button>
                      </div>
                    )}

                    {totpStep === 'disabling' && (
                      <div className="glass-subtle hud-clip-sm px-4 py-4 space-y-3">
                        <p className="text-xs text-gray-300">Enter a code to disable 2FA:</p>
                        <div className="flex items-end gap-2">
                          <input
                            type="text"
                            inputMode="numeric"
                            maxLength={6}
                            value={totpCode}
                            onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                            placeholder="000000"
                            className="flex-1 jarvis-input px-3 py-2 text-center text-sm font-mono tracking-[0.4em]"
                            autoFocus
                          />
                          <button
                            onClick={handleTOTPDisable}
                            disabled={totpCode.length !== 6 || totpLoading}
                            className="px-4 py-2 text-[10px] font-mono text-hud-red hud-clip-sm border border-hud-red/20 bg-hud-red/5 hover:bg-hud-red/10 transition-all disabled:opacity-40"
                          >
                            {totpLoading ? '...' : 'DISABLE'}
                          </button>
                        </div>
                        {totpError && (
                          <p className="text-[10px] text-hud-red text-center">{totpError}</p>
                        )}
                        <button
                          onClick={() => { setTotpStep('idle'); setTotpError(''); setTotpCode(''); }}
                          className="w-full text-[10px] text-gray-500 hover:text-gray-300 transition-colors"
                        >
                          Cancel
                        </button>
                      </div>
                    )}
                  </div>
                )}

                {/* ── System Tab ── */}
                {activeTab === 'system' && (
                  <div className="space-y-3">
                    <div className="grid grid-cols-2 gap-2">
                      <InfoCard label="VERSION" value="1.0.0" />
                      <InfoCard label="CONNECTION" value={wsConnected ? 'Online' : 'Offline'} />
                      <InfoCard label="FRONTEND" value="React + TypeScript" />
                      <InfoCard label="BACKEND" value="FastAPI + WebSocket" />
                    </div>
                    <div className="text-center pt-1">
                      <p className="text-[9px] text-gray-700 font-mono tracking-wider">
                        STARK INDUSTRIES
                      </p>
                    </div>
                  </div>
                )}
              </div>

              {/* Tab hint */}
              <div className="px-6 pb-3">
                <p className="text-[8px] text-gray-700 font-mono text-center tracking-wider">
                  Press TAB to cycle sections
                </p>
              </div>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
