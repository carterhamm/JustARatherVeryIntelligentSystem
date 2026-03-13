import { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  X,
  Plus,
  Trash2,
  Edit3,
  Flame,
  Check,
  Target,
  ChevronDown,
  ChevronUp,
  Shield,
  RotateCcw,
} from 'lucide-react';
import { api } from '@/services/api';
import { useAutoRefresh } from '@/hooks/useAutoRefresh';
import clsx from 'clsx';

// ── Types ──────────────────────────────────────────────────────────────

type Frequency = 'daily' | 'weekday' | 'weekly' | 'custom';

interface Habit {
  id: string;
  name: string;
  description?: string | null;
  frequency: Frequency;
  target_count: number;
  icon?: string | null;
  color?: string | null;
  is_active: boolean;
  sort_order: number;
  created_at: string;
  today_count: number;
  current_streak: number;
}

interface HabitSummary {
  total_habits: number;
  completed_today: number;
  total_today: number;
  completion_percentage: number;
  habits: Habit[];
}

interface HabitLog {
  id: string;
  habit_id: string;
  completed_at: string;
  notes?: string | null;
  value?: number | null;
}

interface HabitStats {
  habit_id: string;
  habit_name: string;
  current_streak: number;
  longest_streak: number;
  completion_rate: number;
  total_completions: number;
  last_30_days: { date: string; count: number }[];
}

interface HabitFormData {
  name: string;
  description: string;
  frequency: Frequency;
  target_count: number;
  icon: string;
  color: string;
  sort_order?: number;
}

interface UndoToast {
  habitId: string;
  logId: string;
  habitName: string;
  timeout: ReturnType<typeof setTimeout>;
}

// ── Constants ──────────────────────────────────────────────────────────

const PRESET_COLORS = [
  '#00d4ff', // jarvis-blue
  '#39ff14', // hud-green
  '#f0a500', // gold
  '#ff3b5c', // red
  '#a855f7', // purple
  '#ec4899', // pink
  '#14b8a6', // teal
  '#f97316', // orange
];

const FREQUENCY_LABELS: Record<Frequency, string> = {
  daily: 'DAILY',
  weekday: 'WEEKDAY',
  weekly: 'WEEKLY',
  custom: 'CUSTOM',
};

const DEFAULT_FORM: HabitFormData = {
  name: '',
  description: '',
  frequency: 'daily',
  target_count: 1,
  icon: '',
  color: '#00d4ff',
};

// ── Progress Ring ──────────────────────────────────────────────────────

