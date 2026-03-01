import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, User, Mic, Key, Info, LogOut, Volume2, VolumeX } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { useUIStore } from '@/stores/uiStore';
import clsx from 'clsx';

type SettingsSection = 'profile' | 'voice' | 'api-keys' | 'about';

const sections: { id: SettingsSection; label: string; icon: React.ReactNode }[] = [
  { id: 'profile', label: 'Profile', icon: <User size={15} /> },
  { id: 'voice', label: 'Voice', icon: <Mic size={15} /> },
  { id: 'api-keys', label: 'API Keys', icon: <Key size={15} /> },
  { id: 'about', label: 'About', icon: <Info size={15} /> },
];

function ProfileSection() {
  const { user, logout } = useAuth();

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-display font-semibold tracking-wider text-jarvis-blue">
        Profile
      </h3>

      {user ? (
        <div className="space-y-3">
          {/* Avatar */}
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-full bg-gradient-to-br from-jarvis-blue/20 to-jarvis-cyan/10 border border-jarvis-blue/30 flex items-center justify-center">
              <span className="text-lg font-display font-bold text-jarvis-blue">
                {user.username?.charAt(0).toUpperCase() || 'U'}
              </span>
            </div>
            <div>
              <p className="text-sm font-medium text-gray-200">{user.username}</p>
              <p className="text-xs text-gray-500">{user.email}</p>
            </div>
          </div>

          {/* User ID */}
          <div className="glass-panel rounded-lg px-3 py-2">
            <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-0.5">User ID</p>
            <p className="text-xs text-gray-400 font-mono truncate">{user.id}</p>
          </div>

          {/* Logout */}
          <button
            onClick={logout}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm hover:bg-red-500/20 transition-all"
          >
            <LogOut size={15} />
            Sign Out
          </button>
        </div>
      ) : (
        <p className="text-sm text-gray-500">Not logged in.</p>
      )}
    </div>
  );
}

function VoiceSection() {
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [selectedVoice, setSelectedVoice] = useState('jarvis-default');

  const voices = [
    { id: 'jarvis-default', name: 'J.A.R.V.I.S. Classic' },
    { id: 'jarvis-formal', name: 'J.A.R.V.I.S. Formal' },
    { id: 'jarvis-casual', name: 'J.A.R.V.I.S. Casual' },
  ];

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-display font-semibold tracking-wider text-jarvis-blue">
        Voice Settings
      </h3>

      {/* Toggle voice mode */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {voiceEnabled ? (
            <Volume2 size={15} className="text-jarvis-blue" />
          ) : (
            <VolumeX size={15} className="text-gray-500" />
          )}
          <span className="text-sm text-gray-300">Voice Responses</span>
        </div>
        <button
          onClick={() => setVoiceEnabled(!voiceEnabled)}
          className={clsx(
            'relative w-10 h-5 rounded-full transition-colors',
            {
              'bg-jarvis-blue/30': voiceEnabled,
              'bg-gray-700': !voiceEnabled,
            }
          )}
        >
          <div
            className={clsx(
              'absolute top-0.5 w-4 h-4 rounded-full transition-all',
              {
                'left-5.5 bg-jarvis-blue': voiceEnabled,
                'left-0.5 bg-gray-500': !voiceEnabled,
              }
            )}
            style={{ left: voiceEnabled ? '22px' : '2px' }}
          />
        </button>
      </div>

      {/* Voice selection */}
      <div>
        <label className="block text-xs text-gray-500 uppercase tracking-wider mb-2">
          Voice Style
        </label>
        <div className="space-y-1.5">
          {voices.map((voice) => (
            <button
              key={voice.id}
              onClick={() => setSelectedVoice(voice.id)}
              className={clsx(
                'w-full text-left px-3 py-2 rounded-lg text-sm transition-all',
                {
                  'bg-jarvis-blue/10 border border-jarvis-blue/20 text-jarvis-blue':
                    selectedVoice === voice.id,
                  'bg-transparent border border-transparent text-gray-400 hover:bg-white/[0.03]':
                    selectedVoice !== voice.id,
                }
              )}
            >
              {voice.name}
            </button>
          ))}
        </div>
      </div>
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
      <h3 className="text-sm font-display font-semibold tracking-wider text-jarvis-blue">
        Connected Services
      </h3>

      <div className="space-y-2">
        {services.map((service) => (
          <div
            key={service.name}
            className="glass-panel rounded-lg px-3 py-2.5 flex items-center justify-between"
          >
            <div>
              <p className="text-sm text-gray-300">{service.name}</p>
              <p className="text-[10px] text-gray-600 font-mono">{service.key}</p>
            </div>
            <div className="flex items-center gap-1.5">
              <div
                className={clsx('w-1.5 h-1.5 rounded-full', {
                  'bg-green-400': service.status === 'connected' || service.status === 'active',
                  'bg-yellow-400': service.status === 'partial',
                  'bg-red-400': service.status === 'disconnected',
                })}
              />
              <span className="text-[10px] text-gray-500 capitalize">{service.status}</span>
            </div>
          </div>
        ))}
      </div>

      <p className="text-[10px] text-gray-600 leading-relaxed">
        API keys and service connections are managed server-side. Contact your administrator to modify integrations.
      </p>
    </div>
  );
}

