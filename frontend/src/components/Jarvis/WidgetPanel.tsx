import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { useAutoRefresh } from '@/hooks/useAutoRefresh';
import {
  Cloud, Sun, CloudRain, CloudSnow, CloudLightning, CloudDrizzle, Wind, Droplets,
  Calendar, Clock, ChevronRight, ExternalLink, RefreshCw,
  Thermometer, Eye, EyeOff, MapPin, Target, Check, Flame,
  Heart, Activity, Moon, Mail, Bell, AlertTriangle, WifiOff,
} from 'lucide-react';
import { api } from '@/services/api';
import { useAuthStore } from '@/stores/authStore';
import { useUIStore } from '@/stores/uiStore';
import gsap from 'gsap';
import clsx from 'clsx';

// ── Types ──────────────────────────────────────────────────────────────

interface WeatherData {
  location?: string;
  temperature?: number;
  feels_like?: number;
  temp_min?: number;
  temp_max?: number;
  description?: string;
  humidity?: number;
  wind_speed?: number;
  clouds?: number;
  icon?: string;
  units?: string;
  forecast?: {
    date: string;
    description: string;
    temp_min: number;
    temp_max: number;
  }[];
  error?: string;
}

interface CalendarEvent {
  title: string;
  start: string;
  end: string;
  location: string;
}

interface CalendarData {
  connected: boolean;
  events: CalendarEvent[];
  error?: string;
  message?: string;
}

interface SystemStatus {
  google_connected: boolean;
  time: string;
  date: string;
  timezone: string;
  services: Record<string, boolean>;
}

interface HealthSummary {
  date: string;
  steps?: { total: number; unit: string };
  heart_rate?: { value: number; unit: string; recorded_at: string };
  sleep?: { total_hours: number; unit: string };
  workouts?: { value: number; unit: string; start: string; end: string }[];
}

interface ReminderItem {
  id: string;
  message: string;
  remind_at: string;
}

interface RemindersData {
  overdue: ReminderItem[];
  upcoming: ReminderItem[];
  overdue_count: number;
  upcoming_count: number;
  error?: string;
}

interface EmailData {
  connected: boolean;
  important: { subject: string; from: string; date?: string; snippet?: string }[];
  total_checked: number;
  // Legacy fields for backward compat
  unread_count?: number;
  recent?: { subject: string; from: string }[];
  error?: string;
}

interface WidgetLayoutItem {
  type: string;
  urgency: number;
  visible: boolean;
  data_hint?: string | null;
}

interface LayoutResponse {
  widgets: WidgetLayoutItem[];
}

// ── Urgency helpers ───────────────────────────────────────────────────

type UrgencyLevel = 'high' | 'medium' | 'low';

function getUrgencyLevel(score: number): UrgencyLevel {
  if (score >= 7.0) return 'high';
  if (score >= 4.0) return 'medium';
  return 'low';
}

function getUrgencyColor(level: UrgencyLevel): string {
  switch (level) {
    case 'high': return 'rgba(255, 59, 48, 0.7)';   // red
    case 'medium': return 'rgba(255, 149, 0, 0.6)';  // amber
    case 'low': return 'rgba(57, 255, 20, 0.3)';     // green
  }
}

function getUrgencyGlow(level: UrgencyLevel): string {
  switch (level) {
    case 'high': return '0 0 6px rgba(255, 59, 48, 0.4)';
    case 'medium': return '0 0 4px rgba(255, 149, 0, 0.3)';
    case 'low': return 'none';
  }
}

// ── Skeleton primitives ────────────────────────────────────────────────

function SkeletonLine({ className }: { className?: string }) {
  return <div className={clsx('skeleton-line', className)} />;
}

function WeatherSkeleton() {
  return (
    <WidgetCard label="WEATHER">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          {/* Icon placeholder */}
          <SkeletonLine className="w-[22px] h-[22px] rounded-full flex-shrink-0" />
          <div>
            {/* Temperature */}
            <SkeletonLine className="w-14 h-5 mb-1" />
            {/* Description */}
            <SkeletonLine className="w-20 h-2.5" />
          </div>
        </div>
        <div className="flex flex-col items-end gap-1">
          {/* Location */}
          <SkeletonLine className="w-16 h-2" />
          {/* Hi/Lo */}
          <SkeletonLine className="w-12 h-2" />
        </div>
      </div>
      {/* Detail row */}
      <div className="flex items-center gap-4 mt-2 pt-2 border-t border-white/[0.04]">
        <SkeletonLine className="w-14 h-2" />
        <SkeletonLine className="w-8 h-2" />
        <SkeletonLine className="w-12 h-2" />
      </div>
    </WidgetCard>
  );
}

function CalendarSkeleton() {
  return (
    <WidgetCard label="CALENDAR">
      <div className="space-y-1.5">
        {[0, 1, 2].map((i) => (
          <div key={i} className="flex items-start gap-2 py-1" style={{ animationDelay: `${i * 0.15}s` }}>
            <SkeletonLine className="w-0.5 h-5 flex-shrink-0 rounded-full" />
            <div className="flex-1">
              <SkeletonLine className="w-3/4 h-2.5 mb-1" />
              <SkeletonLine className="w-12 h-2" />
            </div>
          </div>
        ))}
      </div>
    </WidgetCard>
  );
}