function ProgressRing({
  current,
  target,
  color,
  size = 44,
  strokeWidth = 3,
  onClick,
}: {
  current: number;
  target: number;
  color: string;
  size?: number;
  strokeWidth?: number;
  onClick?: () => void;
}) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = Math.min(current / Math.max(target, 1), 1);
  const offset = circumference - progress * circumference;
  const completed = current >= target;

  return (
    <button
      onClick={onClick}
      className={clsx(
        'relative flex-shrink-0 transition-transform hover:scale-110 active:scale-95',
        completed && 'cursor-default'
      )}
      title={completed ? 'Completed!' : 'Log completion'}
    >
      <svg width={size} height={size} className="transform -rotate-90">
        {/* Background track */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(255,255,255,0.06)"
          strokeWidth={strokeWidth}
        />
        {/* Progress arc */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={completed ? '#39ff14' : color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-all duration-500 ease-out"
          style={{
            filter: `drop-shadow(0 0 4px ${completed ? '#39ff14' : color}40)`,
          }}
        />
      </svg>
      {/* Center content */}
      <div className="absolute inset-0 flex items-center justify-center">
        {completed ? (
          <Check size={14} className="text-[#39ff14]" />
        ) : (
          <span className="text-[9px] font-mono text-gray-400">
            {current}/{target}
          </span>
        )}
      </div>
    </button>
  );
}

// ── Mini Bar Chart (30-day) ────────────────────────────────────────────

function MiniBarChart({ data, color }: { data: { date: string; count: number }[]; color: string }) {
  const maxCount = Math.max(...data.map((d) => d.count), 1);

  return (
    <div className="flex items-end gap-[2px] h-[40px] mt-2">
      {data.map((d) => {
        const heightPct = (d.count / maxCount) * 100;
        return (
          <div
            key={d.date}
            className="flex-1 min-w-0 rounded-t-[1px] transition-all duration-200"
            style={{
              height: `${Math.max(heightPct, 2)}%`,
              backgroundColor: d.count > 0 ? color : 'rgba(255,255,255,0.04)',
              opacity: d.count > 0 ? 0.8 : 1,
            }}
            title={`${d.date}: ${d.count}`}
          />
        );
      })}
    </div>
  );
}

// ── Habit Form (Create / Edit) ─────────────────────────────────────────

function HabitForm({
  initial,
  onSubmit,
  onCancel,
  saving,
}: {
  initial: HabitFormData;
  onSubmit: (data: HabitFormData) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const [form, setForm] = useState<HabitFormData>(initial);

  const set = <K extends keyof HabitFormData>(key: K, value: HabitFormData[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) return;
    onSubmit(form);
  };

  return (
    <motion.form
      initial={{ height: 0, opacity: 0 }}
      animate={{ height: 'auto', opacity: 1 }}
      exit={{ height: 0, opacity: 0 }}
      transition={{ duration: 0.25 }}
      onSubmit={handleSubmit}
      className="overflow-hidden border-b border-white/[0.06]"
    >
      <div className="px-4 py-3 space-y-3">
        {/* Name */}
        <div>
          <label className="text-[9px] text-gray-500 font-mono tracking-wider block mb-1">NAME</label>
          <input
            type="text"
            value={form.name}
            onChange={(e) => set('name', e.target.value)}
            placeholder="e.g. Morning Workout"
            required
            className="w-full bg-white/[0.03] border border-white/[0.06] rounded px-3 py-1.5 text-sm font-mono text-gray-200 placeholder-gray-600 outline-none focus:border-[#00d4ff]/40 transition-colors"
          />
        </div>

        {/* Description */}
        <div>
          <label className="text-[9px] text-gray-500 font-mono tracking-wider block mb-1">DESCRIPTION</label>
          <textarea
            value={form.description}
            onChange={(e) => set('description', e.target.value)}
            placeholder="Optional description..."
            rows={2}
            className="w-full bg-white/[0.03] border border-white/[0.06] rounded px-3 py-1.5 text-sm font-mono text-gray-200 placeholder-gray-600 outline-none focus:border-[#00d4ff]/40 resize-none transition-colors"
          />
        </div>

        {/* Frequency + Target */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-[9px] text-gray-500 font-mono tracking-wider block mb-1">FREQUENCY</label>
            <select
              value={form.frequency}
              onChange={(e) => set('frequency', e.target.value as Frequency)}
              className="w-full bg-white/[0.03] border border-white/[0.06] rounded px-3 py-1.5 text-sm font-mono text-gray-200 outline-none focus:border-[#00d4ff]/40 appearance-none transition-colors"
            >
              <option value="daily">Daily</option>
              <option value="weekday">Weekday</option>
              <option value="weekly">Weekly</option>
              <option value="custom">Custom</option>
            </select>
          </div>
          <div>
            <label className="text-[9px] text-gray-500 font-mono tracking-wider block mb-1">TARGET</label>
            <input
              type="number"
              min={1}
              max={99}
              value={form.target_count}
              onChange={(e) => set('target_count', Math.max(1, parseInt(e.target.value) || 1))}
              className="w-full bg-white/[0.03] border border-white/[0.06] rounded px-3 py-1.5 text-sm font-mono text-gray-200 outline-none focus:border-[#00d4ff]/40 transition-colors"
            />
          </div>
        </div>

        {/* Icon */}
        <div>
          <label className="text-[9px] text-gray-500 font-mono tracking-wider block mb-1">ICON (EMOJI)</label>
          <input
            type="text"
            value={form.icon}
            onChange={(e) => set('icon', e.target.value)}
            placeholder="e.g. 💪"
            maxLength={4}
            className="w-20 bg-white/[0.03] border border-white/[0.06] rounded px-3 py-1.5 text-sm text-center outline-none focus:border-[#00d4ff]/40 transition-colors"
          />
        </div>

        {/* Color picker */}
        <div>
          <label className="text-[9px] text-gray-500 font-mono tracking-wider block mb-1">COLOR</label>
          <div className="flex items-center gap-2">
            {PRESET_COLORS.map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => set('color', c)}
                className={clsx(
                  'w-6 h-6 rounded-full border-2 transition-all',
                  form.color === c ? 'border-white scale-110' : 'border-transparent hover:border-white/30'
                )}
                style={{ backgroundColor: c }}
              />
            ))}
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 pt-1">
          <button
            type="submit"
            disabled={saving || !form.name.trim()}
            className="flex items-center gap-1.5 px-4 py-1.5 text-[11px] font-mono tracking-wider bg-[#00d4ff]/10 border border-[#00d4ff]/20 text-[#00d4ff] rounded hover:bg-[#00d4ff]/20 transition-colors disabled:opacity-40"
          >
            {saving ? (
              <span className="animate-pulse">SAVING...</span>
            ) : (
              <>
                <Check size={12} />
                SAVE
              </>
            )}
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="flex items-center gap-1.5 px-4 py-1.5 text-[11px] font-mono tracking-wider text-gray-500 hover:text-gray-300 transition-colors"
          >
            <X size={12} />
            CANCEL
          </button>
        </div>
      </div>
    </motion.form>
  );
}

// ── Habit Row ──────────────────────────────────────────────────────────

function HabitRow({
  habit,
  onLog,
  onEdit,
  onDelete,
  expandedId,
  onToggleExpand,
  stats,
  loadingStats,
}: {
  habit: Habit;
  onLog: (id: string) => void;
  onEdit: (habit: Habit) => void;
  onDelete: (id: string) => void;
  expandedId: string | null;
  onToggleExpand: (id: string) => void;
  stats: HabitStats | null;
  loadingStats: boolean;
}) {
  const color = habit.color || '#00d4ff';
  const isExpanded = expandedId === habit.id;

  return (
    <div className="border-b border-white/[0.04]">
      {/* Main row */}
      <div className="px-4 py-3 hover:bg-white/[0.02] transition-colors group">
        <div className="flex items-center gap-3">
          {/* Progress ring */}
          <ProgressRing
            current={habit.today_count}
            target={habit.target_count}
            color={color}
            onClick={() => onLog(habit.id)}
          />

          {/* Habit info — clickable to expand */}
          <button
            className="flex-1 min-w-0 text-left"
            onClick={() => onToggleExpand(habit.id)}
          >
            <div className="flex items-center gap-2">
              {habit.icon && <span className="text-sm">{habit.icon}</span>}
              <span className="text-[12px] font-medium text-gray-200 truncate">{habit.name}</span>
              <span
                className="text-[8px] font-mono tracking-wider px-1.5 py-0.5 rounded border"
                style={{
                  color: color,
                  borderColor: `${color}30`,
                  backgroundColor: `${color}10`,
                }}
              >
                {FREQUENCY_LABELS[habit.frequency]}
              </span>
            </div>
            {habit.current_streak > 0 && (
              <div className="flex items-center gap-1 mt-0.5">
                <Flame size={10} className="text-[#f0a500]" />
                <span className="text-[10px] font-mono text-[#f0a500]">{habit.current_streak}d streak</span>
              </div>
            )}
          </button>

          {/* Expand chevron */}
          <button
            onClick={() => onToggleExpand(habit.id)}
            className="text-gray-600 hover:text-gray-400 transition-colors p-1"
          >
            {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </button>

          {/* Actions (hover) */}
          <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-all">
            <button
              onClick={() => onEdit(habit)}
              className="text-gray-600 hover:text-[#00d4ff] transition-colors p-1"
              title="Edit habit"
            >
              <Edit3 size={11} />
            </button>
            <button
              onClick={() => onDelete(habit.id)}
              className="text-gray-600 hover:text-red-400 transition-colors p-1"
              title="Delete habit"
            >
              <Trash2 size={11} />
            </button>
          </div>
        </div>
      </div>

      {/* Expanded stats */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-3 pt-0">
              <div className="bg-white/[0.02] border border-white/[0.04] rounded p-3">
                {loadingStats ? (
                  <div className="text-[10px] font-mono text-gray-600 animate-pulse text-center py-2">
                    LOADING STATS...
                  </div>
                ) : stats ? (
                  <>
                    {/* Stat grid */}
                    <div className="grid grid-cols-4 gap-2 mb-2">
                      <StatCell label="STREAK" value={`${stats.current_streak}d`} color="#f0a500" />
                      <StatCell label="BEST" value={`${stats.longest_streak}d`} color="#00d4ff" />
                      <StatCell label="RATE" value={`${Math.round(stats.completion_rate)}%`} color="#39ff14" />
                      <StatCell label="TOTAL" value={`${stats.total_completions}`} color="#a855f7" />
                    </div>

                    {/* 30-day chart */}
                    {stats.last_30_days.length > 0 && (
                      <div>
                        <span className="text-[8px] font-mono text-gray-600 tracking-wider">LAST 30 DAYS</span>
                        <MiniBarChart data={stats.last_30_days} color={color} />
                      </div>
                    )}
                  </>
                ) : (
                  <div className="text-[10px] font-mono text-gray-600 text-center py-2">
                    NO STATS AVAILABLE
                  </div>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function StatCell({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="text-center">
      <div className="text-[12px] font-mono font-semibold" style={{ color }}>
        {value}
      </div>
      <div className="text-[7px] font-mono text-gray-600 tracking-wider">{label}</div>
    </div>
  );
}

// ── Undo Toast ─────────────────────────────────────────────────────────

function UndoToastBar({
  toast,
  onUndo,
  onDismiss,
}: {
  toast: UndoToast;
  onUndo: () => void;
  onDismiss: () => void;
}) {
  return (
    <motion.div
      initial={{ y: 20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      exit={{ y: 20, opacity: 0 }}
      transition={{ duration: 0.2 }}
      className="absolute bottom-4 left-4 right-4 flex items-center justify-between gap-2 px-3 py-2 bg-white/[0.06] border border-white/[0.08] rounded backdrop-blur-sm"
    >
      <span className="text-[11px] font-mono text-gray-300 truncate">
        Logged <span className="text-[#39ff14]">{toast.habitName}</span>
      </span>
      <div className="flex items-center gap-2 flex-shrink-0">
        <button
          onClick={onUndo}
          className="flex items-center gap-1 text-[10px] font-mono tracking-wider text-[#f0a500] hover:text-[#f0a500]/80 transition-colors"
        >
          <RotateCcw size={10} />
          UNDO
        </button>
        <button onClick={onDismiss} className="text-gray-600 hover:text-gray-400 transition-colors">
          <X size={10} />
        </button>
      </div>
    </motion.div>
  );
}

// ── Main Panel ─────────────────────────────────────────────────────────

export default function HabitsPanel() {
  const [isOpen, setIsOpen] = useState(false);
  const [habits, setHabits] = useState<Habit[]>([]);
  const [summary, setSummary] = useState<HabitSummary | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  // Form state
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [editingHabit, setEditingHabit] = useState<Habit | null>(null);

  // Expansion + stats
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [statsCache, setStatsCache] = useState<Record<string, HabitStats>>({});
  const [loadingStatsId, setLoadingStatsId] = useState<string | null>(null);

  // Undo toast
  const [undoToast, setUndoToast] = useState<UndoToast | null>(null);
  const undoToastRef = useRef<UndoToast | null>(null);

  // ── Toggle listener ──────────────────────────────────────────────────

  useEffect(() => {
    const handler = () => setIsOpen((prev) => !prev);
    window.addEventListener('jarvis-habits-toggle', handler);
    return () => window.removeEventListener('jarvis-habits-toggle', handler);
  }, []);

  // ── Escape key ───────────────────────────────────────────────────────

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (showCreateForm || editingHabit) {
          setShowCreateForm(false);
          setEditingHabit(null);
        } else {
          setIsOpen(false);
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [showCreateForm, editingHabit]);

  // ── Data loading ─────────────────────────────────────────────────────

  const loadHabits = useCallback(async () => {
    try {
      const result = await api.get<Habit[]>('/habits');
      setHabits(result);
    } catch {
      // silently fail
    }
  }, []);

  const loadSummary = useCallback(async () => {
    try {
      const result = await api.get<HabitSummary>('/habits/summary');
      setSummary(result);
    } catch {
      // silently fail
    }
  }, []);

  const loadAll = useCallback(async () => {
    await Promise.all([loadHabits(), loadSummary()]);
  }, [loadHabits, loadSummary]);

  // Load when panel opens
  useEffect(() => {
    if (isOpen) {
      setIsLoading(true);
      loadAll().finally(() => setIsLoading(false));
      setShowCreateForm(false);
      setEditingHabit(null);
      setExpandedId(null);
    }
  }, [isOpen, loadAll]);

  // Auto-refresh every 5 minutes
  useAutoRefresh(
    useCallback(() => {
      if (isOpen) loadAll();
    }, [isOpen, loadAll]),
    5 * 60 * 1000
  );

  // ── Stats loading ────────────────────────────────────────────────────

  const loadStats = useCallback(async (habitId: string) => {
    if (statsCache[habitId]) return;
    setLoadingStatsId(habitId);
    try {
      const result = await api.get<HabitStats>(`/habits/${habitId}/stats`);
      setStatsCache((prev) => ({ ...prev, [habitId]: result }));
    } catch {
      // silently fail
    } finally {
      setLoadingStatsId(null);
    }
  }, [statsCache]);

  const handleToggleExpand = useCallback(
    (id: string) => {
      setExpandedId((prev) => {
        const next = prev === id ? null : id;
        if (next) loadStats(id);
        return next;
      });
    },
    [loadStats]
  );

  // ── CRUD operations ──────────────────────────────────────────────────

  const handleCreate = useCallback(
    async (data: HabitFormData) => {
      setIsSaving(true);
      try {
        const body: Record<string, unknown> = {
          name: data.name.trim(),
          frequency: data.frequency,
          target_count: data.target_count,
        };
        if (data.description.trim()) body.description = data.description.trim();
        if (data.icon.trim()) body.icon = data.icon.trim();
        if (data.color) body.color = data.color;

        await api.post('/habits', body);
        setShowCreateForm(false);
        await loadAll();
      } catch {
        // silently fail
      } finally {
        setIsSaving(false);
      }
    },
    [loadAll]
  );

  const handleUpdate = useCallback(
    async (data: HabitFormData) => {
      if (!editingHabit) return;
      setIsSaving(true);
      try {
        const body: Record<string, unknown> = {
          name: data.name.trim(),
          frequency: data.frequency,
          target_count: data.target_count,
          description: data.description.trim() || null,
          icon: data.icon.trim() || null,
          color: data.color || null,
        };

        await api.put(`/habits/${editingHabit.id}`, body);
        setEditingHabit(null);
        // Invalidate stats cache for this habit
        setStatsCache((prev) => {
          const next = { ...prev };
          delete next[editingHabit.id];
          return next;
        });
        await loadAll();
      } catch {
        // silently fail
      } finally {
        setIsSaving(false);
      }
    },
    [editingHabit, loadAll]
  );

  const handleDelete = useCallback(
    async (id: string) => {
      try {
        await api.delete(`/habits/${id}`);
        setHabits((prev) => prev.filter((h) => h.id !== id));
        if (expandedId === id) setExpandedId(null);
        await loadSummary();
      } catch {
        // silently fail
      }
    },
    [expandedId, loadSummary]
  );

  // ── Log completion ───────────────────────────────────────────────────

  const dismissUndoToast = useCallback(() => {
    if (undoToastRef.current) {
      clearTimeout(undoToastRef.current.timeout);
    }
    setUndoToast(null);
    undoToastRef.current = null;
  }, []);

  const handleLog = useCallback(
    async (habitId: string) => {
      const habit = habits.find((h) => h.id === habitId);
      if (!habit) return;

      try {
        const log = await api.post<HabitLog>(`/habits/${habitId}/log`, {});

        // Update local state optimistically
        setHabits((prev) =>
          prev.map((h) =>
            h.id === habitId
              ? { ...h, today_count: h.today_count + 1 }
              : h
          )
        );
        await loadSummary();

        // Invalidate stats cache
        setStatsCache((prev) => {
          const next = { ...prev };
          delete next[habitId];
          return next;
        });
        // Reload stats if expanded
        if (expandedId === habitId) {
          loadStats(habitId);
        }

        // Show undo toast
        dismissUndoToast();
        const timeout = setTimeout(() => {
          setUndoToast(null);
          undoToastRef.current = null;
        }, 5000);
        const toast: UndoToast = {
          habitId,
          logId: log.id,
          habitName: habit.name,
          timeout,
        };
        setUndoToast(toast);
        undoToastRef.current = toast;
      } catch {
        // silently fail
      }
    },
    [habits, expandedId, loadSummary, loadStats, dismissUndoToast]
  );

  const handleUndo = useCallback(async () => {
    if (!undoToast) return;
    const { habitId, logId } = undoToast;

    try {
      await api.delete(`/habits/${habitId}/log/${logId}`);

      // Update local state
      setHabits((prev) =>
        prev.map((h) =>
          h.id === habitId
            ? { ...h, today_count: Math.max(0, h.today_count - 1) }
            : h
        )
      );
      await loadSummary();

      // Invalidate stats cache
      setStatsCache((prev) => {
        const next = { ...prev };
        delete next[habitId];
        return next;
      });
      if (expandedId === habitId) {
        loadStats(habitId);
      }
    } catch {
      // silently fail
    } finally {
      dismissUndoToast();
    }
  }, [undoToast, expandedId, loadSummary, loadStats, dismissUndoToast]);

  // ── Edit helpers ─────────────────────────────────────────────────────

  const handleStartEdit = useCallback((habit: Habit) => {
    setEditingHabit(habit);
    setShowCreateForm(false);
  }, []);

  const handleCancelForm = useCallback(() => {
    setShowCreateForm(false);
    setEditingHabit(null);
  }, []);

  const handleClose = useCallback(() => setIsOpen(false), []);

  // ── Completion percentage bar ────────────────────────────────────────

  const completionPct = summary?.completion_percentage ?? 0;

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
            {/* ── Header ──────────────────────────────────────────── */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-[#00d4ff]/10">
              <h2 className="font-display text-sm font-semibold tracking-wider text-[#00d4ff] flex items-center gap-2">
                <Shield size={16} />
                HABITS
              </h2>
              <button onClick={handleClose} className="text-gray-500 hover:text-[#00d4ff] transition-colors">
                <X size={16} />
              </button>
            </div>

            {/* ── Summary bar ─────────────────────────────────────── */}
            {summary && (
              <div className="px-4 py-2 border-b border-white/[0.04]">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-[10px] font-mono text-gray-400 tracking-wider">
                    TODAY: {summary.completed_today}/{summary.total_habits} COMPLETE
                  </span>
                  <span className="text-[10px] font-mono text-[#00d4ff]">
                    {Math.round(completionPct)}%
                  </span>
                </div>
                <div className="w-full h-[3px] bg-white/[0.04] rounded-full overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${completionPct}%` }}
                    transition={{ duration: 0.6, ease: 'easeOut' }}
                    className="h-full rounded-full"
                    style={{
                      background: `linear-gradient(90deg, #00d4ff, ${completionPct >= 100 ? '#39ff14' : '#00d4ff'})`,
                      boxShadow: `0 0 8px ${completionPct >= 100 ? '#39ff14' : '#00d4ff'}40`,
                    }}
                  />
                </div>
              </div>
            )}

            {/* ── Add habit button ────────────────────────────────── */}
            {!showCreateForm && !editingHabit && (
              <div className="px-4 py-2 border-b border-white/[0.04]">
                <button
                  onClick={() => setShowCreateForm(true)}
                  className="flex items-center gap-1.5 text-[11px] font-mono tracking-wider text-gray-500 hover:text-[#00d4ff] transition-colors"
                >
                  <Plus size={13} />
                  ADD HABIT
                </button>
              </div>
            )}

            {/* ── Create form ─────────────────────────────────────── */}
            <AnimatePresence>
              {showCreateForm && (
                <HabitForm
                  initial={DEFAULT_FORM}
                  onSubmit={handleCreate}
                  onCancel={handleCancelForm}
                  saving={isSaving}
                />
              )}
            </AnimatePresence>

            {/* ── Edit form ───────────────────────────────────────── */}
            <AnimatePresence>
              {editingHabit && (
                <HabitForm
                  initial={{
                    name: editingHabit.name,
                    description: editingHabit.description || '',
                    frequency: editingHabit.frequency,
                    target_count: editingHabit.target_count,
                    icon: editingHabit.icon || '',
                    color: editingHabit.color || '#00d4ff',
                  }}
                  onSubmit={handleUpdate}
                  onCancel={handleCancelForm}
                  saving={isSaving}
                />
              )}
            </AnimatePresence>

            {/* ── Habit list ──────────────────────────────────────── */}
            <div className="flex-1 overflow-y-auto scrollbar-thin relative">
              {isLoading && !habits.length ? (
                <div className="flex items-center justify-center py-12 text-gray-500">
                  <div className="text-[10px] font-mono animate-pulse tracking-wider">LOADING...</div>
                </div>
              ) : habits.length === 0 ? (
                <div className="text-center py-12 px-4">
                  <Target size={24} className="mx-auto text-gray-600 mb-2" />
                  <p className="text-[11px] text-gray-500 font-mono">
                    No habits yet. Tap ADD HABIT to start tracking.
                  </p>
                </div>
              ) : (
                habits.map((habit) => (
                  <HabitRow
                    key={habit.id}
                    habit={habit}
                    onLog={handleLog}
                    onEdit={handleStartEdit}
                    onDelete={handleDelete}
                    expandedId={expandedId}
                    onToggleExpand={handleToggleExpand}
                    stats={statsCache[habit.id] || null}
                    loadingStats={loadingStatsId === habit.id}
                  />
                ))
              )}

              {/* Undo toast */}
              <AnimatePresence>
                {undoToast && (
                  <UndoToastBar
                    toast={undoToast}
                    onUndo={handleUndo}
                    onDismiss={dismissUndoToast}
                  />
                )}
              </AnimatePresence>
            </div>

            {/* ── Footer ──────────────────────────────────────────── */}
            {habits.length > 0 && (
              <div className="px-4 py-2 border-t border-white/[0.04] flex items-center justify-between">
                <span className="text-[10px] text-gray-600 font-mono tracking-wider">
                  {habits.length} HABIT{habits.length !== 1 ? 'S' : ''} TRACKED
                </span>
                <span className="text-[10px] text-gray-600 font-mono tracking-wider">
                  {summary?.total_today ?? 0} LOG{(summary?.total_today ?? 0) !== 1 ? 'S' : ''} TODAY
                </span>
              </div>
            )}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
