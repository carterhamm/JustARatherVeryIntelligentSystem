import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, LogOut, Volume2, VolumeX, Clock, Shield, Loader2 } from 'lucide-react';
import { QRCodeSVG } from 'qrcode.react';
import { useAuth } from '@/hooks/useAuth';
import { useSettingsStore } from '@/stores/settingsStore';
import { useUIStore } from '@/stores/uiStore';
import clsx from 'clsx';

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
  const { user, logout, getTOTPStatus, setupTOTP, enableTOTP, disableTOTP } = useAuth();
  const { voiceEnabled, setVoiceEnabled, use24HourTime, setUse24HourTime, modelPreference } = useSettingsStore();

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

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setIsOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Fetch TOTP status when panel opens
  useEffect(() => {
    if (isOpen && user) {
      getTOTPStatus().then((s) => setTotpEnabled(s.totp_enabled)).catch(() => {});
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

          {/* Centered panel */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            transition={{ type: 'spring', damping: 28, stiffness: 350 }}
            className="fixed inset-0 z-50 flex items-center justify-center pointer-events-none"
          >
            <div className="glass-heavy rounded-3xl w-full max-w-sm mx-4 pointer-events-auto overflow-hidden">
              {/* Header */}
              <div className="flex items-center justify-between px-6 py-4">
                <span className="hud-label text-[10px]">SETTINGS</span>
                <button
                  onClick={handleClose}
                  className="glass-circle w-8 h-8 flex items-center justify-center"
                >
                  <X size={14} className="text-gray-400" />
                </button>
              </div>

              <div className="px-6 pb-6 space-y-5">
                {/* Profile */}
                {user && (
                  <div className="glass-subtle rounded-2xl p-4">
                    <div className="flex items-center gap-3">
                      <div
                        className="w-10 h-10 flex items-center justify-center rounded-full flex-shrink-0"
                        style={{
                          background:
                            'linear-gradient(135deg, rgba(0,212,255,0.15), rgba(0,128,255,0.1))',
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
                    </div>
                    <button
                      onClick={logout}
                      className="mt-3 w-full flex items-center justify-center gap-2 px-4 py-2 text-[10px] font-mono font-medium text-hud-red uppercase tracking-wider rounded-xl border border-hud-red/20 bg-hud-red/5 hover:bg-hud-red/10 transition-all"
                    >
                      <LogOut size={12} />
                      Sign Out
                    </button>
                  </div>
                )}

                {/* Preferences */}
                <div>
                  <span className="hud-label text-[8px] block mb-3">PREFERENCES</span>
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

                {/* Security — TOTP 2FA */}
                <div>
                  <span className="hud-label text-[8px] block mb-3">SECURITY</span>
                  <div className="space-y-2">
                    {totpStep === 'idle' && !totpEnabled && (
                      <button
                        onClick={handleTOTPSetup}
                        className="w-full glass-subtle rounded-xl px-4 py-3 flex items-center justify-between hover:border-jarvis-blue/20 transition-all border border-transparent"
                      >
                        <div className="flex items-center gap-2.5">
                          <Shield size={14} className="text-gray-600" />
                          <div className="text-left">
                            <span className="text-xs text-gray-300">Two-Factor Auth</span>
                            <p className="text-[9px] text-gray-600 font-mono">Disabled</p>
                          </div>
                        </div>
                        <span className="text-[10px] text-jarvis-blue font-mono">ENABLE</span>
                      </button>
                    )}

                    {totpStep === 'idle' && totpEnabled && (
                      <div className="glass-subtle rounded-xl px-4 py-3">
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2.5">
                            <Shield size={14} className="text-hud-green" />
                            <div>
                              <span className="text-xs text-gray-300">Two-Factor Auth</span>
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
                      </div>
                    )}

                    {totpStep === 'loading' && (
                      <div className="glass-subtle rounded-xl px-4 py-6 flex items-center justify-center">
                        <Loader2 size={16} className="animate-spin text-jarvis-blue" />
                      </div>
                    )}

                    {totpStep === 'setup' && (
                      <div className="glass-subtle rounded-xl px-4 py-3 space-y-3">
                        <p className="text-xs text-gray-300 text-center">Scan with your authenticator app</p>
                        <div className="flex justify-center">
                          <div className="bg-white rounded-xl p-3">
                            <QRCodeSVG value={totpUri} size={160} level="M" />
                          </div>
                        </div>
                        <p className="text-[10px] text-gray-500 text-center">Or enter this key manually:</p>
                        <div className="bg-black/40 rounded-lg px-3 py-2 font-mono text-[11px] text-jarvis-blue break-all select-all text-center">
                          {totpSecret}
                        </div>
                        <div>
                          <label className="hud-label text-[7px] block mb-1.5">ENTER CODE TO CONFIRM</label>
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
                        {totpError && (
                          <p className="text-[10px] text-hud-red text-center">{totpError}</p>
                        )}
                        <div className="flex gap-2">
                          <button
                            onClick={() => { setTotpStep('idle'); setTotpError(''); }}
                            className="flex-1 text-[10px] text-gray-500 py-1.5 hover:text-gray-300 transition-colors"
                          >
                            Cancel
                          </button>
                          <button
                            onClick={handleTOTPConfirm}
                            disabled={totpCode.length !== 6 || totpLoading}
                            className="flex-1 text-[10px] font-mono text-jarvis-blue py-1.5 rounded-lg border border-jarvis-blue/20 bg-jarvis-blue/5 hover:bg-jarvis-blue/10 transition-all disabled:opacity-40"
                          >
                            {totpLoading ? 'Verifying...' : 'CONFIRM'}
                          </button>
                        </div>
                      </div>
                    )}

                    {totpStep === 'disabling' && (
                      <div className="glass-subtle rounded-xl px-4 py-3 space-y-3">
                        <p className="text-xs text-gray-300">Enter a code to disable 2FA:</p>
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
                        {totpError && (
                          <p className="text-[10px] text-hud-red text-center">{totpError}</p>
                        )}
                        <div className="flex gap-2">
                          <button
                            onClick={() => { setTotpStep('idle'); setTotpError(''); setTotpCode(''); }}
                            className="flex-1 text-[10px] text-gray-500 py-1.5 hover:text-gray-300 transition-colors"
                          >
                            Cancel
                          </button>
                          <button
                            onClick={handleTOTPDisable}
                            disabled={totpCode.length !== 6 || totpLoading}
                            className="flex-1 text-[10px] font-mono text-hud-red py-1.5 rounded-lg border border-hud-red/20 bg-hud-red/5 hover:bg-hud-red/10 transition-all disabled:opacity-40"
                          >
                            {totpLoading ? 'Disabling...' : 'DISABLE'}
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* System */}
                <div>
                  <span className="hud-label text-[8px] block mb-3">SYSTEM</span>
                  <div className="grid grid-cols-2 gap-2">
                    <InfoCard label="VERSION" value="1.0.0" />
                    <InfoCard label="CONNECTION" value={wsConnected ? 'Online' : 'Offline'} />
                    <InfoCard label="FRONTEND" value="React + TypeScript" />
                    <InfoCard label="BACKEND" value="FastAPI + WebSocket" />
                  </div>
                </div>

                {/* Footer */}
                <div className="text-center pt-1">
                  <p className="text-[9px] text-gray-700 font-mono tracking-wider">
                    STARK INDUSTRIES
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
