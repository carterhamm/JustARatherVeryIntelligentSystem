import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Cloud, Sun, CloudRain, CloudSnow, CloudLightning, CloudDrizzle, Wind, Droplets,
  Calendar, Clock, ChevronRight, ExternalLink, Loader2, RefreshCw,
  Thermometer, Eye, EyeOff, MapPin,
} from 'lucide-react';
import { api } from '@/services/api';
import { useAuthStore } from '@/stores/authStore';
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

  const fetchWeather = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (coordsRef.current) {
        params.set('lat', coordsRef.current.lat.toFixed(4));
        params.set('lon', coordsRef.current.lon.toFixed(4));
      }
      const qs = params.toString();
      const res = await api.get<WeatherData>(`/widgets/weather${qs ? `?${qs}` : ''}`);
      setData(res);
    } catch {
      setData({ error: 'Failed to fetch weather' });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Wait briefly for geolocation to resolve before first fetch
    const timer = setTimeout(fetchWeather, 1500);
    const interval = setInterval(fetchWeather, 10 * 60 * 1000); // 10 min
    return () => { clearTimeout(timer); clearInterval(interval); };
  }, [fetchWeather]);

  if (loading && !data) {
    return (
      <WidgetCard label="WEATHER">
        <div className="flex items-center justify-center py-4">
          <Loader2 size={14} className="animate-spin text-jarvis-blue/50" />
        </div>
      </WidgetCard>
    );
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

  const fetchCalendar = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.get<CalendarData>('/widgets/calendar');
      setData(res);
    } catch {
      setData({ connected: false, events: [] });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCalendar();
    const interval = setInterval(fetchCalendar, 5 * 60 * 1000); // 5 min
    return () => clearInterval(interval);
  }, [fetchCalendar]);

  if (loading && !data) {
    return (
      <WidgetCard label="CALENDAR">
        <div className="flex items-center justify-center py-4">
          <Loader2 size={14} className="animate-spin text-jarvis-blue/50" />
        </div>
      </WidgetCard>
    );
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

  return (
    <WidgetCard label="TODAY" onRefresh={fetchCalendar}>
      {data.events.length === 0 ? (
        <p className="text-[10px] text-gray-600 font-mono py-1">No events today</p>
      ) : (
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
      )}
    </WidgetCard>
  );
}

// ── Google Connect Widget ──────────────────────────────────────────────

function GoogleConnectWidget() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get<SystemStatus>('/widgets/status')
      .then(setStatus)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return null;

  // Only show if Google is NOT connected
  if (status?.google_connected) return null;

  return (
    <WidgetCard label="CONNECTIONS">
      <a
        href="/connect/google"
        className="flex items-center justify-between py-1 group"
      >
        <div className="flex items-center gap-2.5">
          <div className="w-6 h-6 rounded-lg flex items-center justify-center bg-white/[0.04] border border-white/[0.06]">
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

  useEffect(() => {
    api.get<SystemStatus>('/widgets/status')
      .then(setStatus)
      .catch(() => {});
  }, []);

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

// ── Widget Card (shared wrapper) ───────────────────────────────────────

const _WIDGET_CLIP = 'polygon(0 0, calc(100% - 12px) 0, 100% 12px, 100% 100%, 12px 100%, 0 calc(100% - 12px))';

function WidgetCard({
  label,
  children,
  onRefresh,
}: {
  label: string;
  children: React.ReactNode;
  onRefresh?: () => void;
}) {
  return (
    <div className="relative px-4 py-3" style={{
      background: 'rgba(8, 12, 24, 0.45)',
      backdropFilter: 'blur(24px) saturate(1.3)',
      WebkitBackdropFilter: 'blur(24px) saturate(1.3)',
      border: '1px solid rgba(0, 212, 255, 0.06)',
      clipPath: _WIDGET_CLIP,
    }}>
      {/* Diagonal border accents at cut corners */}
      <svg className="absolute top-0 right-0 w-3 h-3 pointer-events-none" viewBox="0 0 12 12" fill="none">
        <line x1="0" y1="0" x2="12" y2="12" stroke="rgba(0,212,255,0.1)" strokeWidth="1" />
      </svg>
      <svg className="absolute bottom-0 left-0 w-3 h-3 pointer-events-none" viewBox="0 0 12 12" fill="none">
        <line x1="0" y1="0" x2="12" y2="12" stroke="rgba(0,212,255,0.1)" strokeWidth="1" />
      </svg>

      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <div className="w-1 h-1 bg-jarvis-blue/40 rotate-45" />
          <span className="hud-label text-[8px]">{label}</span>
        </div>
        {onRefresh && (
          <button
            onClick={(e) => { e.stopPropagation(); onRefresh(); }}
            className="text-gray-700 hover:text-jarvis-blue transition-colors"
          >
            <RefreshCw size={9} />
          </button>
        )}
      </div>
      {children}
    </div>
  );
}

// ── Helper ─────────────────────────────────────────────────────────────

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

// ── Main Panel ─────────────────────────────────────────────────────────

export default function WidgetPanel() {
  const panelRef = useRef<HTMLDivElement>(null);
  const token = useAuthStore((s) => s.token);
  const [visible, setVisible] = useState(true);

  // Boot animation
  useEffect(() => {
    if (panelRef.current) {
      const cards = panelRef.current.querySelectorAll('.glass');
      gsap.fromTo(
        cards,
        { opacity: 0, x: 20, scale: 0.97 },
        { opacity: 1, x: 0, scale: 1, duration: 0.4, stagger: 0.08, delay: 0.6, ease: 'power2.out' },
      );
    }
  }, []);

  // Toggle via custom event
  useEffect(() => {
    const handler = () => setVisible((v) => !v);
    window.addEventListener('jarvis-widgets-toggle', handler);
    return () => window.removeEventListener('jarvis-widgets-toggle', handler);
  }, []);

  if (!token || !visible) return null;

  return (
    <div
      ref={panelRef}
      className="fixed right-4 top-[72px] bottom-[24px] z-10 w-[260px] hidden xl:flex flex-col gap-3 overflow-y-auto py-2 pr-1 pointer-events-auto"
      style={{
        maskImage: 'linear-gradient(to bottom, transparent 0px, black 8px, black calc(100% - 8px), transparent 100%)',
        WebkitMaskImage: 'linear-gradient(to bottom, transparent 0px, black 8px, black calc(100% - 8px), transparent 100%)',
      }}
    >
      <WeatherWidget />
      <CalendarWidget />
      <GoogleConnectWidget />
      <QuickStatsWidget />
    </div>
  );
}
