import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Lock } from 'lucide-react';
import { useSettingsStore, type ModelProvider } from '@/stores/settingsStore';
import { api } from '@/services/api';
import clsx from 'clsx';

const _PANEL_CLIP = 'polygon(10px 0, calc(50% - 60px) 0, calc(50% - 48px) 5px, calc(50% + 48px) 5px, calc(50% + 60px) 0, calc(100% - 10px) 0, 100% 10px, 100% calc(100% - 10px), calc(100% - 10px) 100%, 10px 100%, 0 calc(100% - 10px), 0 10px)';

interface ProviderDef {
  id: ModelProvider;
  label: string;
  description: string;
  tag: string;
  color: string;
}

const providers: ProviderDef[] = [
  { id: 'claude', label: 'Claude', description: 'Nuanced reasoning', tag: 'UPLINK', color: '#ff8c00' },
  { id: 'gemini', label: 'Gemini', description: 'Multimodal Flash', tag: 'UPLINK', color: '#4285F4' },
  { id: 'stark_protocol', label: 'Stark Protocol', description: 'Self-hosted LLM', tag: 'LOCAL', color: '#00d4ff' },
];

export default function ModelPickerFloat() {
  const [isOpen, setIsOpen] = useState(false);
  const { modelPreference, setModelPreference } = useSettingsStore();
  const [available, setAvailable] = useState<Set<string>>(new Set(providers.map((p) => p.id)));

  useEffect(() => {
    const handler = () => setIsOpen((prev) => !prev);
    window.addEventListener('jarvis-model-toggle', handler);
    return () => window.removeEventListener('jarvis-model-toggle', handler);
  }, []);

  useEffect(() => {
    api
      .get<{ id: string; available: boolean }[]>('/providers')
      .then((data) => setAvailable(new Set(data.filter((p) => p.available).map((p) => p.id))))
      .catch(() => {});
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

          {/* Centered picker */}
          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: 20 }}
            transition={{ type: 'spring', damping: 25, stiffness: 350 }}
            className="fixed inset-0 z-50 flex items-center justify-center pointer-events-none"
          >
            <div className="relative w-full max-w-[360px] mx-4 pointer-events-auto">
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
              {/* Header */}
              <div className="flex items-center justify-between px-5 py-3.5">
                <span className="hud-label text-[10px]">SELECT MODEL</span>
                <button
                  onClick={handleClose}
                  className="glass-circle w-7 h-7 flex items-center justify-center"
                >
                  <X size={12} className="text-gray-400" />
                </button>
              </div>

              {/* Provider list */}
              <div className="px-3 pb-4 space-y-1">
                {providers.map((p) => {
                  const isAvail = available.has(p.id);
                  const isSelected = modelPreference === p.id;
                  return (
                    <button
                      key={p.id}
                      disabled={!isAvail}
                      onClick={() => {
                        if (isAvail) {
                          setModelPreference(p.id);
                          handleClose();
                        }
                      }}
                      className={clsx(
                        'w-full text-left px-4 py-3 hud-clip-sm transition-all flex items-center justify-between',
                        isSelected
                          ? 'bg-white/[0.06] border border-white/[0.08]'
                          : 'border border-transparent hover:bg-white/[0.03]',
                        !isAvail && 'opacity-30 cursor-not-allowed',
                      )}
                    >
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-[8px] font-mono text-gray-600 uppercase">
                            {p.tag}
                          </span>
                          <span
                            className={clsx(
                              'text-xs font-semibold',
                              isSelected ? 'text-white' : 'text-gray-300',
                            )}
                          >
                            {p.label}
                          </span>
                          {!isAvail && <Lock size={9} className="text-gray-600" />}
                        </div>
                        <p className="text-[10px] text-gray-600 font-mono mt-0.5">
                          {p.description}
                        </p>
                      </div>
                      {isSelected && isAvail && (
                        <div
                          className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                          style={{
                            backgroundColor: p.color,
                            boxShadow: `0 0 8px ${p.color}66`,
                          }}
                        />
                      )}
                    </button>
                  );
                })}
              </div>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
