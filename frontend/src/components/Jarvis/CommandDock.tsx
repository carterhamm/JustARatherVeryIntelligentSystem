import { useState } from 'react';
import {
  MessageSquare,
  Cpu,
  Mic,
  MicOff,
  Brain,
  Download,
  Settings,
  Activity,
} from 'lucide-react';
import { useUIStore } from '@/stores/uiStore';
import { useSettingsStore } from '@/stores/settingsStore';
import clsx from 'clsx';

interface DockIconProps {
  icon: React.ElementType;
  label: string;
  active?: boolean;
  accent?: string;
  onClick?: () => void;
}

function DockIcon({ icon: Icon, label, active, accent, onClick }: DockIconProps) {
  const [hovered, setHovered] = useState(false);

  return (
    <div className="relative flex items-center">
      <button
        onClick={onClick}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        className={clsx(
          'glass-circle w-9 h-9 flex items-center justify-center transition-all',
          active && '!bg-jarvis-blue/15 !border-jarvis-blue/30 shadow-glow-cyan',
        )}
        style={accent ? { borderColor: `${accent}33`, boxShadow: active ? `0 0 12px ${accent}33` : undefined } : undefined}
      >
        <Icon
          size={15}
          className={clsx(
            'transition-colors',
            active ? 'text-jarvis-blue' : 'text-gray-500',
          )}
          style={accent && active ? { color: accent } : undefined}
        />
      </button>

      {/* Tooltip — to the right */}
      {hovered && (
        <div className="absolute left-full top-1/2 -translate-y-1/2 ml-3 px-2.5 py-1 glass rounded-lg whitespace-nowrap z-50 pointer-events-none">
          <span className="text-[9px] font-mono text-gray-300 uppercase tracking-wider">
            {label}
          </span>
        </div>
      )}

      {/* Active indicator dot — to the left */}
      {active && (
        <div
          className="absolute -left-1.5 top-1/2 -translate-y-1/2 w-1 h-1 rounded-full bg-jarvis-blue"
          style={accent ? { backgroundColor: accent } : undefined}
        />
      )}
    </div>
  );
}

export default function CommandDock() {
  const isThinking = useUIStore((s) => s.isThinking);
  const voiceEnabled = useSettingsStore((s) => s.voiceEnabled);

  const toggleVoice = () => {
    useSettingsStore.getState().setVoiceEnabled(!voiceEnabled);
  };

  const dispatch = (event: string) => {
    window.dispatchEvent(new CustomEvent(event));
  };

  return (
    <div className="fixed left-4 top-1/2 -translate-y-1/2 z-30 pointer-events-auto boot-4">
      <div className="glass-capsule px-2 py-2.5 flex flex-col items-center gap-1.5">
        <DockIcon
          icon={MessageSquare}
          label="Sessions"
          onClick={() => dispatch('jarvis-sessions-toggle')}
        />
        <DockIcon
          icon={Cpu}
          label="Model"
          onClick={() => dispatch('jarvis-model-toggle')}
        />
        <DockIcon
          icon={voiceEnabled ? Mic : MicOff}
          label="Voice"
          active={voiceEnabled}
          accent="#f0a500"
          onClick={toggleVoice}
        />

        {/* Divider */}
        <div className="w-5 h-px bg-white/[0.06] my-0.5" />

        <DockIcon
          icon={Activity}
          label="Diagnostics"
          active={isThinking}
          accent="#ffbf00"
          onClick={() => dispatch('jarvis-diagnostics-toggle')}
        />
        <DockIcon
          icon={Brain}
          label="Knowledge"
          onClick={() => dispatch('jarvis-knowledge-toggle')}
        />
        <DockIcon
          icon={Download}
          label="Import"
          onClick={() => dispatch('jarvis-import-toggle')}
        />

        {/* Divider */}
        <div className="w-5 h-px bg-white/[0.06] my-0.5" />

        <DockIcon
          icon={Settings}
          label="Settings"
          onClick={() => dispatch('jarvis-settings-toggle')}
        />
      </div>
    </div>
  );
}
