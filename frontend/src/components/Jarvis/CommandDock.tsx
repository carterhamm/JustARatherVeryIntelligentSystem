import { useState, useRef, useEffect } from 'react';
import {
  MessageSquare,
  Cpu,
  Volume2,
  VolumeX,
  Brain,
  Download,
  Settings,
  Activity,
  LayoutGrid,
} from 'lucide-react';
import { useUIStore } from '@/stores/uiStore';
import { useSettingsStore } from '@/stores/settingsStore';
import gsap from 'gsap';
import clsx from 'clsx';

interface DockIconProps {
  icon: React.ElementType;
  label: string;
  active?: boolean;
  accent?: string;
  onClick?: () => void;
  index: number;
}

function DockIcon({ icon: Icon, label, active, accent, onClick, index }: DockIconProps) {
  const [hovered, setHovered] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);

  const handleMouseEnter = () => {
    setHovered(true);
    if (btnRef.current) {
      gsap.to(btnRef.current, {
        scale: 1.15,
        duration: 0.2,
        ease: 'back.out(1.7)',
      });
    }
  };

  const handleMouseLeave = () => {
    setHovered(false);
    if (btnRef.current) {
      gsap.to(btnRef.current, {
        scale: 1,
        duration: 0.3,
        ease: 'power2.out',
      });
    }
  };

  const handleClick = () => {
    if (btnRef.current) {
      gsap.fromTo(
        btnRef.current,
        { scale: 0.9 },
        { scale: 1, duration: 0.4, ease: 'elastic.out(1, 0.3)' },
      );
    }
    onClick?.();
  };

  return (
    <div className="relative flex items-center">
      <button
        ref={btnRef}
        onClick={handleClick}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        className={clsx(
          'glass-circle w-9 h-9 flex items-center justify-center transition-colors',
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
        <div className="absolute left-full top-1/2 -translate-y-1/2 ml-3 px-2.5 py-1 glass rounded-lg whitespace-nowrap z-50 pointer-events-none animate-fade-in">
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
  const dockRef = useRef<HTMLDivElement>(null);

  // GSAP stagger boot animation
  useEffect(() => {
    if (dockRef.current) {
      const icons = dockRef.current.querySelectorAll('.glass-circle');
      gsap.fromTo(
        icons,
        { opacity: 0, x: -15, scale: 0.8 },
        {
          opacity: 1,
          x: 0,
          scale: 1,
          duration: 0.4,
          ease: 'back.out(1.7)',
          stagger: 0.05,
          delay: 0.5,
        },
      );
    }
  }, []);

  const toggleVoice = () => {
    useSettingsStore.getState().setVoiceEnabled(!voiceEnabled);
  };

  const dispatch = (event: string) => {
    window.dispatchEvent(new CustomEvent(event));
  };

  return (
    <div className="fixed left-4 inset-y-0 z-30 pointer-events-none flex items-center">
      <div ref={dockRef} className="glass-capsule px-2 py-2.5 flex flex-col items-center gap-1.5 pointer-events-auto">
        <DockIcon
          icon={MessageSquare}
          label="Sessions"
          index={0}
          onClick={() => dispatch('jarvis-sessions-toggle')}
        />
        <DockIcon
          icon={Cpu}
          label="Model"
          index={1}
          onClick={() => dispatch('jarvis-model-toggle')}
        />
        <DockIcon
          icon={voiceEnabled ? Volume2 : VolumeX}
          label="Voice"
          active={voiceEnabled}
          accent="#f0a500"
          index={2}
          onClick={toggleVoice}
        />

        {/* Divider */}
        <div className="w-5 h-px bg-white/[0.06] my-0.5" />

        <DockIcon
          icon={Activity}
          label="Diagnostics"
          active={isThinking}
          accent="#ffbf00"
          index={3}
          onClick={() => dispatch('jarvis-diagnostics-toggle')}
        />
        <DockIcon
          icon={LayoutGrid}
          label="Widgets"
          index={4}
          onClick={() => dispatch('jarvis-widgets-toggle')}
        />
        <DockIcon
          icon={Brain}
          label="Knowledge"
          index={5}
          onClick={() => dispatch('jarvis-knowledge-toggle')}
        />
        <DockIcon
          icon={Download}
          label="Import"
          index={6}
          onClick={() => dispatch('jarvis-import-toggle')}
        />

        {/* Divider */}
        <div className="w-5 h-px bg-white/[0.06] my-0.5" />

        <DockIcon
          icon={Settings}
          label="Settings"
          index={7}
          onClick={() => dispatch('jarvis-settings-toggle')}
        />
      </div>
    </div>
  );
}
