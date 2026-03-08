import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, LogOut, Volume2, VolumeX, Clock, Shield, Loader2, Cpu, Settings, Info } from 'lucide-react';
import { QRCodeSVG } from 'qrcode.react';
import { useAuth } from '@/hooks/useAuth';
import { useSettingsStore, type ModelProvider } from '@/stores/settingsStore';
import { useUIStore } from '@/stores/uiStore';
import { api } from '@/services/api';
import clsx from 'clsx';

const MODEL_OPTIONS: { id: ModelProvider; label: string; desc: string; tag: string; color: string }[] = [
  { id: 'claude', label: 'Claude', desc: 'Nuanced reasoning', tag: 'UPLINK', color: '#ff8c00' },
  { id: 'gemini', label: 'Gemini', desc: 'Multimodal Flash', tag: 'UPLINK', color: '#4285F4' },
  { id: 'stark_protocol', label: 'Stark Protocol', desc: 'Self-hosted LLM', tag: 'LOCAL', color: '#00d4ff' },
];

const TABS = [
  { id: 'general', label: 'General', icon: Settings },
  { id: 'model', label: 'Model', icon: Cpu },
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
    <div className="glass-subtle rounded-xl px-4 py-3 flex items-center justify-between">
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
    <div className="glass-subtle rounded-xl px-3 py-2.5">
      <span className="hud-label text-[7px] block mb-0.5">{label}</span>
      <p className="text-[11px] text-gray-300">{value}</p>
    </div>
  );
}

type TOTPStep = 'idle' | 'loading' | 'setup' | 'confirm' | 'disabling';

export default function SettingsPanel() {
  const [isOpen, setIsOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<TabId>('general');
  const { user, logout, getTOTPStatus, setupTOTP, enableTOTP, disableTOTP } = useAuth();
  const { voiceEnabled, setVoiceEnabled, use24HourTime, setUse24HourTime, modelPreference, setModelPreference } = useSettingsStore();
  const [availableModels, setAvailableModels] = useState<Set<string>>(new Set(MODEL_OPTIONS.map((m) => m.id)));

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
        setIsOpen((prev) => !prev);
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

  // Fetch TOTP status + provider availability when panel opens
  useEffect(() => {
    if (isOpen && user) {
      getTOTPStatus().then((s) => setTotpEnabled(s.totp_enabled)).catch(() => {});
      api.get<{ id: string; available: boolean }[]>('/providers')
        .then((data) => setAvailableModels(new Set(data.filter((p) => p.available).map((p) => p.id))))
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
            <div className="glass-heavy rounded-3xl w-full max-w-lg mx-4 pointer-events-auto overflow-hidden">
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
                        'flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl text-[10px] font-mono uppercase tracking-wider transition-all',
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
                      <div className="glass-subtle rounded-2xl p-4">
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
                            className="flex items-center gap-1.5 px-3 py-1.5 text-[9px] font-mono font-medium text-hud-red uppercase tracking-wider rounded-lg border border-hud-red/20 bg-hud-red/5 hover:bg-hud-red/10 transition-all flex-shrink-0"
                          >
                            <LogOut size={10} />
                            Sign Out
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Preferences */}
                    <div className="space-y-2">
                      <ToggleRow
                        icon={voiceEnabled ? Volume2 : VolumeX}
                        label="Voice Responses"
                        sublabel={modelPreference === 'stark_protocol' ? 'JARVIS Voice (Local)' : 'ElevenLabs TTS'}
                        enabled={voiceEnabled}
                        onToggle={() => setVoiceEnabled(!voiceEnabled)}
                      />
                      <ToggleRow
                        icon={Clock}
                        label="24-Hour Clock"
                        enabled={use24HourTime}
                        onToggle={() => setUse24HourTime(!use24HourTime)}
                      />
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
                            'w-full text-left px-4 py-3 rounded-xl transition-all flex items-center justify-between',
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

                {/* ── Security Tab ── */}
                {activeTab === 'security' && (
                  <div className="space-y-3">
                    {totpStep === 'idle' && !totpEnabled && (
                      <button
                        onClick={handleTOTPSetup}
                        className="w-full glass-subtle rounded-xl px-4 py-3 flex items-center justify-between hover:border-jarvis-blue/20 transition-all border border-transparent"
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
                      <div className="glass-subtle rounded-xl px-4 py-3 flex items-center justify-between">
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
                      <div className="glass-subtle rounded-xl px-4 py-8 flex items-center justify-center">
                        <Loader2 size={16} className="animate-spin text-jarvis-blue" />
                      </div>
                    )}

                    {totpStep === 'setup' && (
                      <div className="glass-subtle rounded-xl px-4 py-4 space-y-3">
                        <p className="text-xs text-gray-300 text-center">Scan with your authenticator app</p>
                        <div className="flex justify-center">
                          <div className="bg-white rounded-xl p-3">
                            <QRCodeSVG value={totpUri} size={140} level="M" />
                          </div>
                        </div>
                        <p className="text-[10px] text-gray-500 text-center">Or enter manually:</p>
                        <div className="bg-black/40 rounded-lg px-3 py-2 font-mono text-[10px] text-jarvis-blue break-all select-all text-center">
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
                            className="px-4 py-2 text-[10px] font-mono text-jarvis-blue rounded-xl border border-jarvis-blue/20 bg-jarvis-blue/5 hover:bg-jarvis-blue/10 transition-all disabled:opacity-40"
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
                      <div className="glass-subtle rounded-xl px-4 py-4 space-y-3">
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
                            className="px-4 py-2 text-[10px] font-mono text-hud-red rounded-xl border border-hud-red/20 bg-hud-red/5 hover:bg-hud-red/10 transition-all disabled:opacity-40"
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
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
