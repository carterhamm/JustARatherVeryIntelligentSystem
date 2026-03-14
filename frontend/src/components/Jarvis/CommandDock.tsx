import { useState, useRef, useEffect } from 'react';
import {
  MessageSquare,
  Volume2,
  VolumeX,
  Brain,
  Settings,
  Activity,
  LayoutGrid,
  Users,
  MapPin,
  Monitor,
  Camera,
  Flame,
  Target,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
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
  expanded?: boolean;
}

function DockIcon({ icon: Icon, label, active, accent, onClick, index, expanded }: DockIconProps) {
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
          'flex items-center transition-colors',
          expanded
            ? 'gap-2.5 w-full px-2 py-1.5 rounded hover:bg-white/[0.04]'
            : 'glass-circle w-9 h-9 justify-center',
          active && !expanded && '!bg-jarvis-blue/15 !border-jarvis-blue/30 shadow-glow-cyan',
        )}
        style={!expanded && accent ? { borderColor: `${accent}33`, boxShadow: active ? `0 0 12px ${accent}33` : undefined } : undefined}
      >
        <Icon
          size={expanded ? 14 : 15}
          className={clsx(
            'transition-colors flex-shrink-0',
            active ? 'text-jarvis-blue' : 'text-gray-500',
          )}
          style={accent && active ? { color: accent } : undefined}
        />
        {expanded && (
          <span className="text-[9px] font-mono text-gray-400 uppercase tracking-wider truncate">
            {label}
          </span>
        )}
      </button>

      {/* Tooltip — to the right (only when not expanded) */}
      {hovered && !expanded && (
        <div className="absolute left-full top-1/2 -translate-y-1/2 ml-3 px-2.5 py-1 glass hud-clip-sm whitespace-nowrap z-50 pointer-events-none animate-fade-in">
          <span className="text-[9px] font-mono text-gray-300 uppercase tracking-wider">
            {label}
          </span>
        </div>
      )}

      {/* Active indicator dot — to the left */}
      {active && !expanded && (
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
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);

  // D key hold to expand dock
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if (e.key === 'd' && !e.metaKey && !e.ctrlKey && !e.repeat) setExpanded(true);
    };
    const up = (e: KeyboardEvent) => {
      if (e.key === 'd') setExpanded(false);
    };
    window.addEventListener('keydown', down);
    window.addEventListener('keyup', up);
    return () => { window.removeEventListener('keydown', down); window.removeEventListener('keyup', up); };
  }, []);

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
      <div
        ref={dockRef}
        className={clsx(
          'glass-capsule py-2.5 flex flex-col gap-1.5 pointer-events-auto transition-all duration-200',
          expanded ? 'px-3' : 'px-2',
        )}
        style={{ width: expanded ? 160 : undefined }}
      >
        <DockIcon expanded={expanded}
          icon={MessageSquare}
          label="Sessions"
          index={0}
          onClick={() => dispatch('jarvis-sessions-toggle')}
        />
        <DockIcon expanded={expanded}
          icon={voiceEnabled ? Volume2 : VolumeX}
          label="Voice"
          active={voiceEnabled}
          accent="#f0a500"
          index={1}
          onClick={toggleVoice}
        />

        {/* Divider */}
        <div className="w-5 h-px bg-white/[0.06] my-0.5" />

        <DockIcon expanded={expanded}
          icon={Users}
          label="Contacts"
          index={2}
          onClick={() => dispatch('jarvis-contacts-toggle')}
        />
        <DockIcon expanded={expanded}
          icon={Flame}
          label="Habits"
          accent="#f0a500"
          index={3}
          onClick={() => dispatch('jarvis-habits-toggle')}
        />
        <DockIcon expanded={expanded}
          icon={Target}
          label="Focus"
          accent="#00d4ff"
          index={4}
          onClick={() => dispatch('jarvis-focus-toggle')}
        />

        {/* Divider */}
        <div className="w-5 h-px bg-white/[0.06] my-0.5" />

        <DockIcon expanded={expanded}
          icon={MapPin}
          label="Atlas"
          index={5}
          onClick={() => navigate('/atlas')}
        />
        <DockIcon expanded={expanded}
          icon={Camera}
          label="Camera"
          index={6}
          onClick={() => navigate('/camera')}
        />
        <DockIcon expanded={expanded}
          icon={Monitor}
          label="Remote Desktop"
          index={7}
          onClick={() => window.open('/vnc/mac-mini', '_blank')}
        />

        {/* Divider */}
        <div className="w-5 h-px bg-white/[0.06] my-0.5" />

        <DockIcon expanded={expanded}
          icon={Settings}
          label="Settings"
          index={8}
          onClick={() => dispatch('jarvis-settings-toggle')}
        />
      </div>
    </div>
  );
}
