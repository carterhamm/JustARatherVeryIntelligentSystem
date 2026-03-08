import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, LogOut, Volume2, VolumeX, Clock } from 'lucide-react';
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
          className={clsx('absolute top-1 w-4 h-4 rounded-full transition-all', {
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

export default function SettingsPanel() {
  const [isOpen, setIsOpen] = useState(false);
  const { user, logout } = useAuth();
  const { voiceEnabled, setVoiceEnabled, use24HourTime, setUse24HourTime, modelPreference } = useSettingsStore();
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
                          {user.username?.charAt(0).toUpperCase() || 'U'}
                        </span>
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-200 truncate">
                          {user.username}
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
