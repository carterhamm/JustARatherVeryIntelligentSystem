import { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  X,
  Play,
  Square,
  Plus,
  Clock,
  Target,
  Zap,
  Brain,
  BarChart3,
  History,
  Star,
  AlertTriangle,
} from 'lucide-react';
import { api } from '@/services/api';
import { useAutoRefresh } from '@/hooks/useAutoRefresh';
import clsx from 'clsx';

// ── Types ──────────────────────────────────────────────────────────────

type Category = 'learning' | 'deep_work' | 'creative' | 'admin';
type TabKey = 'session' | 'history' | 'stats';
type StatsPeriod = 'week' | 'month';

interface FocusSession {
  id: string;
  title: string;
  category: Category;
  started_at: string;
  ended_at: string | null;
  planned_duration_min: number | null;
  actual_duration_min: number | null;
  notes: string | null;
  distractions: number;
  energy_level: number | null;
  productivity_rating: number | null;
  in_progress: boolean;
}

interface FocusStats {
  period: StatsPeriod;
  total_sessions: number;
  total_focus_hours: number;
  avg_session_min: number;
  avg_productivity: number;
  avg_energy: number;
  total_distractions: number;
  by_category: Record<string, { sessions: number; hours: number }>;
}

interface HistoryResponse {
  sessions: FocusSession[];
  total: number;
}

// ── Constants ─────────────────────────────────────────────────────────

const CATEGORY_COLORS: Record<Category, string> = {
  learning: '#4285F4',
  deep_work: '#00d4ff',
  creative: '#f0a500',
  admin: '#39ff14',
};

const CATEGORY_LABELS: Record<Category, string> = {
  learning: 'Learning',
  deep_work: 'Deep Work',
  creative: 'Creative',
  admin: 'Admin',
};

const ALL_CATEGORIES: Category[] = ['learning', 'deep_work', 'creative', 'admin'];

// ── Helpers ───────────────────────────────────────────────────────────

function formatElapsed(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function formatDuration(minutes: number): string {
  if (minutes < 60) return `${Math.round(minutes)}m`;
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  const days = Math.floor(diff / 86400000);
  if (days === 0) return 'Today';
  if (days === 1) return 'Yesterday';
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

// ── Sub-Components ────────────────────────────────────────────────────

function CategoryBadge({ category, size = 'sm' }: { category: Category; size?: 'sm' | 'md' }) {
  const color = CATEGORY_COLORS[category];
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 font-mono tracking-wider uppercase rounded-full border',
        size === 'sm' ? 'text-[8px] px-1.5 py-0.5' : 'text-[9px] px-2 py-0.5'
      )}
      style={{
        color,
        borderColor: `${color}33`,
        backgroundColor: `${color}0D`,
      }}
    >
      <span
        className="inline-block w-1.5 h-1.5 rounded-full"
        style={{ backgroundColor: color }}
      />
      {CATEGORY_LABELS[category]}
    </span>
  );
}

function DotRating({
  value,
  max = 5,
  color = '#00d4ff',
  onChange,
  readonly = false,
}: {
  value: number;
  max?: number;
  color?: string;
  onChange?: (v: number) => void;
  readonly?: boolean;
}) {
  return (
    <div className="flex items-center gap-1">
      {Array.from({ length: max }, (_, i) => (
        <button
          key={i}
          type="button"
          disabled={readonly}
          onClick={() => onChange?.(i + 1)}
          className={clsx(
            'transition-all',
            readonly ? 'cursor-default' : 'cursor-pointer hover:scale-125'
          )}
        >
          <Star
            size={readonly ? 10 : 14}
            fill={i < value ? color : 'transparent'}
            stroke={i < value ? color : '#ffffff15'}
            strokeWidth={1.5}
          />
        </button>
      ))}
    </div>
  );
}

// ── Active Session View ───────────────────────────────────────────────

