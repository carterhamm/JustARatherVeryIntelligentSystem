import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, ArrowUp, ArrowDown, ArrowRight,
  Home, Eye, EyeOff, Hand, Maximize2, ZoomIn, ZoomOut,
  Video, VideoOff, ChevronLeft, RotateCcw, Camera,
} from 'lucide-react';
import { api } from '@/services/api';
import { useAuthStore } from '@/stores/authStore';

// ── Types ────────────────────────────────────────────────────────────────

interface CameraStatus {
  online: boolean;
  fps: number;
  resolution: number[];
  camera_ip: string;
  gestures_enabled: boolean;
  ptz_enabled: boolean;
  model: string;
  error?: string;
}

interface GestureState {
  active: boolean;
  gesture: string | null;
  confidence: number;
  hand_count: number;
  hold_frames: number;
  recent: { gesture: string; confidence: number; time: number }[];
}

// ── Gesture label map ────────────────────────────────────────────────────

const GESTURE_LABELS: Record<string, { label: string; icon: string }> = {
  open_palm: { label: 'OPEN PALM', icon: '🖐️' },
  fist: { label: 'FIST', icon: '✊' },
  thumbs_up: { label: 'THUMBS UP', icon: '👍' },
  thumbs_down: { label: 'THUMBS DOWN', icon: '👎' },
  point: { label: 'POINTING', icon: '👆' },
  peace: { label: 'PEACE', icon: '✌️' },
};

// ── Main Component ───────────────────────────────────────────────────────