function SubsystemsSkeleton() {
  return (
    <WidgetCard label="SUBSYSTEMS">
      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="flex items-center gap-1.5">
            <SkeletonLine className="w-1 h-1 rounded-full flex-shrink-0" />
            <SkeletonLine className="w-16 h-2" />
          </div>
        ))}
      </div>
      <div className="mt-2 pt-2 border-t border-white/[0.04]">
        <div className="flex items-center justify-between">
          <SkeletonLine className="w-10 h-2" />
          <SkeletonLine className="w-16 h-2" />
        </div>
      </div>
    </WidgetCard>
  );
}

function GenericSkeleton({ label }: { label: string }) {
  return (
    <WidgetCard label={label}>
      <div className="space-y-2 py-1">
        <SkeletonLine className="w-3/4 h-2.5" />
        <SkeletonLine className="w-1/2 h-2" />
        <SkeletonLine className="w-2/3 h-2" />
      </div>
    </WidgetCard>
  );
}

// ── Weather icon mapping ───────────────────────────────────────────────

function WeatherIcon({ description, size = 18 }: { description: string; size?: number }) {
  const desc = (description || '').toLowerCase();
  const cls = 'text-jarvis-blue';

  if (desc.includes('thunder') || desc.includes('lightning'))
    return <CloudLightning size={size} className="text-hud-amber" />;
  if (desc.includes('snow') || desc.includes('sleet'))
    return <CloudSnow size={size} className={cls} />;
  if (desc.includes('rain') || desc.includes('shower'))
    return <CloudRain size={size} className={cls} />;
  if (desc.includes('drizzle'))
    return <CloudDrizzle size={size} className={cls} />;
  if (desc.includes('clear') || desc.includes('sunny'))
    return <Sun size={size} className="text-jarvis-gold" />;
  if (desc.includes('cloud') || desc.includes('overcast'))
    return <Cloud size={size} className="text-gray-400" />;
  return <Cloud size={size} className={cls} />;
}

// ── Weather Widget ─────────────────────────────────────────────────────