function ActiveSessionView({
  session,
  onEnd,
  onDistraction,
}: {
  session: FocusSession;
  onEnd: () => void;
  onDistraction: () => void;
}) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const start = new Date(session.started_at).getTime();
    const tick = () => setElapsed(Math.floor((Date.now() - start) / 1000));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [session.started_at]);

  const progress =
    session.planned_duration_min
      ? Math.min(100, (elapsed / (session.planned_duration_min * 60)) * 100)
      : null;

  return (
    <div className="px-4 py-5 space-y-5">
      {/* Timer */}
      <div className="text-center space-y-2">
        <div
          className="text-4xl font-mono tracking-[0.15em] animate-pulse"
          style={{ color: '#00d4ff', textShadow: '0 0 20px rgba(0,212,255,0.4)' }}
        >
          {formatElapsed(elapsed)}
        </div>
        {progress !== null && (
          <div className="w-full h-1 rounded-full bg-white/[0.06] overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-1000"
              style={{
                width: `${progress}%`,
                backgroundColor: progress >= 100 ? '#f0a500' : '#00d4ff',
              }}
            />
          </div>
        )}
        {session.planned_duration_min && (
          <p className="text-[9px] font-mono text-gray-500 tracking-wider">
            PLANNED: {session.planned_duration_min}MIN
            {progress !== null && progress >= 100 && (
              <span className="ml-2 text-[#f0a500]">// EXCEEDED</span>
            )}
          </p>
        )}
      </div>

      {/* Session info */}
      <div className="bg-white/[0.03] border border-white/[0.06] rounded-lg p-3 space-y-2">
        <p className="text-sm text-gray-200 font-medium">{session.title}</p>
        <CategoryBadge category={session.category} size="md" />
      </div>

      {/* Distraction counter */}
      <div className="flex items-center justify-between bg-white/[0.03] border border-white/[0.06] rounded-lg p-3">
        <div className="flex items-center gap-2">
          <AlertTriangle size={12} className="text-[#f0a500]" />
          <span className="text-[10px] font-mono text-gray-400 tracking-wider">DISTRACTIONS</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-lg font-mono text-gray-200">{session.distractions}</span>
          <button
            onClick={onDistraction}
            className="w-7 h-7 rounded-md bg-white/[0.05] border border-white/[0.08] hover:border-[#f0a500]/40 hover:bg-[#f0a500]/10 transition-all flex items-center justify-center"
          >
            <Plus size={12} className="text-[#f0a500]" />
          </button>
        </div>
      </div>

      {/* End session button */}
      <button
        onClick={onEnd}
        className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-[#ff4444]/10 border border-[#ff4444]/30 hover:bg-[#ff4444]/20 transition-all text-[#ff4444] text-sm font-mono tracking-wider"
      >
        <Square size={14} />
        END SESSION
      </button>
    </div>
  );
}

// ── End Session Rating Form ───────────────────────────────────────────

function EndSessionForm({
  onSubmit,
  onCancel,
  submitting,
}: {
  onSubmit: (data: { notes?: string; energy_level?: number; productivity_rating?: number }) => void;
  onCancel: () => void;
  submitting: boolean;
}) {
  const [notes, setNotes] = useState('');
  const [energy, setEnergy] = useState(0);
  const [productivity, setProductivity] = useState(0);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      notes: notes.trim() || undefined,
      energy_level: energy || undefined,
      productivity_rating: productivity || undefined,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="px-4 py-5 space-y-5">
      <div className="text-center">
        <h3 className="text-[11px] font-mono tracking-[0.2em] text-gray-400 mb-1">SESSION COMPLETE</h3>
        <p className="text-[10px] font-mono text-gray-600">Rate your session below</p>
      </div>

      {/* Energy */}
      <div className="space-y-1.5">
        <div className="flex items-center gap-1.5">
          <Zap size={10} className="text-[#f0a500]" />
          <span className="text-[9px] font-mono text-gray-500 tracking-wider">ENERGY LEVEL</span>
        </div>
        <DotRating value={energy} onChange={setEnergy} color="#f0a500" />
      </div>

      {/* Productivity */}
      <div className="space-y-1.5">
        <div className="flex items-center gap-1.5">
          <Brain size={10} className="text-[#00d4ff]" />
          <span className="text-[9px] font-mono text-gray-500 tracking-wider">PRODUCTIVITY</span>
        </div>
        <DotRating value={productivity} onChange={setProductivity} color="#00d4ff" />
      </div>

      {/* Notes */}
      <div className="space-y-1.5">
        <span className="text-[9px] font-mono text-gray-500 tracking-wider">NOTES</span>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
          placeholder="What did you accomplish?"
          className="w-full bg-white/[0.03] border border-white/[0.06] rounded-lg px-3 py-2 text-sm font-mono text-gray-300 placeholder-gray-600 resize-none focus:outline-none focus:border-[#00d4ff]/30"
        />
      </div>

      {/* Actions */}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="flex-1 px-4 py-2 rounded-lg bg-white/[0.03] border border-white/[0.06] text-gray-400 text-[10px] font-mono tracking-wider hover:bg-white/[0.06] transition-all"
        >
          CANCEL
        </button>
        <button
          type="submit"
          disabled={submitting}
          className="flex-1 px-4 py-2.5 rounded-lg bg-[#00d4ff]/10 border border-[#00d4ff]/30 text-[#00d4ff] text-[10px] font-mono tracking-wider hover:bg-[#00d4ff]/20 transition-all disabled:opacity-40"
        >
          {submitting ? 'SAVING...' : 'SUBMIT'}
        </button>
      </div>
    </form>
  );
}

