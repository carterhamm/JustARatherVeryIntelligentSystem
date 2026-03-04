import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, User, Mic, Key, Info, LogOut, Volume2, VolumeX, Cpu } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { useSettingsStore } from '@/stores/settingsStore';
import ModelPicker from '@/components/ModelPicker';
import clsx from 'clsx';

type SettingsSection = 'profile' | 'model' | 'voice' | 'api-keys' | 'about';

const sections: { id: SettingsSection; label: string; icon: React.ReactNode }[] = [
  { id: 'profile', label: 'Profile', icon: <User size={13} /> },
  { id: 'model', label: 'Model', icon: <Cpu size={13} /> },
  { id: 'voice', label: 'Voice', icon: <Mic size={13} /> },
  { id: 'api-keys', label: 'Services', icon: <Key size={13} /> },
  { id: 'about', label: 'About', icon: <Info size={13} /> },
];

function ProfileSection() {
  const { user, logout } = useAuth();

  return (
    <div className="space-y-4">
      <span className="hud-label text-[9px] block">USER PROFILE</span>

      {user ? (
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <div
              className="w-10 h-10 flex items-center justify-center rounded-2xl"
              style={{
                background: 'linear-gradient(135deg, rgba(0, 212, 255, 0.15), rgba(0, 128, 255, 0.1))',
                border: '1px solid rgba(0, 212, 255, 0.2)',
              }}
            >
              <span className="text-sm font-display font-bold text-jarvis-blue">
                {user.username?.charAt(0).toUpperCase() || 'U'}
              </span>
            </div>
            <div>
              <p className="text-sm font-medium text-gray-200">{user.username}</p>
              <p className="text-[10px] text-gray-500 font-mono">{user.email}</p>
            </div>
          </div>

          <div className="glass-subtle rounded-xl px-4 py-2.5">
            <span className="hud-label text-[8px] block mb-0.5">USER ID</span>
            <p className="text-[10px] text-gray-400 font-mono truncate">{user.id}</p>
          </div>

          <button
            onClick={logout}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 text-xs font-medium text-hud-red rounded-xl border border-hud-red/20 bg-hud-red/5 hover:bg-hud-red/10 transition-all"
          >
            <LogOut size={13} />
            SIGN OUT
          </button>
        </div>
      ) : (
        <p className="text-xs text-gray-500">Not authenticated.</p>
      )}
    </div>
  );
}

function VoiceSection() {
  const { voiceEnabled, setVoiceEnabled } = useSettingsStore();

  return (
    <div className="space-y-4">
      <span className="hud-label text-[9px] block">VOICE CONFIGURATION</span>

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {voiceEnabled ? (
            <Volume2 size={13} className="text-jarvis-gold" />
          ) : (
            <VolumeX size={13} className="text-gray-600" />
          )}
          <span className="text-xs text-gray-300">Voice Responses</span>
        </div>
        <button
          onClick={() => setVoiceEnabled(!voiceEnabled)}
          className={clsx('relative w-10 h-6 rounded-full transition-colors', {
            'bg-jarvis-blue/20 border border-jarvis-blue/30': voiceEnabled,
            'bg-gray-800 border border-gray-700': !voiceEnabled,
          })}
        >
          <div
            className={clsx('absolute top-1 w-4 h-4 rounded-full transition-all', {
              'bg-jarvis-blue left-5': voiceEnabled,
              'bg-gray-600 left-1': !voiceEnabled,
            })}
          />
        </button>
      </div>

      <p className="text-[10px] text-gray-600 leading-relaxed font-mono">
        UPLINK MODE ONLY. POWERED BY ELEVENLABS.
      </p>
    </div>
  );
}

function ModelSection() {
  return (
    <div className="space-y-4">
      <span className="hud-label text-[9px] block">AI MODEL SELECTION</span>
      <p className="text-[10px] text-gray-600 leading-relaxed font-mono">
        SELECT PRIMARY MODEL. ALL MODELS HAVE FULL FEATURE PARITY.
      </p>
      <ModelPicker />
    </div>
  );
}