function WeatherWidget() {
  const [data, setData] = useState<WeatherData | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);
  const coordsRef = useRef<{ lat: number; lon: number } | null>(null);

  // Request geolocation once on mount
  useEffect(() => {
    if ('geolocation' in navigator) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          coordsRef.current = { lat: pos.coords.latitude, lon: pos.coords.longitude };
        },
        () => { /* denied or unavailable — fall back to server-side location */ },
        { enableHighAccuracy: false, timeout: 8000, maximumAge: 600_000 },
      );
    }
  }, []);

  const hasDataRef = useRef(false);
  const fetchWeather = useCallback(async () => {
    try {
      if (!hasDataRef.current) setLoading(true);
      const params = new URLSearchParams();
      if (coordsRef.current) {
        params.set('lat', coordsRef.current.lat.toFixed(4));
        params.set('lon', coordsRef.current.lon.toFixed(4));
      }
      const qs = params.toString();
      const res = await api.get<WeatherData>(`/widgets/weather${qs ? `?${qs}` : ''}`);
      setData(res);
      hasDataRef.current = true;
    } catch {
      setData({ error: 'Failed to fetch weather' });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(fetchWeather, 1500);
    return () => clearTimeout(timer);
  }, [fetchWeather]);
  useAutoRefresh(fetchWeather, 10 * 60 * 1000); // 10 min + visibility refetch

  if (loading && !data) {
    return <WeatherSkeleton />;
  }

  if (data?.error && !data.temperature) {
    const is401 = data.error.includes('401') || data.error.includes('Unauthorized');
    return (
      <WidgetCard label="WEATHER" onRefresh={fetchWeather}>
        <p className="text-[10px] text-gray-600 font-mono py-2">
          {is401 ? 'API key activating — may take up to 2 hours' : 'Unavailable'}
        </p>
      </WidgetCard>
    );
  }

  if (!data) return null;

  return (
    <WidgetCard label="WEATHER" onRefresh={fetchWeather}>
      {/* Main weather display */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <WeatherIcon description={data.description || ''} size={22} />
            <div>
              <div className="flex items-baseline gap-1">
                <span className="text-xl font-display font-bold text-white leading-none">
                  {Math.round(data.temperature ?? 0)}°
                </span>
                <span className="text-[9px] text-gray-500 font-mono">{data.units || 'F'}</span>
              </div>
              <p className="text-[10px] text-gray-400 capitalize leading-tight mt-0.5">
                {data.description}
              </p>
            </div>
          </div>

          <div className="text-right">
            <div className="flex items-center gap-1 text-[9px] text-gray-500 font-mono">
              <MapPin size={8} />
              {data.location}
            </div>
            <p className="text-[9px] text-gray-600 font-mono mt-0.5">
              H:{Math.round(data.temp_max ?? 0)}° L:{Math.round(data.temp_min ?? 0)}°
            </p>
          </div>
        </div>

        {/* Detail row */}
        <div className="flex items-center gap-4 mt-2 pt-2 border-t border-white/[0.04]">
          <div className="flex items-center gap-1">
            <Thermometer size={9} className="text-gray-600" />
            <span className="text-[9px] text-gray-500 font-mono">
              Feels {Math.round(data.feels_like ?? 0)}°
            </span>
          </div>
          <div className="flex items-center gap-1">
            <Droplets size={9} className="text-gray-600" />
            <span className="text-[9px] text-gray-500 font-mono">{data.humidity}%</span>
          </div>
          <div className="flex items-center gap-1">
            <Wind size={9} className="text-gray-600" />
            <span className="text-[9px] text-gray-500 font-mono">{data.wind_speed} mph</span>
          </div>
        </div>
      </button>

      {/* Forecast (expanded) */}
      {expanded && data.forecast && data.forecast.length > 0 && (
        <div className="mt-2 pt-2 border-t border-white/[0.04] space-y-1.5">
          {data.forecast.map((day) => (
            <div key={day.date} className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <WeatherIcon description={day.description} size={12} />
                <span className="text-[10px] text-gray-400 font-mono w-16">{day.date}</span>
              </div>
              <span className="text-[10px] text-gray-500 font-mono capitalize flex-1 text-center truncate px-1">
                {day.description}
              </span>
              <span className="text-[10px] text-gray-400 font-mono">
                {Math.round(day.temp_max)}°/{Math.round(day.temp_min)}°
              </span>
            </div>
          ))}
        </div>
      )}
    </WidgetCard>
  );
}

// ── Calendar Widget ────────────────────────────────────────────────────

function CalendarWidget() {
  const [data, setData] = useState<CalendarData | null>(null);
  const [loading, setLoading] = useState(true);

  const calHasDataRef = useRef(false);
  const fetchCalendar = useCallback(async () => {
    try {
      if (!calHasDataRef.current) setLoading(true);
      const res = await api.get<CalendarData>('/widgets/calendar');
      setData(res);
      calHasDataRef.current = true;
    } catch {
      setData({ connected: false, events: [] });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchCalendar(); }, [fetchCalendar]);
  useAutoRefresh(fetchCalendar, 5 * 60 * 1000); // 5 min + visibility refetch

  if (loading && !data) {
    return <CalendarSkeleton />;
  }

  if (!data?.connected) {
    return (
      <WidgetCard label="CALENDAR">
        <div className="py-2 text-center">
          <Calendar size={16} className="text-gray-600 mx-auto mb-2" />
          <p className="text-[10px] text-gray-500 mb-2">Connect Google to see events</p>
          <a
            href="/connect/google"
            className="inline-flex items-center gap-1 text-[10px] text-jarvis-blue font-mono hover:underline"
          >
            Connect <ExternalLink size={8} />
          </a>
        </div>
      </WidgetCard>
    );
  }

  if (data.events.length === 0) return null;

  return (
    <WidgetCard label="TODAY" onRefresh={fetchCalendar}>
        <div className="space-y-1.5">
          {data.events.map((event, i) => {
            const startTime = formatEventTime(event.start);
            return (
              <div
                key={i}
                className="flex items-start gap-2 py-1"
              >
                <div className="w-0.5 h-full min-h-[20px] rounded-full bg-jarvis-blue/40 mt-0.5 flex-shrink-0" />
                <div className="min-w-0">
                  <p className="text-[11px] text-gray-300 truncate leading-tight">{event.title}</p>
                  <p className="text-[9px] text-gray-500 font-mono">{startTime}</p>
                </div>
              </div>
            );
          })}
        </div>
    </WidgetCard>
  );
}

// ── Google Connect Widget ──────────────────────────────────────────────

function GoogleConnectWidget() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchStatus = useCallback(() => {
    api.get<SystemStatus>('/widgets/status')
      .then(setStatus)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);
  useAutoRefresh(fetchStatus, 5 * 60 * 1000); // 5 min + visibility refetch

  if (loading) {
    return (
      <WidgetCard label="CONNECTIONS">
        <div className="flex items-center justify-between py-1">
          <div className="flex items-center gap-2.5">
            <SkeletonLine className="w-6 h-6 flex-shrink-0" />
            <div>
              <SkeletonLine className="w-14 h-2.5 mb-1" />
              <SkeletonLine className="w-24 h-2" />
            </div>
          </div>
          <SkeletonLine className="w-3 h-3" />
        </div>
      </WidgetCard>
    );
  }

  // Only show if Google is NOT connected
  if (status?.google_connected) return null;

  return (
    <WidgetCard label="CONNECTIONS">
      <a
        href="/connect/google"
        className="flex items-center justify-between py-1 group"
      >
        <div className="flex items-center gap-2.5">
          <div className="w-6 h-6 hud-clip-sm flex items-center justify-center bg-white/[0.04] border border-white/[0.06]">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none">
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/>
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
            </svg>
          </div>
          <div>
            <p className="text-[11px] text-gray-300 leading-tight">Google</p>
            <p className="text-[9px] text-gray-600 font-mono">Gmail, Calendar, Drive</p>
          </div>
        </div>
        <ChevronRight size={12} className="text-gray-600 group-hover:text-jarvis-blue transition-colors" />
      </a>
    </WidgetCard>
  );
}

// ── Quick Stats Widget ─────────────────────────────────────────────────

function QuickStatsWidget() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchStatus = useCallback(() => {
    api.get<SystemStatus>('/widgets/status')
      .then(setStatus)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);
  useAutoRefresh(fetchStatus, 5 * 60 * 1000); // 5 min + visibility refetch

  if (loading && !status) return <SubsystemsSkeleton />;
  if (!status) return null;

  const services = status.services || {};
  const activeCount = Object.values(services).filter(Boolean).length;
  const totalCount = Object.keys(services).length;

  return (
    <WidgetCard label="SUBSYSTEMS">
      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
        {Object.entries(services).map(([key, active]) => (
          <div key={key} className="flex items-center gap-1.5">
            <div
              className={clsx('w-1 h-1 rounded-full flex-shrink-0', {
                'bg-hud-green shadow-[0_0_4px_rgba(57,255,20,0.5)]': active,
                'bg-gray-600': !active,
              })}
            />
            <span className="text-[9px] text-gray-500 font-mono uppercase truncate">
              {key.replace(/_/g, ' ')}
            </span>
          </div>
        ))}
      </div>
      <div className="mt-2 pt-2 border-t border-white/[0.04]">
        <div className="flex items-center justify-between">
          <span className="text-[9px] text-gray-600 font-mono">STATUS</span>
          <span className={clsx('text-[9px] font-mono', {
            'text-hud-green': activeCount === totalCount,
            'text-hud-amber': activeCount > 0 && activeCount < totalCount,
            'text-hud-red': activeCount === 0,
          })}>
            {activeCount}/{totalCount} ONLINE
          </span>
        </div>
      </div>
    </WidgetCard>
  );
}

// ── Health Widget ─────────────────────────────────────────────────────

function HealthWidget() {
  const [data, setData] = useState<HealthSummary | null>(null);
  const [loading, setLoading] = useState(true);

  const healthHasDataRef = useRef(false);
  const fetchHealth = useCallback(async () => {
    try {
      if (!healthHasDataRef.current) setLoading(true);
      const res = await api.get<HealthSummary>('/health/summary');
      setData(res);
      healthHasDataRef.current = true;
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchHealth(); }, [fetchHealth]);
  useAutoRefresh(fetchHealth, 10 * 60 * 1000);

  if (loading && !data) return <GenericSkeleton label="HEALTH" />;

  const hasAnyData = data && (data.steps || data.heart_rate || data.sleep);

  if (!hasAnyData) return null;

  return (
    <WidgetCard label="HEALTH" onRefresh={fetchHealth}>
      <div className="space-y-2">
        {/* Steps */}
        {data.steps && (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <Activity size={10} className="text-hud-green" />
              <span className="text-[9px] text-gray-500 font-mono">STEPS</span>
            </div>
            <span className="text-[11px] text-gray-300 font-mono font-medium">
              {data.steps.total.toLocaleString()}
            </span>
          </div>
        )}

        {/* Heart Rate */}
        {data.heart_rate && (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <Heart size={10} className="text-hud-red" />
              <span className="text-[9px] text-gray-500 font-mono">HR</span>
            </div>
            <span className={clsx('text-[11px] font-mono font-medium', {
              'text-hud-red': data.heart_rate.value > 100 || data.heart_rate.value < 45,
              'text-gray-300': data.heart_rate.value <= 100 && data.heart_rate.value >= 45,
            })}>
              {data.heart_rate.value} {data.heart_rate.unit}
            </span>
          </div>
        )}

        {/* Sleep */}
        {data.sleep && (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <Moon size={10} className="text-jarvis-blue" />
              <span className="text-[9px] text-gray-500 font-mono">SLEEP</span>
            </div>
            <span className={clsx('text-[11px] font-mono font-medium', {
              'text-hud-amber': data.sleep.total_hours < 6,
              'text-gray-300': data.sleep.total_hours >= 6,
            })}>
              {data.sleep.total_hours}h
            </span>
          </div>
        )}
      </div>
    </WidgetCard>
  );
}

// ── Email Widget ──────────────────────────────────────────────────────

function EmailWidget() {
  const [data, setData] = useState<EmailData | null>(null);
  const [loading, setLoading] = useState(true);

  const emailHasDataRef = useRef(false);
  const fetchEmail = useCallback(async () => {
    try {
      if (!emailHasDataRef.current) setLoading(true);
      const res = await api.get<EmailData>('/widgets/email');
      setData(res);
      emailHasDataRef.current = true;
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchEmail(); }, [fetchEmail]);
  useAutoRefresh(fetchEmail, 10 * 60 * 1000);

  if (loading && !data) return <GenericSkeleton label="INTEL" />;

  // Do not render if Google not connected
  if (!data?.connected) return null;

  // Use new important emails format, fallback to legacy recent format
  const importantEmails = data.important ?? data.recent ?? [];

  // Hide widget if no important emails
  if (importantEmails.length === 0) return null;

  return (
    <WidgetCard label="INTEL" onRefresh={fetchEmail}>
      <div className="space-y-1.5">
        {importantEmails.slice(0, 4).map((email, i) => (
          <div key={i} className="group">
            <p className="text-[10px] text-gray-300 truncate leading-tight group-first:text-gray-200">
              {email.subject}
            </p>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className="text-[8px] text-jarvis-blue/30 font-mono truncate flex-1">
                {email.from.replace(/<[^>]+>/g, '').trim()}
              </span>
              {email.date && (
                <span className="text-[7px] text-gray-700 font-mono flex-shrink-0">
                  {(() => {
                    try {
                      const d = new Date(email.date);
                      const now = new Date();
                      const diffH = Math.floor((now.getTime() - d.getTime()) / 3600000);
                      if (diffH < 1) return 'now';
                      if (diffH < 24) return `${diffH}h`;
                      return `${Math.floor(diffH / 24)}d`;
                    } catch { return ''; }
                  })()}
                </span>
              )}
            </div>
            {i < importantEmails.length - 1 && i < 3 && (
              <div className="mt-1.5 h-px bg-white/[0.03]" />
            )}
          </div>
        ))}
      </div>
    </WidgetCard>
  );
}

// ── Reminders Widget ──────────────────────────────────────────────────

function RemindersWidget() {
  const [data, setData] = useState<RemindersData | null>(null);
  const [loading, setLoading] = useState(true);

  const remHasDataRef = useRef(false);
  const fetchReminders = useCallback(async () => {
    try {
      if (!remHasDataRef.current) setLoading(true);
      const res = await api.get<RemindersData>('/widgets/reminders');
      setData(res);
      remHasDataRef.current = true;
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchReminders(); }, [fetchReminders]);
  useAutoRefresh(fetchReminders, 2 * 60 * 1000);

  if (loading && !data) return <GenericSkeleton label="REMINDERS" />;

  const totalCount = (data?.overdue_count ?? 0) + (data?.upcoming_count ?? 0);

  if (totalCount === 0 && !data?.error) return null;

  return (
    <WidgetCard label="REMINDERS" onRefresh={fetchReminders}>
      <div className="space-y-1.5">
        {/* Overdue */}
        {data?.overdue && data.overdue.length > 0 && (
          <div className="space-y-1">
            {data.overdue.map((r) => (
              <div key={r.id} className="flex items-start gap-1.5">
                <AlertTriangle size={9} className="text-hud-red mt-0.5 flex-shrink-0" />
                <div className="min-w-0">
                  <p className="text-[10px] text-hud-red truncate leading-tight">{r.message}</p>
                  <p className="text-[8px] text-gray-600 font-mono">
                    {formatReminderTime(r.remind_at)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Upcoming */}
        {data?.upcoming && data.upcoming.length > 0 && (
          <div className={clsx('space-y-1', { 'pt-1.5 border-t border-white/[0.04]': data?.overdue && data.overdue.length > 0 })}>
            {data.upcoming.map((r) => (
              <div key={r.id} className="flex items-start gap-1.5">
                <Bell size={9} className="text-hud-amber mt-0.5 flex-shrink-0" />
                <div className="min-w-0">
                  <p className="text-[10px] text-gray-400 truncate leading-tight">{r.message}</p>
                  <p className="text-[8px] text-gray-600 font-mono">
                    {formatReminderTime(r.remind_at)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </WidgetCard>
  );
}

// ── Widget Card (shared wrapper) ───────────────────────────────────────

const _WIDGET_CLIP = 'polygon(0 0, calc(100% - 12px) 0, 100% 12px, 100% 100%, 12px 100%, 0 calc(100% - 12px))';

function WidgetCard({
  label,
  children,
  onRefresh,
  urgencyLevel,
  offline,
}: {
  label: string;
  children: React.ReactNode;
  onRefresh?: () => void;
  urgencyLevel?: UrgencyLevel;
  offline?: boolean;
}) {
  const isOnline = useUIStore((s) => s.isOnline);
  const wsConnected = useUIStore((s) => s.wsConnected);
  const isOffline = offline ?? (!isOnline || !wsConnected);
  const borderColor = urgencyLevel ? getUrgencyColor(urgencyLevel) : undefined;
  const borderGlow = urgencyLevel ? getUrgencyGlow(urgencyLevel) : undefined;

  return (
    <div
      className="relative px-4 py-3"
      style={{
        background: 'rgba(8, 12, 24, 0.45)',
        backdropFilter: 'blur(24px) saturate(1.3)',
        WebkitBackdropFilter: 'blur(24px) saturate(1.3)',
        border: '1px solid rgba(0, 212, 255, 0.18)',
        clipPath: _WIDGET_CLIP,
      }}
    >
      {/* Urgency indicator — left border stripe */}
      {urgencyLevel && (
        <div
          className="absolute left-0 top-3 bottom-3 w-[2px] rounded-full"
          style={{
            backgroundColor: borderColor,
            boxShadow: borderGlow,
            transition: 'background-color 0.4s ease, box-shadow 0.4s ease',
          }}
        />
      )}

      {/* Diagonal border accents at cut corners */}
      <svg className="absolute top-0 right-0 w-3 h-3 pointer-events-none" viewBox="0 0 12 12" fill="none">
        <line x1="0" y1="0" x2="12" y2="12" stroke="rgba(0,212,255,0.2)" strokeWidth="1" />
      </svg>
      <svg className="absolute bottom-0 left-0 w-3 h-3 pointer-events-none" viewBox="0 0 12 12" fill="none">
        <line x1="0" y1="0" x2="12" y2="12" stroke="rgba(0,212,255,0.2)" strokeWidth="1" />
      </svg>

      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <div className="w-1 h-1 bg-jarvis-blue/40 rotate-45" />
          <span className="hud-label text-[8px]">{label}</span>
          {isOffline && <WifiOff size={9} className="text-gray-600 ml-1" />}
        </div>
      </div>
      {children}
    </div>
  );
}

// ── Helpers ────────────────────────────────────────────────────────────

function formatEventTime(isoStr: string): string {
  if (!isoStr) return '';
  try {
    const d = new Date(isoStr);
    // Check if all-day (no time component)
    if (isoStr.length <= 10) return 'All day';
    return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
  } catch {
    return isoStr;
  }
}

function formatReminderTime(isoStr: string): string {
  if (!isoStr) return '';
  try {
    const d = new Date(isoStr);
    const now = new Date();
    const diffMs = d.getTime() - now.getTime();
    const diffMin = Math.round(diffMs / 60000);

    if (diffMin < 0) {
      const absMin = Math.abs(diffMin);
      if (absMin < 60) return `${absMin}m overdue`;
      if (absMin < 1440) return `${Math.round(absMin / 60)}h overdue`;
      return `${Math.round(absMin / 1440)}d overdue`;
    }
    if (diffMin < 60) return `in ${diffMin}m`;
    if (diffMin < 1440) return `in ${Math.round(diffMin / 60)}h`;
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  } catch {
    return isoStr;
  }
}

// ── Habits Widget ─────────────────────────────────────────────────────

interface HabitData {
  id: string;
  name: string;
  icon: string | null;
  color: string | null;
  target: number;
  today_count: number;
  done: boolean;
  frequency: string;
  applies_today: boolean;
}

interface HabitsData {
  total: number;
  completed: number;
  habits: HabitData[];
}

function HabitProgressRing({ done, count, target, color }: { done: boolean; count: number; target: number; color?: string | null }) {
  const size = 16;
  const stroke = 2;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.min(count / target, 1);
  const offset = circumference - pct * circumference;
  const ringColor = done ? '#39ff14' : (color || '#00d4ff');

  return (
    <svg width={size} height={size} className="flex-shrink-0">
      <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={stroke} />
      <circle
        cx={size / 2} cy={size / 2} r={radius} fill="none"
        stroke={ringColor} strokeWidth={stroke}
        strokeDasharray={circumference} strokeDashoffset={offset}
        strokeLinecap="round"
        style={{ filter: done ? `drop-shadow(0 0 3px ${ringColor}40)` : undefined }}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
      {done && (
        <path
          d={`M${size * 0.3} ${size * 0.5} L${size * 0.45} ${size * 0.65} L${size * 0.7} ${size * 0.35}`}
          stroke={ringColor}
          strokeWidth="1.5"
          fill="none"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      )}
    </svg>
  );
}

function HabitsWidget() {
  const [data, setData] = useState<HabitsData | null>(null);
  const [loading, setLoading] = useState(true);

  const habHasDataRef = useRef(false);
  const fetchHabits = useCallback(async () => {
    try {
      if (!habHasDataRef.current) setLoading(true);
      const res = await api.get<HabitsData>('/widgets/habits');
      setData(res);
      habHasDataRef.current = true;
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchHabits(); }, [fetchHabits]);
  useAutoRefresh(fetchHabits, 5 * 60 * 1000);

  if (loading && !data) {
    return (
      <WidgetCard label="HABITS">
        <div className="space-y-1.5">
          {[0, 1, 2].map((i) => (
            <div key={i} className="flex items-center gap-2 py-1">
              <div className="skeleton-line w-4 h-4 rounded flex-shrink-0" />
              <div className="skeleton-line w-20 h-2.5 flex-1" />
              <div className="skeleton-line w-6 h-2" />
            </div>
          ))}
        </div>
      </WidgetCard>
    );
  }

  if (!data || data.habits.length === 0) return null;

  const pct = data.total > 0 ? Math.round((data.completed / data.total) * 100) : 0;

  return (
    <WidgetCard label="HABITS" onRefresh={fetchHabits}>
      {/* Summary bar */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5">
          <Target size={10} className="text-jarvis-blue" />
          <span className="text-[10px] font-mono text-gray-400">
            {data.completed}/{data.total}
          </span>
        </div>
        <span className={clsx('text-[10px] font-mono font-semibold', {
          'text-hud-green': pct === 100,
          'text-hud-amber': pct > 0 && pct < 100,
          'text-gray-600': pct === 0,
        })}>
          {pct}%
        </span>
      </div>

      {/* Progress bar */}
      <div className="w-full h-1 rounded-full bg-white/[0.04] mb-2.5 overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${pct}%`,
            background: pct === 100
              ? 'linear-gradient(90deg, #39ff14, #00ff88)'
              : 'linear-gradient(90deg, #00d4ff, #0080ff)',
            boxShadow: pct === 100
              ? '0 0 8px rgba(57, 255, 20, 0.4)'
              : '0 0 6px rgba(0, 212, 255, 0.3)',
          }}
        />
      </div>

      {/* Habit list */}
      <div className="space-y-1">
        {data.habits
          .filter((h) => h.applies_today)
          .map((habit) => (
          <div key={habit.id} className="flex items-center gap-2 py-0.5">
            <HabitProgressRing
              done={habit.done}
              count={habit.today_count}
              target={habit.target}
              color={habit.color}
            />
            <span className={clsx(
              'text-[10px] font-mono flex-1 truncate',
              habit.done ? 'text-gray-500 line-through' : 'text-gray-300',
            )}>
              {habit.icon && <span className="mr-1">{habit.icon}</span>}
              {habit.name}
            </span>
            {habit.done ? (
              <Check size={10} className="text-hud-green flex-shrink-0" />
            ) : (
              <span className="text-[9px] font-mono text-gray-600 flex-shrink-0">
                {habit.today_count}/{habit.target}
              </span>
            )}
          </div>
        ))}
      </div>
    </WidgetCard>
  );
}

// ── Widget renderer (maps type string to component) ───────────────────

function renderWidget(type: string, urgencyLevel: UrgencyLevel, key: string) {
  // Wrap each widget in a container that carries the urgency indicator
  // The container provides the reorder animation target and urgency border
  switch (type) {
    case 'weather':
      return <WeatherWidget key={key} />;
    case 'calendar':
      return <CalendarWidget key={key} />;
    case 'health':
      return <HealthWidget key={key} />;
    case 'email':
      return <EmailWidget key={key} />;
    case 'reminders':
      return <RemindersWidget key={key} />;
    case 'habits':
      return <HabitsWidget key={key} />;
    case 'system':
      return <QuickStatsWidget key={key} />;
    default:
      return null;
  }
}

// ── Main Panel ─────────────────────────────────────────────────────────

function OfflineWidget() {
  return (
    <WidgetCard label="STATUS">
      <div className="flex flex-col items-center justify-center py-6 gap-3">
        <div className="w-10 h-10 rounded-full flex items-center justify-center"
          style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
          <WifiOff size={18} className="text-gray-500" />
        </div>
        <div className="text-center">
          <p className="text-[11px] font-mono text-gray-400 tracking-wider uppercase">Offline</p>
          <p className="text-[9px] text-gray-600 mt-1">Waiting for connection...</p>
        </div>
      </div>
    </WidgetCard>
  );
}

export default function WidgetPanel() {
  const panelRef = useRef<HTMLDivElement>(null);
  const token = useAuthStore((s) => s.token);
  const isOnline = useUIStore((s) => s.isOnline);
  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number } | null>(null);
  const wsConnected = useUIStore((s) => s.wsConnected);
  const [visible, setVisible] = useState(true);
  const [layout, setLayout] = useState<WidgetLayoutItem[] | null>(null);
  const [layoutReady, setLayoutReady] = useState(false);
  const prevOrderRef = useRef<string[]>([]);

  // Fetch layout from backend
  const fetchLayout = useCallback(async () => {
    try {
      const res = await api.get<LayoutResponse>('/widgets/layout');
      setLayout(res.widgets);
      setLayoutReady(true);
    } catch {
      // Fallback: show all widgets in default order
      setLayout(null);
      setLayoutReady(true);
    }
  }, []);

  useEffect(() => { if (token) fetchLayout(); }, [token, fetchLayout]);
  useAutoRefresh(fetchLayout, 3 * 60 * 1000);

  // Animate reorder when layout changes
  useEffect(() => {
    if (!panelRef.current || !layout) return;

    const currentOrder = layout.filter((w) => w.visible).map((w) => w.type);
    const prevOrder = prevOrderRef.current;

    // Only animate if order actually changed (not first load)
    if (prevOrder.length > 0 && JSON.stringify(prevOrder) !== JSON.stringify(currentOrder)) {
      const children = panelRef.current.querySelectorAll('[data-widget]');
      gsap.fromTo(
        children,
        { opacity: 0.6, y: 8 },
        { opacity: 1, y: 0, duration: 0.35, stagger: 0.05, ease: 'power2.out' },
      );
    }

    prevOrderRef.current = currentOrder;
  }, [layout]);

  // Boot animation
  useEffect(() => {
    if (panelRef.current && layoutReady) {
      const cards = panelRef.current.querySelectorAll('[data-widget]');
      gsap.fromTo(
        cards,
        { opacity: 0, x: 20, scale: 0.97 },
        { opacity: 1, x: 0, scale: 1, duration: 0.4, stagger: 0.08, delay: 0.3, ease: 'power2.out' },
      );
    }
  }, [layoutReady]);

  // Toggle via custom event
  useEffect(() => {
    const handler = () => setVisible((v) => !v);
    window.addEventListener('jarvis-widgets-toggle', handler);
    return () => window.removeEventListener('jarvis-widgets-toggle', handler);
  }, []);

  // Build the ordered, visible widget list
  const visibleWidgets = useMemo(() => {
    if (!layout) {
      // Fallback: default order when layout endpoint is unavailable
      return [
        { type: 'weather', urgency: 3, visible: true },
        { type: 'calendar', urgency: 3, visible: true },
        { type: 'health', urgency: 3, visible: true },
        { type: 'habits', urgency: 2.5, visible: true },
        { type: 'reminders', urgency: 2, visible: true },
        { type: 'system', urgency: 1.5, visible: true },
      ] as WidgetLayoutItem[];
    }
    return layout.filter((w) => w.visible);
  }, [layout]);

  if (!token || !layoutReady) return null;

  // When hidden, render invisible right-side zone for right-click to re-show
  if (!visible) {
    return (
      <>
        <div
          className="fixed right-0 top-[72px] bottom-[24px] z-10 w-[280px] hidden xl:block pointer-events-auto"
          onContextMenu={(e) => {
            e.preventDefault();
            setCtxMenu({ x: e.clientX, y: e.clientY });
          }}
        />
        {ctxMenu && createPortal(
          <div className="fixed inset-0 z-[99999]" onClick={() => setCtxMenu(null)} onContextMenu={(e) => { e.preventDefault(); setCtxMenu(null); }}>
            <div
              style={{
                position: 'fixed', left: ctxMenu.x, top: ctxMenu.y, transform: 'translate(-50%, -50%)',
                minWidth: 160, background: 'linear-gradient(to bottom right, rgba(10,10,10,0.85), rgba(10,10,10,0.95))',
                backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)',
                clipPath: 'polygon(0 0, calc(100% - 10px) 0, 100% 10px, 100% 100%, 10px 100%, 0 calc(100% - 10px))',
                border: '1px solid rgba(0,212,255,0.12)', boxShadow: '0 10px 40px rgba(0,0,0,0.5)', padding: '4px',
              }}
              onClick={(e) => e.stopPropagation()}
            >
              <button onClick={() => { setVisible(true); setCtxMenu(null); }}
                className="w-full flex items-center gap-3 px-4 py-2.5 text-left text-[12px] font-medium text-gray-300 hover:bg-white/[0.06] transition-colors">
                <Eye size={14} className="text-jarvis-blue/60" /> Show Widgets
              </button>
            </div>
          </div>,
          document.body,
        )}
      </>
    );
  }

  return (
    <div
      ref={panelRef}
      className="fixed right-4 top-[72px] bottom-[24px] z-10 w-[260px] hidden xl:flex flex-col gap-3 overflow-y-auto py-2 pr-1 pointer-events-auto"
      style={{
        maskImage: 'linear-gradient(to bottom, transparent 0px, black 8px, black calc(100% - 8px), transparent 100%)',
        WebkitMaskImage: 'linear-gradient(to bottom, transparent 0px, black 8px, black calc(100% - 8px), transparent 100%)',
      }}
    >
      {visibleWidgets.map((w) => (
        <div
          key={w.type}
          data-widget={w.type}
          style={{
            transition: 'transform 0.35s ease, opacity 0.35s ease',
          }}
          onContextMenu={(e) => {
            e.preventDefault();
            setCtxMenu({ x: e.clientX, y: e.clientY });
          }}
        >
          {renderWidget(w.type, 'low', w.type)}
        </div>
      ))}
      {(isOnline && wsConnected) && <GoogleConnectWidget />}

      {/* Widget context menu */}
      {ctxMenu && createPortal(
        <div
          className="fixed inset-0 z-[99999]"
          onClick={() => setCtxMenu(null)}
          onContextMenu={(e) => { e.preventDefault(); setCtxMenu(null); }}
        >
          <div
            style={{
              position: 'fixed',
              left: ctxMenu.x,
              top: ctxMenu.y,
              transform: 'translate(-50%, -50%)',
              minWidth: 160,
              background: 'linear-gradient(to bottom right, rgba(10, 10, 10, 0.85), rgba(10, 10, 10, 0.95))',
              backdropFilter: 'blur(20px)',
              WebkitBackdropFilter: 'blur(20px)',
              clipPath: 'polygon(0 0, calc(100% - 10px) 0, 100% 10px, 100% 100%, 10px 100%, 0 calc(100% - 10px))',
              border: '1px solid rgba(0, 212, 255, 0.12)',
              boxShadow: '0 10px 40px rgba(0,0,0,0.5)',
              padding: '4px',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => { setVisible(false); setCtxMenu(null); }}
              className="w-full flex items-center gap-3 px-4 py-2.5 text-left text-[12px] font-medium text-gray-300 hover:bg-white/[0.06] transition-colors"
            >
              <EyeOff size={14} className="text-jarvis-blue/60" />
              Hide Widgets
            </button>
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}
