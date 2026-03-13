import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Monitor,
  Smartphone,
  Terminal,
  Watch,
  HelpCircle,
  Shield,
  X,
  LogOut,
  Clock,
  MapPin,
  Globe,
  Wifi,
  Loader,
} from 'lucide-react';
import { api } from '@/services/api';
import { useAutoRefresh } from '@/hooks/useAutoRefresh';
import clsx from 'clsx';

// ── Types ──────────────────────────────────────────────────────────────

interface SessionResponse {
  id: string;
  ip_address: string;
  user_agent: string;
  device_type: string;
  location_city: string | null;
  location_country: string | null;
  signed_in_at: string;
  last_active_at: string;
  expires_at: string;
  is_active: boolean;
  login_method: string;
  is_current: boolean;
}

// ── Helpers ─────────────────────────────────────────────────────────────

function relativeTime(iso: string): string {
  const now = Date.now();
  const then = new Date(iso).getTime();
  const diffMs = now - then;

  if (diffMs < 0) return 'just now';

  const seconds = Math.floor(diffMs / 1000);
  if (seconds < 60) return 'just now';

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;

  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;

  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo ago`;

  const years = Math.floor(months / 12);
  return `${years}y ago`;
}

function getDeviceIcon(deviceType: string) {
  switch (deviceType.toLowerCase()) {
    case 'web':
      return Monitor;
    case 'ios':
    case 'mobile':
      return Smartphone;
    case 'cli':
      return Terminal;
    case 'watch':
      return Watch;
    default:
      return HelpCircle;
  }
}

function formatLoginMethod(method: string): string {
  switch (method) {
    case 'password':
      return 'PASSWORD';
    case 'passkey':
      return 'PASSKEY';
    case 'cli_sht':
      return 'CLI SHT';
    default:
      return method.toUpperCase();
  }
}

// ── Main Panel ──────────────────────────────────────────────────────────

export default function SessionsManagementPanel() {
  const [isOpen, setIsOpen] = useState(false);
  const [sessions, setSessions] = useState<SessionResponse[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [confirmRevokeAll, setConfirmRevokeAll] = useState(false);
  const [revokingAll, setRevokingAll] = useState(false);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  // Toggle listener
  useEffect(() => {
    const handler = () => setIsOpen((prev) => !prev);
    window.addEventListener('jarvis-sessions-manage-toggle', handler);
    return () => window.removeEventListener('jarvis-sessions-manage-toggle', handler);
  }, []);

  // Escape key
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsOpen(false);
        setConfirmRevokeAll(false);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Load sessions when panel opens
  const loadSessions = useCallback(async () => {
    if (!isOpen) return;
    setIsLoading(true);
    try {
      const result = await api.get<SessionResponse[]>('/sessions');
      setSessions(result);
    } catch {
      // silently fail
    } finally {
      setIsLoading(false);
    }
  }, [isOpen]);

  useEffect(() => {
    if (isOpen) {
      loadSessions();
      setConfirmRevokeAll(false);
    }
  }, [isOpen]);

  // Auto-refresh every 30 seconds
  useAutoRefresh(loadSessions, 30_000);

  // Revoke a single session
  const handleRevoke = useCallback(async (id: string) => {
    setRevokingId(id);
    try {
      await api.delete(`/sessions/${id}`);
      setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, is_active: false } : s)));
    } catch {
      // silently fail
    } finally {
      setRevokingId(null);
    }
  }, []);

  // Revoke all sessions
  const handleRevokeAll = useCallback(async () => {
    setRevokingAll(true);
    try {
      await api.delete<{ revoked: number }>('/sessions');
      setSessions((prev) => prev.map((s) => (s.is_current ? s : { ...s, is_active: false })));
      setConfirmRevokeAll(false);
    } catch {
      // silently fail
    } finally {
      setRevokingAll(false);
    }
  }, []);

  const handleClose = useCallback(() => {
    setIsOpen(false);
    setConfirmRevokeAll(false);
  }, []);

  const activeCount = sessions.filter((s) => s.is_active).length;

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
            className="fixed inset-0 z-40 panel-backdrop"
            onClick={handleClose}
          />

          {/* Panel */}
          <motion.div
            initial={{ x: '-100%' }}
            animate={{ x: 0 }}
            exit={{ x: '-100%' }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
            className="fixed left-5 top-5 bottom-5 w-[400px] z-50 glass-heavy hud-clip flex flex-col overflow-hidden"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-jarvis-blue/10">
              <h2 className="font-display text-sm font-semibold tracking-wider text-jarvis-blue flex items-center gap-2">
                <Shield size={16} />
                Sessions
                {sessions.length > 0 && (
                  <span className="text-[10px] text-gray-500 font-mono">({activeCount} active)</span>
                )}
              </h2>
              <button onClick={handleClose} className="text-gray-500 hover:text-jarvis-blue transition-colors">
                <X size={16} />
              </button>
            </div>

            {/* Summary bar */}
            <div className="px-4 py-2.5 border-b border-white/[0.04] flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Wifi size={12} className="text-green-400/70" />
                <span className="text-[11px] font-mono text-green-400/80">
                  {activeCount} active session{activeCount !== 1 ? 's' : ''}
                </span>
              </div>
              <span className="text-[10px] font-mono text-gray-600">
                {sessions.length} total
              </span>
            </div>

            {/* Sign Out All */}
            <div className="px-4 py-3 border-b border-white/[0.04]">
              {!confirmRevokeAll ? (
                <button
                  onClick={() => setConfirmRevokeAll(true)}
                  disabled={activeCount <= 1}
                  className="w-full px-4 py-2.5 text-sm font-medium flex items-center justify-center gap-2 rounded border border-red-500/20 bg-red-500/[0.06] text-red-400 hover:bg-red-500/[0.12] hover:border-red-500/30 transition-all disabled:opacity-30 disabled:cursor-not-allowed hud-clip-sm"
                >
                  <LogOut size={14} />
                  Sign Out All Other Sessions
                </button>
              ) : (
                <div className="space-y-2">
                  <p className="text-[11px] text-red-400/80 font-mono text-center">
                    Revoke all sessions except current?
                  </p>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setConfirmRevokeAll(false)}
                      className="flex-1 px-3 py-2 text-xs font-mono text-gray-400 border border-white/[0.06] hover:border-white/[0.12] transition-colors hud-clip-sm"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleRevokeAll}
                      disabled={revokingAll}
                      className="flex-1 px-3 py-2 text-xs font-mono text-red-400 border border-red-500/20 bg-red-500/[0.08] hover:bg-red-500/[0.15] transition-colors hud-clip-sm flex items-center justify-center gap-1.5"
                    >
                      {revokingAll ? <Loader size={12} className="animate-spin" /> : <LogOut size={12} />}
                      Confirm
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Session list */}
            <div className="flex-1 overflow-y-auto scrollbar-thin">
              {isLoading && sessions.length === 0 ? (
                <div className="flex items-center justify-center py-12 text-gray-500">
                  <Loader size={16} className="animate-spin" />
                </div>
              ) : sessions.length === 0 ? (
                <div className="text-center py-12 px-4">
                  <Shield size={24} className="mx-auto text-gray-600 mb-2" />
                  <p className="text-sm text-gray-500">No sessions recorded yet.</p>
                </div>
              ) : (
                <div className="divide-y divide-white/[0.03]">
                  {sessions.map((session) => (
                    <SessionRow
                      key={session.id}
                      session={session}
                      onRevoke={handleRevoke}
                      revoking={revokingId === session.id}
                    />
                  ))}
                </div>
              )}
            </div>

            {/* Footer */}
            {sessions.length > 0 && (
              <div className="px-4 py-2 border-t border-white/[0.04] flex items-center justify-between">
                <span className="text-[10px] text-gray-600 font-mono">
                  AUTO-REFRESH 30s
                </span>
                <span className="text-[10px] text-gray-600 font-mono">
                  {activeCount} / {sessions.length} ACTIVE
                </span>
              </div>
            )}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

// ── Session Row ─────────────────────────────────────────────────────────

function SessionRow({
  session,
  onRevoke,
  revoking,
}: {
  session: SessionResponse;
  onRevoke: (id: string) => void;
  revoking: boolean;
}) {
  const DeviceIcon = getDeviceIcon(session.device_type);
  const location =
    session.location_city && session.location_country
      ? `${session.location_city}, ${session.location_country}`
      : session.location_city || session.location_country || null;

  return (
    <div
      className={clsx(
        'px-4 py-3 transition-colors',
        session.is_active
          ? 'border-l-2 border-hud-green/30 hover:bg-white/[0.02]'
          : 'border-l-2 border-transparent opacity-60'
      )}
    >
      <div className="flex items-start gap-3">
        {/* Device icon */}
        <div className="flex-shrink-0 mt-0.5">
          <div
            className={clsx(
              'w-8 h-8 rounded-full flex items-center justify-center border',
              session.is_active
                ? 'bg-jarvis-blue/[0.08] border-jarvis-blue/20'
                : 'bg-white/[0.02] border-white/[0.06]'
            )}
          >
            <DeviceIcon
              size={14}
              className={session.is_active ? 'text-jarvis-blue/70' : 'text-gray-600'}
            />
          </div>
        </div>

        {/* Info */}
        <div className="min-w-0 flex-1 space-y-1">
          {/* Device type + method + badges */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-medium text-gray-200 capitalize">
              {session.device_type}
            </span>
            <span className="text-[9px] font-mono tracking-wider px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/[0.06] text-gray-500">
              {formatLoginMethod(session.login_method)}
            </span>
            {session.is_current && (
              <span className="text-[9px] font-mono tracking-wider px-1.5 py-0.5 rounded bg-cyan-500/[0.08] border border-cyan-500/20 text-cyan-400">
                CURRENT
              </span>
            )}
          </div>

          {/* IP address */}
          <div className="flex items-center gap-1.5">
            <Globe size={10} className="text-gray-600 flex-shrink-0" />
            <span className="text-[11px] font-mono text-gray-500">{session.ip_address}</span>
          </div>

          {/* Location */}
          {location && (
            <div className="flex items-center gap-1.5">
              <MapPin size={10} className="text-gray-600 flex-shrink-0" />
              <span className="text-[11px] text-gray-500">{location}</span>
            </div>
          )}

          {/* Times */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1">
              <Clock size={9} className="text-gray-600" />
              <span className="text-[10px] font-mono text-gray-600">
                Signed in {relativeTime(session.signed_in_at)}
              </span>
            </div>
            <span className="text-[10px] font-mono text-gray-600">
              Active {relativeTime(session.last_active_at)}
            </span>
          </div>

          {/* Status badge */}
          <div className="flex items-center gap-1.5 pt-0.5">
            <span
              className={clsx(
                'w-1.5 h-1.5 rounded-full',
                session.is_active ? 'bg-green-400' : 'bg-gray-600'
              )}
            />
            <span
              className={clsx(
                'text-[9px] font-mono tracking-wider',
                session.is_active ? 'text-green-400/80' : 'text-gray-600'
              )}
            >
              {session.is_active ? 'ACTIVE' : new Date(session.expires_at) < new Date() ? 'EXPIRED' : 'REVOKED'}
            </span>
          </div>
        </div>

        {/* Revoke button */}
        {session.is_active && !session.is_current && (
          <div className="flex-shrink-0 mt-1">
            <button
              onClick={() => onRevoke(session.id)}
              disabled={revoking}
              className="text-[10px] font-mono text-red-400/70 hover:text-red-400 transition-colors px-2 py-1 border border-red-500/15 hover:border-red-500/30 rounded hud-clip-sm flex items-center gap-1"
            >
              {revoking ? (
                <Loader size={10} className="animate-spin" />
              ) : (
                <LogOut size={10} />
              )}
              Sign Out
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