// ── Start Session View ────────────────────────────────────────────────

function StartSessionView({ onStart, starting }: { onStart: (data: { title: string; category: Category; planned_duration_min?: number }) => void; starting: boolean }) {
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState<Category>('deep_work');
  const [duration, setDuration] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    onStart({
      title: title.trim(),
      category,
      planned_duration_min: duration ? parseInt(duration, 10) : undefined,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="px-4 py-5 space-y-5">
      {/* Title */}
      <div className="space-y-1.5">
        <span className="text-[9px] font-mono text-gray-500 tracking-wider">SESSION TITLE</span>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="What are you focusing on?"
          required
          className="w-full bg-white/[0.03] border border-white/[0.06] rounded-lg px-3 py-2.5 text-sm font-mono text-gray-200 placeholder-gray-600 focus:outline-none focus:border-[#00d4ff]/30"
        />
      </div>

      {/* Category */}
      <div className="space-y-1.5">
        <span className="text-[9px] font-mono text-gray-500 tracking-wider">CATEGORY</span>
        <div className="grid grid-cols-2 gap-2">
          {ALL_CATEGORIES.map((cat) => {
            const color = CATEGORY_COLORS[cat];
            const active = category === cat;
            return (
              <button
                key={cat}
                type="button"
                onClick={() => setCategory(cat)}
                className={clsx(
                  'flex items-center gap-2 px-3 py-2 rounded-lg border text-[10px] font-mono tracking-wider transition-all',
                  active
                    ? 'bg-white/[0.06] border-opacity-40'
                    : 'bg-white/[0.02] border-white/[0.06] hover:bg-white/[0.04]'
                )}
                style={active ? { borderColor: `${color}66`, color } : { color: '#9ca3af' }}
              >
                <span
                  className="w-2 h-2 rounded-full flex-shrink-0"
                  style={{ backgroundColor: active ? color : '#4b5563' }}
                />
                {CATEGORY_LABELS[cat].toUpperCase()}
              </button>
            );
          })}
        </div>
      </div>

      {/* Duration */}
      <div className="space-y-1.5">
        <div className="flex items-center gap-1.5">
          <Clock size={10} className="text-gray-500" />
          <span className="text-[9px] font-mono text-gray-500 tracking-wider">PLANNED DURATION (OPTIONAL)</span>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="number"
            value={duration}
            onChange={(e) => setDuration(e.target.value)}
            placeholder="Minutes"
            min={1}
            max={480}
            className="flex-1 bg-white/[0.03] border border-white/[0.06] rounded-lg px-3 py-2 text-sm font-mono text-gray-200 placeholder-gray-600 focus:outline-none focus:border-[#00d4ff]/30"
          />
          <span className="text-[10px] font-mono text-gray-600">MIN</span>
        </div>
      </div>

      {/* Start button */}
      <button
        type="submit"
        disabled={starting || !title.trim()}
        className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg bg-[#00d4ff]/10 border border-[#00d4ff]/30 hover:bg-[#00d4ff]/20 transition-all text-[#00d4ff] text-sm font-mono tracking-wider disabled:opacity-40"
      >
        <Play size={14} />
        START FOCUS
      </button>
    </form>
  );
}

// ── History Tab ───────────────────────────────────────────────────────

function HistoryTab() {
  const [sessions, setSessions] = useState<FocusSession[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filterCategory, setFilterCategory] = useState<Category | ''>('');
  const offsetRef = useRef(0);

  const loadHistory = useCallback(
    async (reset = false) => {
      setLoading(true);
      const offset = reset ? 0 : offsetRef.current;
      try {
        const params: Record<string, unknown> = { limit: 20, offset };
        if (filterCategory) params.category = filterCategory;
        const result = await api.get<HistoryResponse>('/focus/history', params);
        if (reset) {
          setSessions(result.sessions);
        } else {
          setSessions((prev) => (offset === 0 ? result.sessions : [...prev, ...result.sessions]));
        }
        setTotal(result.total);
        offsetRef.current = (reset ? 0 : offset) + result.sessions.length;
      } catch {
        // silently fail
      } finally {
        setLoading(false);
      }
    },
    [filterCategory]
  );

  useEffect(() => {
    offsetRef.current = 0;
    loadHistory(true);
  }, [filterCategory, loadHistory]);

  useAutoRefresh(
    useCallback(() => {
      offsetRef.current = 0;
      loadHistory(true);
    }, [loadHistory]),
    300000
  );

  const hasMore = sessions.length < total;

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* Filter */}
      <div className="px-4 py-2 border-b border-white/[0.04]">
        <select
          value={filterCategory}
          onChange={(e) => setFilterCategory(e.target.value as Category | '')}
          className="w-full bg-white/[0.03] border border-white/[0.06] rounded-lg px-3 py-1.5 text-[10px] font-mono text-gray-300 tracking-wider focus:outline-none focus:border-[#00d4ff]/30 appearance-none"
        >
          <option value="">ALL CATEGORIES</option>
          {ALL_CATEGORIES.map((cat) => (
            <option key={cat} value={cat}>
              {CATEGORY_LABELS[cat].toUpperCase()}
            </option>
          ))}
        </select>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {loading && sessions.length === 0 ? (
          <div className="flex items-center justify-center py-12 text-gray-500">
            <Clock size={16} className="animate-spin" />
          </div>
        ) : sessions.length === 0 ? (
          <div className="text-center py-12 px-4">
            <History size={24} className="mx-auto text-gray-600 mb-2" />
            <p className="text-[11px] text-gray-500 font-mono">No sessions yet.</p>
          </div>
        ) : (
          <div className="divide-y divide-white/[0.03]">
            {sessions.map((s) => (
              <div key={s.id} className="px-4 py-3 hover:bg-white/[0.02] transition-colors">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1 space-y-1">
                    <p className="text-[11px] text-gray-200 font-medium truncate">{s.title}</p>
                    <div className="flex items-center gap-2 flex-wrap">
                      <CategoryBadge category={s.category} />
                      {s.actual_duration_min != null && (
                        <span className="text-[9px] font-mono text-gray-500">
                          {formatDuration(s.actual_duration_min)}
                        </span>
                      )}
                      {s.productivity_rating != null && (
                        <DotRating value={s.productivity_rating} readonly color="#00d4ff" />
                      )}
                    </div>
                  </div>
                  <span className="text-[9px] font-mono text-gray-600 flex-shrink-0">
                    {formatDate(s.started_at)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Load more */}
        {hasMore && (
          <div className="px-4 py-3">
            <button
              onClick={() => loadHistory(false)}
              disabled={loading}
              className="w-full py-2 text-[10px] font-mono tracking-wider text-[#00d4ff] bg-white/[0.03] border border-white/[0.06] rounded-lg hover:bg-white/[0.06] transition-all disabled:opacity-40"
            >
              {loading ? 'LOADING...' : `LOAD MORE (${total - sessions.length} remaining)`}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Stats Tab ─────────────────────────────────────────────────────────

function StatsTab() {
  const [period, setPeriod] = useState<StatsPeriod>('week');
  const [stats, setStats] = useState<FocusStats | null>(null);
  const [loading, setLoading] = useState(true);

  const loadStats = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.get<FocusStats>('/focus/stats', { period });
      setStats(result);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  useAutoRefresh(loadStats, 300000);

  if (loading && !stats) {
    return (
      <div className="flex items-center justify-center py-12 text-gray-500">
        <BarChart3 size={16} className="animate-spin" />
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="text-center py-12 px-4">
        <BarChart3 size={24} className="mx-auto text-gray-600 mb-2" />
        <p className="text-[11px] text-gray-500 font-mono">No data available.</p>
      </div>
    );
  }

  // Find max hours for category bar scaling
  const maxCatHours = Math.max(
    ...Object.values(stats.by_category).map((c) => c.hours),
    0.1
  );

  return (
    <div className="flex-1 overflow-y-auto scrollbar-thin px-4 py-4 space-y-4">
      {/* Period toggle */}
      <div className="flex bg-white/[0.03] border border-white/[0.06] rounded-lg overflow-hidden">
        {(['week', 'month'] as StatsPeriod[]).map((p) => (
          <button
            key={p}
            onClick={() => setPeriod(p)}
            className={clsx(
              'flex-1 py-1.5 text-[10px] font-mono tracking-wider transition-all',
              period === p
                ? 'bg-[#00d4ff]/10 text-[#00d4ff] border-b-2 border-[#00d4ff]'
                : 'text-gray-500 hover:text-gray-300'
            )}
          >
            {p.toUpperCase()}
          </button>
        ))}
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 gap-2">
        <StatCard label="TOTAL SESSIONS" value={String(stats.total_sessions)} icon={<Target size={10} />} color="#00d4ff" />
        <StatCard label="TOTAL HOURS" value={stats.total_focus_hours.toFixed(1)} icon={<Clock size={10} />} color="#00d4ff" />
        <StatCard label="AVG SESSION" value={`${Math.round(stats.avg_session_min)}m`} icon={<Brain size={10} />} color="#f0a500" />
        <StatCard label="AVG PRODUCTIVITY" value={stats.avg_productivity ? stats.avg_productivity.toFixed(1) : '--'} icon={<Star size={10} />} color="#f0a500" />
      </div>

      {/* Extra stats row */}
      <div className="grid grid-cols-2 gap-2">
        <StatCard label="AVG ENERGY" value={stats.avg_energy ? stats.avg_energy.toFixed(1) : '--'} icon={<Zap size={10} />} color="#39ff14" />
        <StatCard label="DISTRACTIONS" value={String(stats.total_distractions)} icon={<AlertTriangle size={10} />} color="#ff4444" />
      </div>

      {/* Category breakdown */}
      <div className="space-y-2">
        <h4 className="text-[9px] font-mono text-gray-500 tracking-[0.2em]">BY CATEGORY</h4>
        <div className="space-y-2">
          {ALL_CATEGORIES.map((cat) => {
            const data = stats.by_category[cat];
            if (!data || data.sessions === 0) return null;
            const color = CATEGORY_COLORS[cat];
            const widthPct = (data.hours / maxCatHours) * 100;
            return (
              <div key={cat} className="space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-[9px] font-mono tracking-wider" style={{ color }}>
                    {CATEGORY_LABELS[cat].toUpperCase()}
                  </span>
                  <span className="text-[9px] font-mono text-gray-500">
                    {data.sessions}x / {data.hours.toFixed(1)}h
                  </span>
                </div>
                <div className="w-full h-1.5 bg-white/[0.04] rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{ width: `${widthPct}%`, backgroundColor: color }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  icon,
  color,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
  color: string;
}) {
  return (
    <div className="bg-white/[0.03] border border-white/[0.06] rounded-lg p-3 space-y-1">
      <div className="flex items-center gap-1.5">
        <span style={{ color }}>{icon}</span>
        <span className="text-[8px] font-mono text-gray-600 tracking-[0.15em]">{label}</span>
      </div>
      <p className="text-lg font-mono text-gray-200" style={{ color }}>
        {value}
      </p>
    </div>
  );
}

// ── Main Panel ────────────────────────────────────────────────────────

export default function FocusPanel() {
  const [isOpen, setIsOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<TabKey>('session');
  const [currentSession, setCurrentSession] = useState<FocusSession | null>(null);
  const [showEndForm, setShowEndForm] = useState(false);
  const [loadingSession, setLoadingSession] = useState(false);
  const [starting, setStarting] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Toggle listener
  useEffect(() => {
    const handler = () => setIsOpen((prev) => !prev);
    window.addEventListener('jarvis-focus-toggle', handler);
    return () => window.removeEventListener('jarvis-focus-toggle', handler);
  }, []);

  // Escape key
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (showEndForm) {
          setShowEndForm(false);
        } else {
          setIsOpen(false);
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [showEndForm]);

  // Load current session when panel opens
  const fetchCurrent = useCallback(async () => {
    try {
      const result = await api.get<{ session: FocusSession | null }>('/focus/current');
      setCurrentSession(result.session);
    } catch {
      // silently fail
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      setLoadingSession(true);
      fetchCurrent().finally(() => setLoadingSession(false));
      setShowEndForm(false);
      setActiveTab('session');
    }
  }, [isOpen, fetchCurrent]);

  // Auto-refresh current session every 30 seconds
  useAutoRefresh(
    useCallback(() => {
      if (isOpen) fetchCurrent();
    }, [isOpen, fetchCurrent]),
    30000
  );

  // ── Handlers ──────────────────────────────────────────────────────

  const handleStart = useCallback(
    async (data: { title: string; category: Category; planned_duration_min?: number }) => {
      setStarting(true);
      try {
        const session = await api.post<FocusSession>('/focus/start', data);
        setCurrentSession(session);
      } catch {
        // silently fail
      } finally {
        setStarting(false);
      }
    },
    []
  );

  const handleEndClick = useCallback(() => {
    setShowEndForm(true);
  }, []);

  const handleEndSubmit = useCallback(
    async (data: { notes?: string; energy_level?: number; productivity_rating?: number }) => {
      setSubmitting(true);
      try {
        await api.post<FocusSession>('/focus/end', data);
        setCurrentSession(null);
        setShowEndForm(false);
      } catch {
        // silently fail
      } finally {
        setSubmitting(false);
      }
    },
    []
  );

  const handleEndCancel = useCallback(() => {
    setShowEndForm(false);
  }, []);

  const handleDistraction = useCallback(async () => {
    try {
      await api.post('/focus/distraction');
      setCurrentSession((prev) =>
        prev ? { ...prev, distractions: prev.distractions + 1 } : null
      );
    } catch {
      // silently fail
    }
  }, []);

  const handleClose = useCallback(() => setIsOpen(false), []);

  // ── Tab content ─────────────────────────────────────────────────

  const TABS: { key: TabKey; label: string; icon: React.ReactNode }[] = [
    { key: 'session', label: 'SESSION', icon: <Target size={11} /> },
    { key: 'history', label: 'HISTORY', icon: <History size={11} /> },
    { key: 'stats', label: 'STATS', icon: <BarChart3 size={11} /> },
  ];

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
            initial={{ opacity: 0, x: -40, scale: 0.97 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: -40, scale: 0.97 }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
            className="fixed left-5 top-20 bottom-24 w-[380px] z-50 glass-heavy hud-clip flex flex-col overflow-hidden"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-jarvis-blue/10">
              <h2 className="font-display text-sm font-semibold tracking-wider text-jarvis-blue flex items-center gap-2">
                <Target size={16} />
                FOCUS
                {currentSession && (
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#00d4ff] opacity-75" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-[#00d4ff]" />
                  </span>
                )}
              </h2>
              <button
                onClick={handleClose}
                className="text-gray-500 hover:text-jarvis-blue transition-colors"
              >
                <X size={16} />
              </button>
            </div>

            {/* Tab bar */}
            <div className="flex border-b border-white/[0.04]">
              {TABS.map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  className={clsx(
                    'flex-1 flex items-center justify-center gap-1.5 py-2 text-[10px] font-mono tracking-wider transition-all border-b-2',
                    activeTab === tab.key
                      ? 'text-[#00d4ff] border-[#00d4ff]'
                      : 'text-gray-600 border-transparent hover:text-gray-400'
                  )}
                >
                  {tab.icon}
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Tab content */}
            <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
              {activeTab === 'session' && (
                <div className="flex-1 overflow-y-auto scrollbar-thin">
                  {loadingSession ? (
                    <div className="flex items-center justify-center py-12 text-gray-500">
                      <Clock size={16} className="animate-spin" />
                    </div>
                  ) : showEndForm ? (
                    <EndSessionForm
                      onSubmit={handleEndSubmit}
                      onCancel={handleEndCancel}
                      submitting={submitting}
                    />
                  ) : currentSession ? (
                    <ActiveSessionView
                      session={currentSession}
                      onEnd={handleEndClick}
                      onDistraction={handleDistraction}
                    />
                  ) : (
                    <StartSessionView onStart={handleStart} starting={starting} />
                  )}
                </div>
              )}

              {activeTab === 'history' && <HistoryTab />}
              {activeTab === 'stats' && <StatsTab />}
            </div>

            {/* Footer */}
            <div className="px-4 py-2 border-t border-white/[0.04]">
              <span className="text-[9px] text-gray-600 font-mono tracking-wider">
                FOCUS // JARVIS HUD
              </span>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