function ApiKeysSection() {
  const services = [
    { name: 'OpenAI', status: 'connected', key: 'sk-...configured' },
    { name: 'Whisper STT', status: 'connected', key: 'Built-in' },
    { name: 'TTS Engine', status: 'connected', key: 'JARVIS Voice' },
    { name: 'WebSocket', status: 'active', key: 'Real-time' },
  ];

  return (
    <div className="space-y-4">
      <span className="hud-label text-[9px] block">CONNECTED SERVICES</span>

      <div className="space-y-1.5">
        {services.map((service) => (
          <div
            key={service.name}
            className="glass-subtle rounded-xl px-4 py-2.5 flex items-center justify-between"
          >
            <div>
              <p className="text-xs text-gray-300">{service.name}</p>
              <p className="text-[9px] text-gray-600 font-mono">{service.key}</p>
            </div>
            <div className="flex items-center gap-1.5">
              <div
                className="status-dot online"
                style={{ width: 5, height: 5 }}
              />
              <span className="text-[9px] text-gray-600 uppercase font-mono">{service.status}</span>
            </div>
          </div>
        ))}
      </div>

      <p className="text-[9px] text-gray-700 leading-relaxed font-mono">
        API KEYS MANAGED SERVER-SIDE.
      </p>
    </div>
  );
}

function AboutSection() {
  return (
    <div className="space-y-4">
      <span className="hud-label text-[9px] block">SYSTEM INFORMATION</span>

      <div className="space-y-1.5">
        {[
          { label: 'VERSION', value: '1.0.0' },
          { label: 'DESIGNATION', value: 'Just A Rather Very Intelligent System' },
          { label: 'FRONTEND', value: 'React + TypeScript' },
          { label: 'BACKEND', value: 'FastAPI + WebSocket' },
        ].map((item) => (
          <div key={item.label} className="glass-subtle rounded-xl px-4 py-2.5">
            <span className="hud-label text-[8px] block mb-0.5">{item.label}</span>
            <p className="text-xs text-gray-300">{item.value}</p>
          </div>
        ))}
      </div>

      <div className="text-center pt-2">
        <div className="hud-divider mb-2">
          <div className="hud-divider-dot" />
        </div>
        <p className="text-[9px] text-gray-700 font-mono">STARK INDUSTRIES</p>
      </div>
    </div>
  );
}

export default function SettingsPanel() {
  const [isOpen, setIsOpen] = useState(false);
  const [activeSection, setActiveSection] = useState<SettingsSection>('profile');

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

  const handleClose = useCallback(() => {
    setIsOpen(false);
  }, []);

  const renderSection = () => {
    switch (activeSection) {
      case 'profile':
        return <ProfileSection />;
      case 'model':
        return <ModelSection />;
      case 'voice':
        return <VoiceSection />;
      case 'api-keys':
        return <ApiKeysSection />;
      case 'about':
        return <AboutSection />;
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-40 panel-backdrop"
            onClick={handleClose}
          />

          <motion.div
            initial={{ opacity: 0, x: 40, scale: 0.97 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: 40, scale: 0.97 }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
            className="fixed right-5 top-5 bottom-5 w-full max-w-sm z-50 glass-heavy rounded-3xl flex flex-col overflow-hidden"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.05]">
              <span className="hud-label text-[10px]">SETTINGS</span>
              <button
                onClick={handleClose}
                className="glass-circle w-8 h-8 flex items-center justify-center"
              >
                <X size={14} className="text-gray-400" />
              </button>
            </div>

            {/* Tabs */}
            <div className="flex border-b border-white/[0.05] px-2 gap-0.5">
              {sections.map((section) => (
                <button
                  key={section.id}
                  onClick={() => setActiveSection(section.id)}
                  className={clsx(
                    'flex items-center gap-1.5 px-3 py-2.5 text-[10px] font-medium transition-all rounded-t-lg border-b-2 -mb-px',
                    {
                      'border-jarvis-blue text-jarvis-blue bg-jarvis-blue/[0.05]':
                        activeSection === section.id,
                      'border-transparent text-gray-600 hover:text-gray-400':
                        activeSection !== section.id,
                    },
                  )}
                >
                  {section.icon}
                  <span className="hidden sm:inline">{section.label}</span>
                </button>
              ))}
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-5">{renderSection()}</div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