function AboutSection() {
  return (
    <div className="space-y-4">
      <h3 className="text-sm font-display font-semibold tracking-wider text-jarvis-blue">
        About J.A.R.V.I.S.
      </h3>

      <div className="space-y-3">
        <div className="glass-panel rounded-lg px-3 py-2.5">
          <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-0.5">Version</p>
          <p className="text-sm text-gray-300">1.0.0</p>
        </div>

        <div className="glass-panel rounded-lg px-3 py-2.5">
          <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-0.5">Full Name</p>
          <p className="text-sm text-gray-300">Just A Rather Very Intelligent System</p>
        </div>

        <div className="glass-panel rounded-lg px-3 py-2.5">
          <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-0.5">Frontend</p>
          <p className="text-sm text-gray-300">React + Three.js + TypeScript</p>
        </div>

        <div className="glass-panel rounded-lg px-3 py-2.5">
          <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-0.5">Backend</p>
          <p className="text-sm text-gray-300">FastAPI + WebSocket</p>
        </div>
      </div>

      <div className="text-center pt-2">
        <p className="text-[10px] text-gray-600">
          Stark Industries
        </p>
        <p className="text-[10px] text-gray-700 mt-0.5">
          "Sometimes you gotta run before you can walk."
        </p>
      </div>
    </div>
  );
}

export default function SettingsPanel() {
  const [isOpen, setIsOpen] = useState(false);
  const [activeSection, setActiveSection] = useState<SettingsSection>('profile');

  // Listen for toggle events from ChatPanel
  useEffect(() => {
    const handler = (e: Event) => {
      const customEvent = e as CustomEvent<{ open: boolean }>;
      setIsOpen(customEvent.detail.open);
    };
    window.addEventListener('jarvis-settings-toggle', handler);
    return () => window.removeEventListener('jarvis-settings-toggle', handler);
  }, []);

  const handleClose = useCallback(() => {
    setIsOpen(false);
    window.dispatchEvent(new CustomEvent('jarvis-settings-toggle', { detail: { open: false } }));
  }, []);

  const renderSection = () => {
    switch (activeSection) {
      case 'profile':
        return <ProfileSection />;
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
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-40 bg-black/40"
            onClick={handleClose}
          />

          {/* Panel */}
          <motion.div
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
            className="fixed right-0 top-0 h-full w-full max-w-sm z-50 glass-panel border-l border-jarvis-blue/15 shadow-jarvis-lg flex flex-col"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-jarvis-blue/10">
              <h2 className="font-display text-sm font-semibold tracking-wider text-jarvis-blue">
                Settings
              </h2>
              <button
                onClick={handleClose}
                className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-500 hover:text-jarvis-blue hover:bg-white/[0.03] transition-all"
                aria-label="Close settings"
              >
                <X size={16} />
              </button>
            </div>

            {/* Section Tabs */}
            <div className="flex border-b border-jarvis-blue/10 px-2">
              {sections.map((section) => (
                <button
                  key={section.id}
                  onClick={() => setActiveSection(section.id)}
                  className={clsx(
                    'flex items-center gap-1.5 px-3 py-2.5 text-xs font-medium transition-all border-b-2 -mb-px',
                    {
                      'border-jarvis-blue text-jarvis-blue': activeSection === section.id,
                      'border-transparent text-gray-500 hover:text-gray-300':
                        activeSection !== section.id,
                    }
                  )}
                >
                  {section.icon}
                  <span className="hidden sm:inline">{section.label}</span>
                </button>
              ))}
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-4">{renderSection()}</div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