export default function CameraPage() {
  const navigate = useNavigate();
  const token = useAuthStore((s) => s.token);

  const [status, setStatus] = useState<CameraStatus | null>(null);
  const [gestures, setGestures] = useState<GestureState | null>(null);
  const [frameUrl, setFrameUrl] = useState<string>('');
  const [streaming, setStreaming] = useState(true);
  const [gesturesEnabled, setGesturesEnabled] = useState(true);
  const [showOverlay, setShowOverlay] = useState(true);
  const [fullscreen, setFullscreen] = useState(false);
  const [ptzActive, setPtzActive] = useState<string | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const frameIntervalRef = useRef<ReturnType<typeof setInterval>>();
  const gestureIntervalRef = useRef<ReturnType<typeof setInterval>>();

  // ── Fetch camera status ────────────────────────────────────────────────

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const data = await api.get<CameraStatus>('/camera/status');
        setStatus(data);
      } catch {
        setStatus({ online: false, fps: 0, resolution: [0, 0], camera_ip: '',
          gestures_enabled: false, ptz_enabled: false, model: '', error: 'Offline' });
      }
    };
    fetchStatus();
    const interval = setInterval(fetchStatus, 10000);
    return () => clearInterval(interval);
  }, []);

  // ── Frame polling (snapshot-based live view) ───────────────────────────

  useEffect(() => {
    if (!streaming) {
      if (frameIntervalRef.current) clearInterval(frameIntervalRef.current);
      return;
    }

    const fetchFrame = async () => {
      try {
        const resp = await fetch(`${import.meta.env.VITE_API_URL || '/api/v1'}/camera/snapshot`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (resp.ok) {
          const blob = await resp.blob();
          const url = URL.createObjectURL(blob);
          setFrameUrl((prev) => {
            if (prev) URL.revokeObjectURL(prev);
            return url;
          });
        }
      } catch { /* camera offline */ }
    };

    fetchFrame();
    frameIntervalRef.current = setInterval(fetchFrame, 150); // ~7fps
    return () => {
      if (frameIntervalRef.current) clearInterval(frameIntervalRef.current);
    };
  }, [streaming, token]);

  // ── Gesture polling ────────────────────────────────────────────────────

  useEffect(() => {
    if (!gesturesEnabled) return;

    const fetchGestures = async () => {
      try {
        const data = await api.get<GestureState>('/camera/gestures');
        setGestures(data);
      } catch { /* ignore */ }
    };

    fetchGestures();
    gestureIntervalRef.current = setInterval(fetchGestures, 500);
    return () => {
      if (gestureIntervalRef.current) clearInterval(gestureIntervalRef.current);
    };
  }, [gesturesEnabled]);

  // ── PTZ Control ────────────────────────────────────────────────────────

  const sendPTZ = useCallback(async (action: string) => {
    setPtzActive(action);
    try {
      await api.post(`/camera/ptz/${action}`, { speed: 0.5, duration: 0.5 });
    } catch { /* ignore */ }
    setTimeout(() => setPtzActive(null), 600);
  }, []);

  // ── Keyboard shortcuts ─────────────────────────────────────────────────

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') navigate('/');
      if (e.key === 'ArrowLeft') sendPTZ('left');
      if (e.key === 'ArrowRight') sendPTZ('right');
      if (e.key === 'ArrowUp') sendPTZ('up');
      if (e.key === 'ArrowDown') sendPTZ('down');
      if (e.key === 'h' || e.key === 'H') sendPTZ('home');
      if (e.key === 'f' || e.key === 'F') setFullscreen((p) => !p);
      if (e.key === 'o' || e.key === 'O') setShowOverlay((p) => !p);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [navigate, sendPTZ]);

  // ── Fullscreen toggle ──────────────────────────────────────────────────

  useEffect(() => {
    if (fullscreen && containerRef.current) {
      containerRef.current.requestFullscreen?.();
    } else if (!fullscreen && document.fullscreenElement) {
      document.exitFullscreen?.();
    }
  }, [fullscreen]);

  // ── Render ─────────────────────────────────────────────────────────────

  const gestureInfo = gestures?.gesture ? GESTURE_LABELS[gestures.gesture] : null;

  return (
    <div ref={containerRef} className="relative w-full h-screen bg-[#050510] overflow-hidden select-none">
      {/* Camera Feed */}
      <div className="absolute inset-0 flex items-center justify-center">
        {frameUrl ? (
          <img
            src={frameUrl}
            alt="Camera feed"
            className="max-w-full max-h-full object-contain"
            draggable={false}
          />
        ) : (
          <div className="flex flex-col items-center gap-4 text-gray-500">
            <VideoOff size={48} className="text-gray-600" />
            <span className="font-mono text-sm tracking-wider">
              {status?.error || 'CONNECTING TO CAMERA...'}
            </span>
          </div>
        )}
      </div>

      {/* HUD Overlay */}
      {showOverlay && (
        <>
          {/* Top Bar */}
          <div className="absolute top-0 left-0 right-0 z-10 flex items-center justify-between px-6 py-4"
            style={{ background: 'linear-gradient(to bottom, rgba(5,5,16,0.8), transparent)' }}>
            {/* Back + Title */}
            <div className="flex items-center gap-4">
              <button
                onClick={() => navigate('/')}
                className="glass-circle w-9 h-9 flex items-center justify-center hover:border-[#00d4ff]/30 transition-colors"
              >
                <ChevronLeft size={16} className="text-[#00d4ff]" />
              </button>
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${status?.online ? 'bg-green-400 shadow-[0_0_8px_rgba(74,222,128,0.6)]' : 'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.6)]'}`} />
                <span className="font-mono text-xs text-[#00d4ff] tracking-[3px] uppercase">
                  {status?.model || 'CAMERA'}
                </span>
              </div>
            </div>

            {/* Controls */}
            <div className="flex items-center gap-2">
              <HUDButton
                icon={streaming ? Video : VideoOff}
                label={streaming ? 'LIVE' : 'PAUSED'}
                active={streaming}
                onClick={() => setStreaming((p) => !p)}
              />
              <HUDButton
                icon={gesturesEnabled ? Hand : EyeOff}
                label="GESTURES"
                active={gesturesEnabled}
                accent="#f0a500"
                onClick={() => setGesturesEnabled((p) => !p)}
              />
              <HUDButton
                icon={Eye}
                label="HUD"
                active={showOverlay}
                onClick={() => setShowOverlay((p) => !p)}
              />
              <HUDButton
                icon={Maximize2}
                label="FULLSCREEN"
                onClick={() => setFullscreen((p) => !p)}
              />
            </div>
          </div>

          {/* Bottom Bar — Timestamp + Gesture */}
          <div className="absolute bottom-0 left-0 right-0 z-10 flex items-end justify-between px-6 py-4"
            style={{ background: 'linear-gradient(to top, rgba(5,5,16,0.8), transparent)' }}>
            {/* Timestamp + Feed Info */}
            <div className="font-mono text-[10px] text-gray-500">
              <div className="text-[#00d4ff]/60 tracking-[2px]">REC ● {new Date().toLocaleTimeString()}</div>
              <div>{new Date().toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })}</div>
              <div className="mt-1 text-gray-600">
                {status?.camera_ip || '—'} · {status?.resolution?.join('×') || '—'} · {status?.fps || 0} FPS
              </div>
            </div>

            {/* Gesture indicator */}
            {gestureInfo && gestures && gestures.confidence > 0.6 && (
              <div className="flex items-center gap-3 px-4 py-2 rounded-lg"
                style={{ background: 'rgba(240,165,0,0.1)', border: '1px solid rgba(240,165,0,0.3)' }}>
                <span className="text-2xl">{gestureInfo.icon}</span>
                <div>
                  <div className="font-mono text-xs text-[#f0a500] tracking-[2px]">{gestureInfo.label}</div>
                  <div className="font-mono text-[10px] text-gray-500">
                    {Math.round(gestures.confidence * 100)}% · {gestures.hand_count} hand{gestures.hand_count !== 1 ? 's' : ''}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* PTZ Controls — Right side */}
          {status?.ptz_enabled && (
            <div className="absolute right-6 top-1/2 -translate-y-1/2 z-10 flex flex-col items-center gap-1">
              <PTZButton icon={ZoomIn} onClick={() => sendPTZ('zoom_in')} active={ptzActive === 'zoom_in'} />
              <div className="h-2" />
              <PTZButton icon={ArrowUp} onClick={() => sendPTZ('up')} active={ptzActive === 'up'} />
              <div className="flex gap-1">
                <PTZButton icon={ArrowLeft} onClick={() => sendPTZ('left')} active={ptzActive === 'left'} />
                <PTZButton icon={Home} onClick={() => sendPTZ('home')} active={ptzActive === 'home'} small />
                <PTZButton icon={ArrowRight} onClick={() => sendPTZ('right')} active={ptzActive === 'right'} />
              </div>
              <PTZButton icon={ArrowDown} onClick={() => sendPTZ('down')} active={ptzActive === 'down'} />
              <div className="h-2" />
              <PTZButton icon={ZoomOut} onClick={() => sendPTZ('zoom_out')} active={ptzActive === 'zoom_out'} />
            </div>
          )}

          {/* HUD Corner Brackets */}
          <svg className="absolute inset-0 w-full h-full pointer-events-none z-[5]">
            <HUDCorners />
          </svg>

          {/* Scanline */}
          <div className="absolute inset-0 pointer-events-none z-[4] opacity-[0.03]"
            style={{
              backgroundImage: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,212,255,0.15) 2px, rgba(0,212,255,0.15) 4px)',
              backgroundSize: '100% 4px',
            }}
          />
        </>
      )}
    </div>
  );
}

// ── Sub-components ───────────────────────────────────────────────────────

function HUDButton({ icon: Icon, label, active, accent, onClick }: {
  icon: React.ElementType; label: string; active?: boolean; accent?: string; onClick: () => void;
}) {
  const color = accent || '#00d4ff';
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-2 px-3 py-1.5 rounded transition-all font-mono text-[10px] tracking-wider"
      style={{
        background: active ? `${color}15` : 'rgba(255,255,255,0.03)',
        border: `1px solid ${active ? `${color}40` : 'rgba(255,255,255,0.06)'}`,
        color: active ? color : '#6b7280',
      }}
    >
      <Icon size={12} />
      {label}
    </button>
  );
}

function PTZButton({ icon: Icon, onClick, active, small }: {
  icon: React.ElementType; onClick: () => void; active?: boolean; small?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center justify-center rounded-lg transition-all ${small ? 'w-8 h-8' : 'w-10 h-10'}`}
      style={{
        background: active ? 'rgba(0,212,255,0.2)' : 'rgba(255,255,255,0.03)',
        border: `1px solid ${active ? 'rgba(0,212,255,0.5)' : 'rgba(255,255,255,0.08)'}`,
        boxShadow: active ? '0 0 12px rgba(0,212,255,0.3)' : 'none',
      }}
    >
      <Icon size={small ? 12 : 16} className={active ? 'text-[#00d4ff]' : 'text-gray-500'} />
    </button>
  );
}

function HUDCorners() {
  const len = 30;
  const pad = 20;
  const color = 'rgba(0,212,255,0.15)';
  return (
    <>
      {/* Top-left */}
      <line x1={pad} y1={pad} x2={pad + len} y2={pad} stroke={color} strokeWidth={1} />
      <line x1={pad} y1={pad} x2={pad} y2={pad + len} stroke={color} strokeWidth={1} />
      {/* Top-right */}
      <line x1="100%" y1={pad} x2="100%" y2={pad + len} stroke={color} strokeWidth={1} transform={`translate(-${pad}, 0)`} />
      <line x1="100%" y1={pad} x2="100%" y2={pad} stroke={color} strokeWidth={1} transform={`translate(-${pad}, 0)`} />
      {/* Bottom-left */}
      <line x1={pad} y1="100%" x2={pad + len} y2="100%" stroke={color} strokeWidth={1} transform={`translate(0, -${pad})`} />
      <line x1={pad} y1="100%" x2={pad} y2="100%" stroke={color} strokeWidth={1} transform={`translate(0, -${pad + len})`} />
      {/* Bottom-right — simplified */}
      <rect x="calc(100% - 50px)" y="calc(100% - 50px)" width={len} height={len} fill="none" stroke={color} strokeWidth={1} rx={0} />
    </>
  );
}
