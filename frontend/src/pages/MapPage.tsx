import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { useAutoRefresh } from '@/hooks/useAutoRefresh';
import { api } from '@/services/api';
import {
  ArrowLeft,
  Loader,
  MapPin,
  Users,
  Search,
  X,
  Phone,
  Mail,
  Building2,
  Globe,
  Cake,
  ChevronDown,
  ChevronUp,
  Crosshair,
  Layers,
  Plus,
  Trash2,
  Edit3,
  Navigation,
  Landmark as LandmarkIcon,
  Copy,
  ExternalLink,
  Eye,
} from 'lucide-react';
import clsx from 'clsx';

// ---------------------------------------------------------------------------
// MapKit JS types (minimal declarations)
// ---------------------------------------------------------------------------

declare global {
  interface Window {
    mapkit: any;
  }
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

// *.malibupoint.dev MapKit JS token (no expiry)
const MAPKIT_TOKEN =
  'eyJraWQiOiI1Uk1QOEJCTDVUIiwidHlwIjoiSldUIiwiYWxnIjoiRVMyNTYifQ.eyJpc3MiOiJIS004UDI5QjY4IiwiaWF0IjoxNzczMzUxNzU5LCJvcmlnaW4iOiIqLm1hbGlidXBvaW50LmRldiJ9.zVP2wOt9lp382ogCcxpfohh1TCFG9LEjSeovjuGa1LvQYAq4tQWGNM-T6-umj0K_EErdLs5-NrsRes2RXTf2ww';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Contact {
  id: string;
  first_name: string;
  last_name?: string | null;
  phone?: string | null;
  email?: string | null;
  company?: string | null;
  title?: string | null;
  address?: string | null;
  notes?: string | null;
  photo?: string | null;
  photo_content_type?: string | null;
  street?: string | null;
  city?: string | null;
  state?: string | null;
  postal_code?: string | null;
  country?: string | null;
  birthday?: string | null;
  url?: string | null;
  extra_fields?: string | null;
  created_at: string;
}

interface GeocodedContact extends Contact {
  lat: number;
  lng: number;
}

interface LandmarkData {
  id: string;
  name: string;
  description?: string | null;
  latitude: number;
  longitude: number;
  address?: string | null;
  apple_maps_url?: string | null;
  icon?: string | null;
  color?: string | null;
  created_at: string;
}

interface ContextMenuState {
  x: number;
  y: number;
  lat: number;
  lng: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const GEOCODE_CACHE_KEY = 'jarvis_geocode_cache';

function loadGeocodeCache(): Record<string, { lat: number; lng: number }> {
  try {
    const raw = localStorage.getItem(GEOCODE_CACHE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function saveGeocodeCache(cache: Record<string, { lat: number; lng: number }>) {
  try {
    localStorage.setItem(GEOCODE_CACHE_KEY, JSON.stringify(cache));
  } catch {
    // localStorage full — silently ignore
  }
}

async function geocodeAddress(
  address: string,
  cache: Record<string, { lat: number; lng: number }>,
): Promise<{ lat: number; lng: number } | null> {
  const key = address.trim().toLowerCase();
  if (cache[key]) return cache[key];

  const mk = window.mapkit;
  if (!mk) return null;

  // Use MapKit JS Geocoder (no rate limiting, no CORS issues)
  return new Promise((resolve) => {
    const geocoder = new mk.Geocoder({ language: 'en' });
    geocoder.lookup(address, (error: any, data: any) => {
      if (error || !data?.results?.length) {
        console.warn('[Map] Geocode failed:', address, error);
        resolve(null);
        return;
      }
      const result = data.results[0];
      const coords = {
        lat: result.coordinate.latitude,
        lng: result.coordinate.longitude,
      };
      cache[key] = coords;
      saveGeocodeCache(cache);
      resolve(coords);
    });
  });
}

function getInitials(contact: Contact): string {
  const first = contact.first_name?.[0] ?? '';
  const last = contact.last_name?.[0] ?? '';
  return (first + last).toUpperCase() || '?';
}

function getPhotoDataUri(contact: Contact): string | null {
  if (!contact.photo) return null;
  // Skip very short strings (likely empty/placeholder)
  if (contact.photo.length < 20) return null;
  const mime = contact.photo_content_type || 'image/jpeg';
  if (contact.photo.startsWith('data:') || contact.photo.startsWith('http')) {
    return contact.photo;
  }
  // Ensure clean base64 (no whitespace/newlines)
  const cleanBase64 = contact.photo.replace(/\s/g, '');
  return `data:${mime};base64,${cleanBase64}`;
}

function getDisplayAddress(contact: Contact): string {
  if (contact.street || contact.city || contact.state) {
    const parts = [contact.street, contact.city, contact.state, contact.postal_code].filter(Boolean);
    return parts.join(', ');
  }
  return contact.address || '';
}

function getShortLocation(contact: Contact): string {
  if (contact.city && contact.state) return `${contact.city}, ${contact.state}`;
  if (contact.city) return contact.city;
  if (contact.state) return contact.state;
  if (contact.address) {
    const parts = contact.address.split(',').map((s) => s.trim());
    return parts.slice(-2).join(', ');
  }
  return '';
}

/** Group contacts by approximate location (within ~200m) */
function groupByLocation(contacts: GeocodedContact[]): Map<string, GeocodedContact[]> {
  const groups = new Map<string, GeocodedContact[]>();
  const precision = 3; // ~111m precision
  contacts.forEach((c) => {
    const key = `${c.lat.toFixed(precision)},${c.lng.toFixed(precision)}`;
    const existing = groups.get(key) || [];
    existing.push(c);
    groups.set(key, existing);
  });
  return groups;
}

// ---------------------------------------------------------------------------
// MapKit JS loader
// ---------------------------------------------------------------------------

let mapkitLoadPromise: Promise<any> | null = null;

function loadMapKit(): Promise<any> {
  if (mapkitLoadPromise) return mapkitLoadPromise;

  mapkitLoadPromise = new Promise((resolve, reject) => {
    if (window.mapkit?.Map) {
      resolve(window.mapkit);
      return;
    }

    const script = document.createElement('script');
    script.src = 'https://cdn.apple-mapkit.com/mk/5.x.x/mapkit.js';
    script.crossOrigin = 'anonymous';
    script.onload = () => {
      try {
        window.mapkit.init({
          authorizationCallback: (done: (token: string) => void) => {
            done(MAPKIT_TOKEN);
          },
        });
        resolve(window.mapkit);
      } catch (err) {
        reject(err);
      }
    };
    script.onerror = () => reject(new Error('Failed to load MapKit JS'));
    document.head.appendChild(script);
  });

  return mapkitLoadPromise;
}

// ---------------------------------------------------------------------------
// Create custom annotation element for a contact
// ---------------------------------------------------------------------------

function createAnnotationElement(contact: Contact, count?: number): HTMLDivElement {
  const photo = getPhotoDataUri(contact);
  const initials = getInitials(contact);
  const el = document.createElement('div');
  el.style.cursor = 'pointer';
  el.style.position = 'relative';
  el.style.willChange = 'transform'; // reduce sub-pixel jitter at low zoom

  if (photo) {
    const wrapper = document.createElement('div');
    wrapper.style.cssText = 'width:44px;height:44px;border-radius:50%;background:rgba(0,20,40,0.9);border:2px solid rgba(0,212,255,0.6);box-shadow:0 0 16px rgba(0,212,255,0.3),0 4px 12px rgba(0,0,0,0.5);overflow:hidden;transition:all 0.25s ease;display:flex;align-items:center;justify-content:center;';
    const img = document.createElement('img');
    img.src = photo;
    img.alt = '';
    img.style.cssText = 'width:100%;height:100%;object-fit:cover;border-radius:50%;';
    img.onerror = () => {
      img.remove();
      const fallback = document.createElement('div');
      fallback.style.cssText = 'display:flex;align-items:center;justify-content:center;width:100%;height:100%;font-family:monospace;font-size:12px;font-weight:600;color:#00d4ff;';
      fallback.textContent = initials;
      wrapper.appendChild(fallback);
    };
    wrapper.appendChild(img);
    el.appendChild(wrapper);
  } else {
    el.innerHTML = `
      <div style="
        width: 40px; height: 40px; border-radius: 50%;
        background: rgba(0, 20, 40, 0.9);
        border: 2px solid rgba(0, 212, 255, 0.5);
        box-shadow: 0 0 14px rgba(0, 212, 255, 0.25), 0 4px 12px rgba(0,0,0,0.5);
        display: flex; align-items: center; justify-content: center;
        font-family: 'JetBrains Mono', 'Fira Code', monospace;
        font-size: 12px; font-weight: 600; color: #00d4ff;
        letter-spacing: 0.5px;
        transition: all 0.25s ease;
      ">${initials}</div>
    `;
  }

  // Add count badge for multiple people at same location
  if (count && count > 1) {
    const badge = document.createElement('div');
    badge.style.cssText = `
      position: absolute; top: -4px; right: -4px;
      min-width: 18px; height: 18px;
      background: #f0a500; border: 2px solid rgba(10, 14, 23, 0.95);
      border-radius: 9px; display: flex; align-items: center; justify-content: center;
      font-family: 'JetBrains Mono', monospace; font-size: 9px; font-weight: 700;
      color: #0A0E17; padding: 0 4px;
      box-shadow: 0 0 8px rgba(240, 165, 0, 0.4);
      z-index: 2;
    `;
    badge.textContent = String(count);
    el.appendChild(badge);
  }

  // Hover effects
  el.addEventListener('mouseenter', () => {
    const inner = el.firstElementChild as HTMLElement;
    if (inner) {
      inner.style.borderColor = 'rgba(0, 212, 255, 0.9)';
      inner.style.boxShadow = '0 0 24px rgba(0, 212, 255, 0.5), 0 4px 16px rgba(0,0,0,0.5)';
      inner.style.transform = 'scale(1.12)';
    }
  });
  el.addEventListener('mouseleave', () => {
    const inner = el.firstElementChild as HTMLElement;
    if (inner) {
      inner.style.borderColor = photo ? 'rgba(0, 212, 255, 0.6)' : 'rgba(0, 212, 255, 0.5)';
      inner.style.boxShadow = photo
        ? '0 0 16px rgba(0, 212, 255, 0.3), 0 4px 12px rgba(0,0,0,0.5)'
        : '0 0 14px rgba(0, 212, 255, 0.25), 0 4px 12px rgba(0,0,0,0.5)';
      inner.style.transform = 'scale(1)';
    }
  });

  return el;
}

// ---------------------------------------------------------------------------
// Create landmark annotation element (gold/orange style)
// ---------------------------------------------------------------------------

function createLandmarkAnnotation(landmark: LandmarkData): HTMLDivElement {
  const color = landmark.color || '#f0a500';
  const el = document.createElement('div');
  el.style.cursor = 'pointer';
  el.style.position = 'relative';
  el.style.willChange = 'transform';

  el.innerHTML = `
    <div style="
      width: 36px; height: 36px; border-radius: 50%;
      background: rgba(20, 15, 5, 0.9);
      border: 2px solid ${color}99;
      box-shadow: 0 0 14px ${color}40, 0 4px 12px rgba(0,0,0,0.5);
      display: flex; align-items: center; justify-content: center;
      transition: all 0.25s ease;
    ">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>
        <circle cx="12" cy="10" r="3"/>
      </svg>
    </div>
  `;

  el.addEventListener('mouseenter', () => {
    const inner = el.firstElementChild as HTMLElement;
    if (inner) {
      inner.style.borderColor = color;
      inner.style.boxShadow = `0 0 24px ${color}66, 0 4px 16px rgba(0,0,0,0.5)`;
      inner.style.transform = 'scale(1.12)';
    }
  });
  el.addEventListener('mouseleave', () => {
    const inner = el.firstElementChild as HTMLElement;
    if (inner) {
      inner.style.borderColor = `${color}99`;
      inner.style.boxShadow = `0 0 14px ${color}40, 0 4px 12px rgba(0,0,0,0.5)`;
      inner.style.transform = 'scale(1)';
    }
  });

  return el;
}

// ---------------------------------------------------------------------------
// Create callout (popup) element for MapKit annotation
// ---------------------------------------------------------------------------

function createCalloutElement(contact: Contact): HTMLDivElement {
  const photo = getPhotoDataUri(contact);
  const el = document.createElement('div');
  el.style.cssText =
    "font-family:'JetBrains Mono','Fira Code',monospace;min-width:200px;max-width:280px;padding:14px 16px;background:rgba(10,14,23,0.95);border:1px solid rgba(0,212,255,0.15);border-radius:6px;box-shadow:0 0 24px rgba(0,212,255,0.08),0 12px 40px rgba(0,0,0,0.6);color:#e0e0e0;backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);";

  const lines: string[] = [];

  // Header with photo
  lines.push(`<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">`);
  if (photo) {
    lines.push(
      `<img src="${photo}" alt="" style="width:36px;height:36px;border-radius:50%;object-fit:cover;border:1.5px solid rgba(0,212,255,0.4);flex-shrink:0;" onerror="this.style.display='none'" />`,
    );
  } else {
    lines.push(
      `<div style="width:36px;height:36px;border-radius:50%;background:rgba(0,20,40,0.8);border:1.5px solid rgba(0,212,255,0.3);display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:600;color:#00d4ff;flex-shrink:0;">${getInitials(contact)}</div>`,
    );
  }
  lines.push(`<div>`);
  lines.push(
    `<div style="font-size:13px;font-weight:600;color:#00d4ff;letter-spacing:0.3px;line-height:1.3;">${contact.first_name} ${contact.last_name || ''}</div>`,
  );
  if (contact.title && contact.company) {
    lines.push(
      `<div style="font-size:9px;color:#888;margin-top:1px;">${contact.title} at ${contact.company}</div>`,
    );
  } else if (contact.company) {
    lines.push(`<div style="font-size:9px;color:#888;margin-top:1px;">${contact.company}</div>`);
  }
  lines.push(`</div></div>`);

  // Divider
  lines.push(
    `<div style="height:1px;background:linear-gradient(90deg,transparent,rgba(0,212,255,0.15),transparent);margin:6px 0;"></div>`,
  );

  if (contact.phone) {
    lines.push(
      `<div style="display:flex;align-items:center;gap:6px;margin:4px 0;"><span style="color:rgba(0,212,255,0.4);font-size:9px;">TEL</span><span style="color:#ccc;font-size:10px;">${contact.phone}</span></div>`,
    );
  }
  if (contact.email) {
    lines.push(
      `<div style="display:flex;align-items:center;gap:6px;margin:4px 0;"><span style="color:rgba(0,212,255,0.4);font-size:9px;">EMAIL</span><span style="color:#ccc;font-size:10px;">${contact.email}</span></div>`,
    );
  }
  const addr = getDisplayAddress(contact);
  if (addr) {
    lines.push(
      `<div style="display:flex;align-items:flex-start;gap:6px;margin:4px 0;"><span style="color:rgba(0,212,255,0.4);font-size:9px;margin-top:1px;">LOC</span><span style="color:#999;font-size:9px;line-height:1.4;">${addr}</span></div>`,
    );
  }
  if (contact.birthday) {
    const bday = new Date(contact.birthday + 'T00:00:00');
    const bdayStr = isNaN(bday.getTime()) ? contact.birthday : bday.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
    lines.push(
      `<div style="display:flex;align-items:center;gap:6px;margin:4px 0;"><span style="color:rgba(0,212,255,0.4);font-size:9px;">BDAY</span><span style="color:#999;font-size:9px;">${bdayStr}</span></div>`,
    );
  }

  el.innerHTML = lines.join('');
  return el;
}

// ---------------------------------------------------------------------------
// Skeleton Loader
// ---------------------------------------------------------------------------

function SidebarSkeleton() {
  return (
    <div className="space-y-1 p-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 px-3 py-3">
          <div className="w-9 h-9 rounded-full skeleton-line flex-shrink-0" />
          <div className="flex-1 space-y-2">
            <div className="skeleton-line h-3 w-3/4 rounded" />
            <div className="skeleton-line h-2 w-1/2 rounded" />
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Contact Card
// ---------------------------------------------------------------------------

function ContactCard({
  contact,
  isSelected,
  isExpanded,
  onSelect,
  onToggleExpand,
}: {
  contact: GeocodedContact;
  isSelected: boolean;
  isExpanded: boolean;
  onSelect: () => void;
  onToggleExpand: () => void;
}) {
  const photo = getPhotoDataUri(contact);
  const shortLoc = getShortLocation(contact);

  return (
    <div
      className={clsx(
        'border-b border-white/[0.03] transition-all duration-200',
        isSelected && 'bg-jarvis-blue/[0.06]',
      )}
    >
      <button
        onClick={onSelect}
        className="w-full text-left px-4 py-3 flex items-center gap-3 hover:bg-white/[0.03] transition-colors"
        style={{ minHeight: '52px' }}
      >
        <div
          className={clsx(
            'w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 overflow-hidden transition-all duration-200',
          )}
          style={{
            background: photo ? 'transparent' : 'rgba(0, 20, 40, 0.8)',
            border: isSelected
              ? '2px solid rgba(0, 212, 255, 0.6)'
              : '1.5px solid rgba(0, 212, 255, 0.2)',
            boxShadow: isSelected ? '0 0 10px rgba(0, 212, 255, 0.25)' : 'none',
          }}
        >
          {photo ? (
            <img src={photo} alt="" className="w-full h-full object-cover rounded-full" onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }} />
          ) : (
            <span className="text-[10px] font-mono font-semibold text-jarvis-blue">
              {getInitials(contact)}
            </span>
          )}
        </div>

        <div className="min-w-0 flex-1">
          <p className="text-[13px] font-medium text-gray-200 truncate leading-tight">
            {contact.first_name} {contact.last_name || ''}
          </p>
          {shortLoc && (
            <p className="text-[10px] text-gray-500 truncate mt-0.5 font-mono">{shortLoc}</p>
          )}
        </div>

        <button
          onClick={(e) => {
            e.stopPropagation();
            onToggleExpand();
          }}
          className="p-1 text-gray-600 hover:text-jarvis-blue/60 transition-colors flex-shrink-0"
          aria-label={isExpanded ? 'Collapse details' : 'Expand details'}
        >
          {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </button>
      </button>

      {isExpanded && (
        <div
          className="px-4 pb-3 pl-16 space-y-1.5 animate-fade-in"
          style={{ animation: 'fadeIn 0.15s ease-out' }}
        >
          {contact.company && (
            <div className="flex items-center gap-2">
              <Building2 size={10} className="text-jarvis-blue/30 flex-shrink-0" />
              <span className="text-[10px] font-mono text-gray-400 truncate">
                {contact.title ? `${contact.title}, ` : ''}
                {contact.company}
              </span>
            </div>
          )}
          {contact.phone && (
            <div className="flex items-center gap-2">
              <Phone size={10} className="text-jarvis-blue/30 flex-shrink-0" />
              <span className="text-[10px] font-mono text-gray-400">{contact.phone}</span>
            </div>
          )}
          {contact.email && (
            <div className="flex items-center gap-2">
              <Mail size={10} className="text-jarvis-blue/30 flex-shrink-0" />
              <span className="text-[10px] font-mono text-gray-400 truncate">{contact.email}</span>
            </div>
          )}
          {contact.address && (
            <div className="flex items-start gap-2">
              <MapPin size={10} className="text-jarvis-blue/30 flex-shrink-0 mt-0.5" />
              <span className="text-[9px] font-mono text-gray-500 leading-relaxed">
                {getDisplayAddress(contact)}
              </span>
            </div>
          )}
          {contact.birthday && (
            <div className="flex items-center gap-2">
              <Cake size={10} className="text-jarvis-blue/30 flex-shrink-0" />
              <span className="text-[10px] font-mono text-gray-400">{(() => { const d = new Date(contact.birthday + 'T00:00:00'); return isNaN(d.getTime()) ? contact.birthday : d.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' }); })()}</span>
            </div>
          )}
          {contact.url && (
            <div className="flex items-center gap-2">
              <Globe size={10} className="text-jarvis-blue/30 flex-shrink-0" />
              <span className="text-[10px] font-mono text-jarvis-blue/50 truncate">
                {contact.url}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Map Controls
// ---------------------------------------------------------------------------

function MapControls({
  onResetView,
  onToggleGrid,
  gridVisible,
}: {
  onResetView: () => void;
  onToggleGrid: () => void;
  gridVisible: boolean;
}) {
  return (
    <div className="absolute bottom-24 right-4 z-10 flex flex-col gap-2">
      <button
        onClick={onResetView}
        className="glass-circle w-9 h-9 flex items-center justify-center"
        title="Reset view to fit all contacts"
        aria-label="Reset view"
      >
        <Crosshair size={14} className="text-jarvis-blue/70" />
      </button>
      <button
        onClick={onToggleGrid}
        className={clsx(
          'glass-circle w-9 h-9 flex items-center justify-center',
          gridVisible && 'active',
        )}
        title="Toggle HUD grid overlay"
        aria-label="Toggle grid"
      >
        <Layers size={14} className="text-jarvis-blue/70" />
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Look Around Panel
// ---------------------------------------------------------------------------

function LookAroundPanel({
  lat,
  lng,
  onClose,
}: {
  lat: number;
  lng: number;
  onClose: () => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const lookAroundRef = useRef<any>(null);
  const [status, setStatus] = useState<'loading' | 'active' | 'unavailable'>('loading');

  useEffect(() => {
    const mk = window.mapkit;
    if (!mk || !containerRef.current) {
      setStatus('unavailable');
      return;
    }

    // Try to initialize MapKit JS Look Around
    // If exact coords fail, search nearby roads within ~200m offsets
    try {
      if (typeof mk.LookAround !== 'function') {
        setStatus('unavailable');
        return;
      }

      let cancelled = false;
      const container = containerRef.current;

      // Try the exact coords first, then nearby offsets (~100-200m in each direction)
      const offsets = [
        [0, 0],
        [0.001, 0], [-0.001, 0], [0, 0.001], [0, -0.001],
        [0.001, 0.001], [-0.001, -0.001], [0.002, 0], [-0.002, 0],
        [0, 0.002], [0, -0.002],
      ];

      const tryLookAround = (latOff: number, lngOff: number): Promise<boolean> => {
        return new Promise((resolve) => {
          if (cancelled || !container) { resolve(false); return; }
          const coord = new mk.Coordinate(lat + latOff, lng + lngOff);
          const la = new mk.LookAround(container, coord, {
            showsDialogControl: true,
            showsCloseControl: false,
          });
          let settled = false;
          la.addEventListener('error', () => {
            if (!settled) { settled = true; la.destroy(); resolve(false); }
          });
          la.addEventListener('load', () => {
            if (!settled) { settled = true; lookAroundRef.current = la; resolve(true); }
          });
          // Timeout: if no event in 2s, assume failure and try next
          setTimeout(() => {
            if (!settled) { settled = true; la.destroy(); resolve(false); }
          }, 2000);
        });
      };

      (async () => {
        for (const [latOff, lngOff] of offsets) {
          if (cancelled) return;
          const ok = await tryLookAround(latOff, lngOff);
          if (ok) {
            if (!cancelled) setStatus('active');
            return;
          }
        }
        if (!cancelled) setStatus('unavailable');
      })();

      return () => {
        cancelled = true;
        if (lookAroundRef.current?.destroy) lookAroundRef.current.destroy();
      };
    } catch {
      setStatus('unavailable');
    }
  }, [lat, lng]);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleEsc);
    return () => document.removeEventListener('keydown', handleEsc);
  }, [onClose]);

  return createPortal(
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.7)' }}
      onClick={onClose}
    >
      <div
        className="relative w-[90vw] max-w-[900px] h-[70vh] max-h-[600px] rounded-lg overflow-hidden"
        style={{
          background: 'rgba(10, 14, 23, 0.95)',
          border: '1px solid rgba(0, 212, 255, 0.15)',
          boxShadow: '0 0 40px rgba(0, 212, 255, 0.08), 0 20px 60px rgba(0,0,0,0.6)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-4 py-2.5"
          style={{
            background: 'rgba(0, 0, 0, 0.4)',
            borderBottom: '1px solid rgba(0, 212, 255, 0.08)',
          }}
        >
          <div className="flex items-center gap-2">
            <Eye size={14} className="text-jarvis-blue/60" />
            <span className="text-[10px] font-mono tracking-[0.2em] text-jarvis-blue/60 uppercase">
              Look Around
            </span>
            <span className="text-[9px] font-mono text-gray-500">
              {lat.toFixed(5)}, {lng.toFixed(5)}
            </span>
          </div>
          <button
            onClick={onClose}
            className="w-6 h-6 flex items-center justify-center rounded-full hover:bg-white/[0.06] transition-colors"
          >
            <X size={14} className="text-jarvis-blue/40" />
          </button>
        </div>

        {/* Look Around container */}
        <div ref={containerRef} className="w-full" style={{ height: 'calc(100% - 40px)' }}>
          {status === 'loading' && (
            <div className="w-full h-full flex flex-col items-center justify-center gap-3">
              <Loader size={24} className="text-jarvis-blue/40 animate-spin" />
              <span className="text-[10px] font-mono text-gray-500 tracking-wider">
                LOADING LOOK AROUND...
              </span>
            </div>
          )}
          {status === 'unavailable' && (
            <div className="w-full h-full flex flex-col items-center justify-center gap-4">
              <Eye size={32} className="text-jarvis-blue/20" />
              <div className="text-center space-y-2">
                <p className="text-[11px] font-mono text-gray-400">
                  Look Around not available for this location
                </p>
                <p className="text-[9px] font-mono text-gray-600 max-w-sm">
                  Coverage is limited to select cities. Try a major urban area, or view in Apple Maps
                  for the full experience.
                </p>
              </div>
              <button
                onClick={() => {
                  window.open(
                    `https://maps.apple.com/?ll=${lat},${lng}&z=17&v=2`,
                    '_blank',
                  );
                }}
                className="mt-2 px-4 py-2 rounded text-[10px] font-mono tracking-wider text-jarvis-blue/70 border border-jarvis-blue/20 hover:bg-jarvis-blue/5 transition-colors"
              >
                OPEN IN APPLE MAPS
              </button>
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}

// ---------------------------------------------------------------------------
// Context Menu (glassmorphic, WagevoCRM-inspired)
// ---------------------------------------------------------------------------

function MapContextMenu({
  x,
  y,
  onAddLandmark,
  onCopyCoords,
  onOpenInAppleMaps,
  onLookAround,
  onClose,
}: {
  x: number;
  y: number;
  onAddLandmark: () => void;
  onCopyCoords: () => void;
  onOpenInAppleMaps: () => void;
  onLookAround: () => void;
  onClose: () => void;
}) {
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('mousedown', handleClick);
    document.addEventListener('keydown', handleEsc);
    return () => {
      document.removeEventListener('mousedown', handleClick);
      document.removeEventListener('keydown', handleEsc);
    };
  }, [onClose]);

  // Auto-close after 5s of inactivity
  useEffect(() => {
    let timer = setTimeout(onClose, 5000);
    const reset = () => {
      clearTimeout(timer);
      timer = setTimeout(onClose, 5000);
    };
    const el = menuRef.current;
    el?.addEventListener('mousemove', reset);
    return () => {
      clearTimeout(timer);
      el?.removeEventListener('mousemove', reset);
    };
  }, [onClose]);

  const items = [
    { icon: Eye, label: 'Look Around', onClick: onLookAround, accent: false },
    { icon: LandmarkIcon, label: 'Add Landmark', onClick: onAddLandmark, accent: false },
    { icon: Copy, label: 'Copy Coordinates', onClick: onCopyCoords, accent: false },
    { icon: ExternalLink, label: 'Open in Apple Maps', onClick: onOpenInAppleMaps, accent: false },
  ];

  return createPortal(
    <div
      ref={menuRef}
      className="animate-fade-in"
      style={{
        position: 'fixed',
        left: x,
        top: y,
        transform: 'translate(-50%, -50%)',
        zIndex: 99999,
        minWidth: 220,
        background: 'linear-gradient(to bottom right, rgba(10, 10, 10, 0.75), rgba(10, 10, 10, 0.9))',
        backdropFilter: 'blur(20px) saturate(180%)',
        WebkitBackdropFilter: 'blur(20px) saturate(180%)',
        borderRadius: 0,
        clipPath: 'polygon(0 0, calc(100% - 12px) 0, 100% 12px, 100% 100%, 12px 100%, 0 calc(100% - 12px))',
        border: '1px solid rgba(0, 212, 255, 0.12)',
        boxShadow: '0 10px 40px rgba(0,0,0,0.4), 0 0 20px rgba(0, 212, 255, 0.05)',
        padding: '6px',
        animation: 'contextMenuIn 0.15s cubic-bezier(0.175, 0.885, 0.32, 1.275) both',
      }}
      onClick={(e) => e.stopPropagation()}
    >
      {items.map((item, i) => (
        <button
          key={i}
          onClick={() => {
            item.onClick();
            onClose();
          }}
          className="w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-white/[0.06]"
        >
          <item.icon size={14} className="text-jarvis-blue/60 flex-shrink-0" />
          <span className="text-[12px] font-medium text-gray-300">{item.label}</span>
        </button>
      ))}
      <style>{`
        @keyframes contextMenuIn {
          from { opacity: 0; transform: translate(-50%, -50%) scale(0.5); }
          to { opacity: 1; transform: translate(-50%, -50%) scale(1); }
        }
      `}</style>
    </div>,
    document.body,
  );
}

// ---------------------------------------------------------------------------
// Landmark Form Modal
// ---------------------------------------------------------------------------

function LandmarkForm({
  lat,
  lng,
  onSave,
  onCancel,
}: {
  lat: number;
  lng: number;
  onSave: (data: { name: string; description: string; latitude: number; longitude: number; address: string; apple_maps_url: string }) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [address, setAddress] = useState('');
  const [appleMapsUrl, setAppleMapsUrl] = useState('');
  const [saving, setSaving] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [finalLat, setFinalLat] = useState(lat);
  const [finalLng, setFinalLng] = useState(lng);

  // Reverse geocode the coordinates to get an address
  useEffect(() => {
    const mk = window.mapkit;
    if (!mk) return;
    const geocoder = new mk.Geocoder({ language: 'en' });
    geocoder.reverseLookup(new mk.Coordinate(lat, lng), (error: any, data: any) => {
      if (!error && data?.results?.length) {
        const r = data.results[0];
        const parts = [r.name, r.locality, r.administrativeArea, r.postCode].filter(Boolean);
        setAddress(parts.join(', '));
      }
    });
  }, [lat, lng]);

  const handleSearch = async () => {
    const query = searchQuery.trim();
    if (!query) return;
    setSearching(true);

    // Check if it's an Apple Maps URL
    if (query.includes('maps.apple.com') || query.includes('apple.com/maps')) {
      try {
        const url = new URL(query);
        const ll = url.searchParams.get('ll');
        if (ll) {
          const [parsedLat, parsedLng] = ll.split(',').map(Number);
          if (!isNaN(parsedLat) && !isNaN(parsedLng)) {
            setFinalLat(parsedLat);
            setFinalLng(parsedLng);
            setAppleMapsUrl(query);
            // Reverse geocode the new coords
            const mk = window.mapkit;
            if (mk) {
              const geocoder = new mk.Geocoder({ language: 'en' });
              geocoder.reverseLookup(new mk.Coordinate(parsedLat, parsedLng), (error: any, data: any) => {
                if (!error && data?.results?.length) {
                  const r = data.results[0];
                  const parts = [r.name, r.locality, r.administrativeArea, r.postCode].filter(Boolean);
                  setAddress(parts.join(', '));
                }
              });
            }
          }
        }
      } catch {
        // not a valid URL, fall through to geocode
      }
      setSearching(false);
      return;
    }

    // Regular search — geocode the query
    const mk = window.mapkit;
    if (!mk) { setSearching(false); return; }
    const geocoder = new mk.Geocoder({ language: 'en' });
    geocoder.lookup(query, (error: any, data: any) => {
      if (!error && data?.results?.length) {
        const r = data.results[0];
        setFinalLat(r.coordinate.latitude);
        setFinalLng(r.coordinate.longitude);
        const parts = [r.name, r.locality, r.administrativeArea, r.postCode].filter(Boolean);
        setAddress(parts.join(', '));
      }
      setSearching(false);
    });
  };

  const handleSubmit = async () => {
    if (!name.trim()) return;
    setSaving(true);
    onSave({
      name: name.trim(),
      description: description.trim(),
      latitude: finalLat,
      longitude: finalLng,
      address: address.trim(),
      apple_maps_url: appleMapsUrl.trim(),
    });
  };

  return createPortal(
    <div
      className="fixed inset-0 z-[99999] flex items-center justify-center"
      style={{ background: 'rgba(0, 0, 0, 0.6)', backdropFilter: 'blur(4px)' }}
      onClick={onCancel}
    >
      <div
        className="animate-fade-in"
        style={{
          width: 400,
          maxWidth: '90vw',
          background: 'rgba(10, 14, 23, 0.97)',
          border: '1px solid rgba(0, 212, 255, 0.12)',
          borderRadius: 12,
          boxShadow: '0 20px 60px rgba(0,0,0,0.6), 0 0 30px rgba(0, 212, 255, 0.05)',
          backdropFilter: 'blur(24px)',
          padding: '24px',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-2 mb-5">
          <LandmarkIcon size={16} className="text-jarvis-gold" />
          <span className="text-[11px] font-mono font-semibold tracking-[0.15em] text-jarvis-gold uppercase">
            New Landmark
          </span>
        </div>

        {/* Search / Apple Maps URL */}
        <div className="mb-4">
          <label className="text-[9px] font-mono tracking-wider text-gray-500 uppercase mb-1.5 block">
            Search Location or Paste Apple Maps URL
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="e.g. Central Park or https://maps.apple.com/?ll=..."
              className="flex-1 py-2 px-3 text-xs font-mono bg-transparent border border-white/[0.06] rounded text-gray-300 placeholder-gray-600 focus:border-jarvis-blue/25 transition-colors"
            />
            <button
              onClick={handleSearch}
              disabled={searching}
              className="px-3 py-2 text-[10px] font-mono bg-jarvis-blue/10 border border-jarvis-blue/20 rounded text-jarvis-blue hover:bg-jarvis-blue/20 transition-colors disabled:opacity-50"
            >
              {searching ? <Loader size={12} className="animate-spin" /> : <Search size={12} />}
            </button>
          </div>
        </div>

        {/* Name */}
        <div className="mb-3">
          <label className="text-[9px] font-mono tracking-wider text-gray-500 uppercase mb-1.5 block">
            Title *
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Childhood Home, Favorite Coffee Shop"
            className="w-full py-2 px-3 text-xs font-mono bg-transparent border border-white/[0.06] rounded text-gray-300 placeholder-gray-600 focus:border-jarvis-gold/25 transition-colors"
            autoFocus
          />
        </div>

        {/* Description */}
        <div className="mb-3">
          <label className="text-[9px] font-mono tracking-wider text-gray-500 uppercase mb-1.5 block">
            Description / Context
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Tell JARVIS about this place... memories, significance, details"
            rows={3}
            className="w-full py-2 px-3 text-xs font-mono bg-transparent border border-white/[0.06] rounded text-gray-300 placeholder-gray-600 focus:border-jarvis-gold/25 transition-colors resize-none"
          />
        </div>

        {/* Address (auto-filled) */}
        <div className="mb-4">
          <label className="text-[9px] font-mono tracking-wider text-gray-500 uppercase mb-1.5 block">
            Address
          </label>
          <input
            type="text"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder="Auto-detected from coordinates..."
            className="w-full py-2 px-3 text-xs font-mono bg-transparent border border-white/[0.06] rounded text-gray-400 placeholder-gray-600 transition-colors"
          />
          <p className="text-[8px] font-mono text-gray-700 mt-1">
            {finalLat.toFixed(6)}, {finalLng.toFixed(6)}
          </p>
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-[11px] font-mono text-gray-500 hover:text-gray-300 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!name.trim() || saving}
            className="px-5 py-2 text-[11px] font-mono font-semibold bg-jarvis-gold/20 border border-jarvis-gold/30 rounded text-jarvis-gold hover:bg-jarvis-gold/30 transition-colors disabled:opacity-40"
          >
            {saving ? 'Saving...' : 'Save Landmark'}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function MapPage() {
  const navigate = useNavigate();
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null); // mapkit.Map
  const annotationsRef = useRef<any[]>([]);
  const landmarkAnnotationsRef = useRef<any[]>([]);
  const calloutOverlayRef = useRef<HTMLDivElement | null>(null);
  const calloutLayerRef = useRef<HTMLDivElement>(null);

  const [contacts, setContacts] = useState<Contact[]>([]);
  const [geocodedContacts, setGeocodedContacts] = useState<GeocodedContact[]>([]);
  const [landmarks, setLandmarks] = useState<LandmarkData[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [mapReady, setMapReady] = useState(false);
  const [geocodeProgress, setGeocodeProgress] = useState({ done: 0, total: 0 });
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedContactId, setSelectedContactId] = useState<string | null>(null);
  const [expandedContactId, setExpandedContactId] = useState<string | null>(null);
  const [gridVisible, setGridVisible] = useState(false);
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const [landmarkForm, setLandmarkForm] = useState<{ lat: number; lng: number } | null>(null);
  const [lookAroundCoords, setLookAroundCoords] = useState<{ lat: number; lng: number } | null>(null);

  // ---- Load MapKit JS + initialize map ----
  useEffect(() => {
    if (!mapContainerRef.current) return;

    let cancelled = false;

    (async () => {
      try {
        const mk = await loadMapKit();
        if (cancelled || !mapContainerRef.current) return;

        const map = new mk.Map(mapContainerRef.current, {
          center: new mk.Coordinate(40.2969, -111.6946), // Orem, Utah
          mapType: mk.Map.MapTypes.Standard,
          colorScheme: mk.Map.ColorSchemes.Dark,
          showsCompass: mk.FeatureVisibility.Hidden,
          showsZoomControl: true,
          showsMapTypeControl: false,
          showsPointsOfInterest: true,
          isZoomEnabled: true,
          isScrollEnabled: true,
          isRotationEnabled: true,
          cameraZoomRange: new mk.CameraZoomRange(200, 20000000),
          padding: new mk.Padding(0, 0, 0, 0),
        });

        mapRef.current = map;

        // Dismiss contact callout when map pans/zooms (prevents "sticking")
        map.addEventListener('region-change-start', () => {
          if (calloutOverlayRef.current) {
            calloutOverlayRef.current.remove();
            calloutOverlayRef.current = null;
          }
        });

        if (!cancelled) setMapReady(true);
      } catch (err) {
        console.error('[MapKit] Init failed:', err);
      }
    })();

    return () => {
      cancelled = true;
      if (mapRef.current) {
        mapRef.current.destroy();
        mapRef.current = null;
      }
      annotationsRef.current = [];
      landmarkAnnotationsRef.current = [];
    };
  }, []);

  // ---- Right-click context menu handler ----
  useEffect(() => {
    const container = mapContainerRef.current;
    if (!container || !mapReady) return;

    const handler = (e: MouseEvent) => {
      e.preventDefault();
      const map = mapRef.current;
      const mk = window.mapkit;
      if (!map || !mk) return;

      const rect = container.getBoundingClientRect();
      const point = new DOMPoint(e.clientX - rect.left, e.clientY - rect.top);
      const coord = map.convertPointOnPageToCoordinate(new DOMPoint(e.clientX, e.clientY));

      setContextMenu({
        x: e.clientX,
        y: e.clientY,
        lat: coord.latitude,
        lng: coord.longitude,
      });
    };

    container.addEventListener('contextmenu', handler);
    return () => container.removeEventListener('contextmenu', handler);
  }, [mapReady]);

  // ---- Fetch contacts + landmarks ----
  const fetchMapData = useCallback(async () => {
    try {
      const [contactResult, landmarkResult] = await Promise.allSettled([
        api.get<Contact[]>('/contacts', { offset: 0, limit: 200 }),
        api.get<LandmarkData[]>('/landmarks'),
      ]);
      if (contactResult.status === 'fulfilled') setContacts(contactResult.value);
      if (landmarkResult.status === 'fulfilled') setLandmarks(landmarkResult.value);
    } catch {
      // silently fail
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    setIsLoading(true);
    fetchMapData();
  }, [fetchMapData]);
  useAutoRefresh(fetchMapData, 5 * 60 * 1000); // 5 min + visibility refetch

  // ---- Geocode contacts with addresses (waits for MapKit) ----
  useEffect(() => {
    if (contacts.length === 0 || !mapReady) return;
    let cancelled = false;

    const withAddress = contacts.filter((c) => c.address?.trim() || (c.street && c.city));
    setGeocodeProgress({ done: 0, total: withAddress.length });

    (async () => {
      const cache = loadGeocodeCache();
      const results: GeocodedContact[] = [];

      for (let i = 0; i < withAddress.length; i++) {
        if (cancelled) return;
        const c = withAddress[i];
        const addrToGeocode =
          c.address?.trim() ||
          [c.street, c.city, c.state, c.postal_code].filter(Boolean).join(', ');
        const coords = await geocodeAddress(addrToGeocode, cache);
        if (coords) {
          results.push({ ...c, lat: coords.lat, lng: coords.lng });
        }
        if (!cancelled) {
          setGeocodeProgress({ done: i + 1, total: withAddress.length });
        }
      }
      // Set all geocoded contacts at once to avoid flickering
      // (each setState triggers annotation removal + re-add)
      if (!cancelled) {
        setGeocodedContacts([...results]);
      }
    })();

    return () => { cancelled = true; };
  }, [contacts, mapReady]);

  // ---- Place contact annotations when geocoded contacts update ----
  useEffect(() => {
    const map = mapRef.current;
    const mk = window.mapkit;
    if (!map || !mk || !mapReady) return;

    // Remove existing contact annotations
    if (annotationsRef.current.length > 0) {
      map.removeAnnotations(annotationsRef.current);
      annotationsRef.current = [];
    }

    // Remove old callout overlay
    if (calloutOverlayRef.current) {
      calloutOverlayRef.current.remove();
      calloutOverlayRef.current = null;
    }

    // Group contacts by approximate location for badge counts
    const locationGroups = groupByLocation(geocodedContacts);
    const countByKey = new Map<string, number>();
    locationGroups.forEach((group, key) => {
      countByKey.set(key, group.length);
    });

    const newAnnotations: any[] = [];

    geocodedContacts.forEach((c) => {
      const coord = new mk.Coordinate(c.lat, c.lng);
      const locKey = `${c.lat.toFixed(3)},${c.lng.toFixed(3)}`;
      const count = countByKey.get(locKey) || 1;

      const annotation = new mk.Annotation(coord, () => {
        return createAnnotationElement(c, count);
      }, {
        anchorOffset: new DOMPoint(0, -20),
        calloutEnabled: false,
        data: { contactId: c.id },
      });

      // Click handler — show custom callout
      annotation.addEventListener('select', () => {
        setSelectedContactId(c.id);

        // Remove existing callout
        if (calloutOverlayRef.current) {
          calloutOverlayRef.current.remove();
          calloutOverlayRef.current = null;
        }

        // Create callout overlay
        const callout = createCalloutElement(c);
        callout.style.position = 'absolute';
        callout.style.zIndex = '1000';
        callout.style.pointerEvents = 'auto';

        // Add close button
        const closeBtn = document.createElement('button');
        closeBtn.innerHTML = '&times;';
        closeBtn.style.cssText =
          'position:absolute;top:4px;right:8px;background:none;border:none;color:rgba(0,212,255,0.4);font-size:18px;cursor:pointer;padding:4px;line-height:1;';
        closeBtn.addEventListener('mouseenter', () => {
          closeBtn.style.color = '#00d4ff';
        });
        closeBtn.addEventListener('mouseleave', () => {
          closeBtn.style.color = 'rgba(0,212,255,0.4)';
        });
        closeBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          callout.remove();
          calloutOverlayRef.current = null;
          map.selectedAnnotation = null;
        });
        callout.appendChild(closeBtn);

        // Add "Look Around" footer button
        const footer = document.createElement('div');
        footer.style.cssText = 'margin-top:8px;padding-top:6px;border-top:1px solid rgba(0,212,255,0.06);display:flex;justify-content:flex-end;';
        const laBtn = document.createElement('button');
        laBtn.style.cssText = 'display:flex;align-items:center;gap:4px;font-family:monospace;font-size:9px;color:rgba(0,212,255,0.5);background:none;border:none;cursor:pointer;padding:2px 4px;transition:color 0.2s;';
        laBtn.innerHTML = `<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>LOOK AROUND`;
        laBtn.addEventListener('mouseenter', () => { laBtn.style.color = '#00d4ff'; });
        laBtn.addEventListener('mouseleave', () => { laBtn.style.color = 'rgba(0,212,255,0.5)'; });
        laBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          setLookAroundCoords({ lat: c.lat, lng: c.lng });
        });
        footer.appendChild(laBtn);
        callout.appendChild(footer);

        // Position callout in the overlay layer (above sidebar z-index)
        const layer = calloutLayerRef.current;
        const mapContainer = mapContainerRef.current;
        if (layer && mapContainer) {
          layer.appendChild(callout);
          const point = map.convertCoordinateToPointOnPage(coord);
          const containerRect = mapContainer.getBoundingClientRect();
          const calloutRect = callout.getBoundingClientRect();
          const cw = calloutRect.width;
          const ch = calloutRect.height;
          const pad = 8;

          // Initial position: centered above the pin
          let left = point.x - containerRect.left - cw / 2;
          let top = point.y - containerRect.top - ch - 24;

          // Clamp within container bounds
          left = Math.max(pad, Math.min(left, containerRect.width - cw - pad));
          top = Math.max(pad, Math.min(top, containerRect.height - ch - pad));

          // If callout would overlap the pin (not enough room above), show below
          if (point.y - containerRect.top - ch - 24 < pad) {
            top = point.y - containerRect.top + 30;
          }

          callout.style.left = `${left}px`;
          callout.style.top = `${top}px`;
          calloutOverlayRef.current = callout;
        }
      });

      annotation.addEventListener('deselect', () => {
        if (calloutOverlayRef.current) {
          calloutOverlayRef.current.remove();
          calloutOverlayRef.current = null;
        }
      });

      newAnnotations.push(annotation);
    });

    map.addAnnotations(newAnnotations);
    annotationsRef.current = newAnnotations;

    // Fit bounds
    if (geocodedContacts.length > 0) {
      const region = regionFromContacts(geocodedContacts);
      map.setRegionAnimated(region, true);
    }
  }, [geocodedContacts, mapReady]);

  // ---- Place landmark annotations ----
  useEffect(() => {
    const map = mapRef.current;
    const mk = window.mapkit;
    if (!map || !mk || !mapReady) return;

    // Remove existing landmark annotations
    if (landmarkAnnotationsRef.current.length > 0) {
      map.removeAnnotations(landmarkAnnotationsRef.current);
      landmarkAnnotationsRef.current = [];
    }

    const newAnnotations: any[] = [];

    landmarks.forEach((lm) => {
      const coord = new mk.Coordinate(lm.latitude, lm.longitude);

      const annotation = new mk.Annotation(coord, () => {
        return createLandmarkAnnotation(lm);
      }, {
        anchorOffset: new DOMPoint(0, -18),
        calloutEnabled: false,
        data: { landmarkId: lm.id },
      });

      // Click handler — show landmark callout
      annotation.addEventListener('select', () => {
        if (calloutOverlayRef.current) {
          calloutOverlayRef.current.remove();
          calloutOverlayRef.current = null;
        }

        const el = document.createElement('div');
        const color = lm.color || '#f0a500';
        el.style.cssText = `font-family:'JetBrains Mono','Fira Code',monospace;min-width:200px;max-width:300px;padding:14px 16px;background:rgba(10,14,23,0.95);border:1px solid ${color}22;border-radius:6px;box-shadow:0 0 24px ${color}10,0 12px 40px rgba(0,0,0,0.6);color:#e0e0e0;backdrop-filter:blur(20px);position:absolute;z-index:1000;pointer-events:auto;`;

        let html = `<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
          <span style="font-size:13px;font-weight:600;color:${color};letter-spacing:0.3px;">${lm.name}</span>
        </div>`;
        if (lm.description) {
          html += `<div style="font-size:10px;color:#999;line-height:1.5;margin-bottom:6px;white-space:pre-wrap;">${lm.description}</div>`;
        }
        if (lm.address) {
          html += `<div style="display:flex;align-items:flex-start;gap:6px;margin:4px 0;"><span style="color:${color}66;font-size:9px;margin-top:1px;">LOC</span><span style="color:#888;font-size:9px;line-height:1.4;">${lm.address}</span></div>`;
        }

        // Delete button
        html += `<div style="margin-top:8px;padding-top:6px;border-top:1px solid rgba(255,255,255,0.04);display:flex;justify-content:flex-end;">
          <button id="lm-delete-${lm.id}" style="font-family:monospace;font-size:9px;color:#ff4444;background:none;border:none;cursor:pointer;padding:2px 6px;">DELETE</button>
        </div>`;

        // Close button
        const closeBtn = document.createElement('button');
        closeBtn.innerHTML = '&times;';
        closeBtn.style.cssText = `position:absolute;top:4px;right:8px;background:none;border:none;color:${color}66;font-size:18px;cursor:pointer;padding:4px;line-height:1;`;
        closeBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          el.remove();
          calloutOverlayRef.current = null;
          map.selectedAnnotation = null;
        });

        el.innerHTML = html;
        el.appendChild(closeBtn);

        // Wire delete button
        setTimeout(() => {
          const delBtn = el.querySelector(`#lm-delete-${lm.id}`);
          if (delBtn) {
            delBtn.addEventListener('click', async () => {
              try {
                await api.delete(`/landmarks/${lm.id}`);
                setLandmarks((prev) => prev.filter((l) => l.id !== lm.id));
                el.remove();
                calloutOverlayRef.current = null;
              } catch (err) {
                console.error('Failed to delete landmark:', err);
              }
            });
          }
        }, 0);

        const mapContainer = mapContainerRef.current;
        if (mapContainer) {
          const point = map.convertCoordinateToPointOnPage(coord);
          const rect = mapContainer.getBoundingClientRect();
          el.style.left = `${point.x - rect.left - 140}px`;
          el.style.top = `${point.y - rect.top - 180}px`;
          mapContainer.appendChild(el);
          calloutOverlayRef.current = el;
        }
      });

      annotation.addEventListener('deselect', () => {
        if (calloutOverlayRef.current) {
          calloutOverlayRef.current.remove();
          calloutOverlayRef.current = null;
        }
      });

      newAnnotations.push(annotation);
    });

    map.addAnnotations(newAnnotations);
    landmarkAnnotationsRef.current = newAnnotations;
  }, [landmarks, mapReady]);

  // Helper: compute region from contacts
  function regionFromContacts(contacts: GeocodedContact[]) {
    const mk = window.mapkit;
    if (contacts.length === 0) {
      return new mk.CoordinateRegion(
        new mk.Coordinate(40.2969, -111.6946),
        new mk.CoordinateSpan(5, 5),
      );
    }

    let minLat = 90,
      maxLat = -90,
      minLng = 180,
      maxLng = -180;
    contacts.forEach((c) => {
      if (c.lat < minLat) minLat = c.lat;
      if (c.lat > maxLat) maxLat = c.lat;
      if (c.lng < minLng) minLng = c.lng;
      if (c.lng > maxLng) maxLng = c.lng;
    });
    // Also include landmarks in bounds
    landmarks.forEach((lm) => {
      if (lm.latitude < minLat) minLat = lm.latitude;
      if (lm.latitude > maxLat) maxLat = lm.latitude;
      if (lm.longitude < minLng) minLng = lm.longitude;
      if (lm.longitude > maxLng) maxLng = lm.longitude;
    });

    const centerLat = (minLat + maxLat) / 2;
    const centerLng = (minLng + maxLng) / 2;
    const spanLat = Math.max(maxLat - minLat, 0.01) * 1.4;
    const spanLng = Math.max(maxLng - minLng, 0.01) * 1.4;

    return new mk.CoordinateRegion(
      new mk.Coordinate(centerLat, centerLng),
      new mk.CoordinateSpan(spanLat, spanLng),
    );
  }

  // ---- Fly to contact ----
  const flyToContact = useCallback(
    (contact: GeocodedContact) => {
      const map = mapRef.current;
      const mk = window.mapkit;
      if (!map || !mk) return;

      setSelectedContactId(contact.id);

      const region = new mk.CoordinateRegion(
        new mk.Coordinate(contact.lat, contact.lng),
        new mk.CoordinateSpan(0.02, 0.02),
      );
      map.setRegionAnimated(region, true);

      const ann = annotationsRef.current.find((a) => a.data?.contactId === contact.id);
      if (ann) {
        map.selectedAnnotation = ann;
      }
    },
    [],
  );

  // ---- Reset view ----
  const resetView = useCallback(() => {
    const map = mapRef.current;
    if (!map || geocodedContacts.length === 0) return;
    const region = regionFromContacts(geocodedContacts);
    map.setRegionAnimated(region, true);
    setSelectedContactId(null);
    if (calloutOverlayRef.current) {
      calloutOverlayRef.current.remove();
      calloutOverlayRef.current = null;
    }
  }, [geocodedContacts, landmarks]);

  // ---- Save landmark ----
  const saveLandmark = useCallback(async (data: { name: string; description: string; latitude: number; longitude: number; address: string; apple_maps_url: string }) => {
    try {
      const result = await api.post<LandmarkData>('/landmarks', data);
      setLandmarks((prev) => [...prev, result]);
      setLandmarkForm(null);
    } catch (err) {
      console.error('Failed to save landmark:', err);
      setLandmarkForm(null);
    }
  }, []);

  // ---- Context menu actions ----
  const handleAddLandmark = useCallback(() => {
    if (contextMenu) {
      setLandmarkForm({ lat: contextMenu.lat, lng: contextMenu.lng });
    }
  }, [contextMenu]);

  const handleCopyCoords = useCallback(() => {
    if (contextMenu) {
      navigator.clipboard.writeText(`${contextMenu.lat.toFixed(6)}, ${contextMenu.lng.toFixed(6)}`);
    }
  }, [contextMenu]);

  const handleOpenInAppleMaps = useCallback(() => {
    if (contextMenu) {
      window.open(`https://maps.apple.com/?ll=${contextMenu.lat},${contextMenu.lng}&z=15`, '_blank');
    }
  }, [contextMenu]);

  const handleLookAround = useCallback(() => {
    if (contextMenu) {
      setLookAroundCoords({ lat: contextMenu.lat, lng: contextMenu.lng });
    }
  }, [contextMenu]);

  // ---- Filtered contacts for sidebar ----
  const filteredContacts = useMemo(() => {
    if (!searchQuery.trim()) return geocodedContacts;
    const q = searchQuery.toLowerCase();
    return geocodedContacts.filter(
      (c) =>
        c.first_name.toLowerCase().includes(q) ||
        (c.last_name?.toLowerCase().includes(q) ?? false) ||
        (c.company?.toLowerCase().includes(q) ?? false) ||
        (c.address?.toLowerCase().includes(q) ?? false) ||
        (c.city?.toLowerCase().includes(q) ?? false) ||
        (c.state?.toLowerCase().includes(q) ?? false),
    );
  }, [searchQuery, geocodedContacts]);

  const contactsWithAddress = useMemo(
    () => contacts.filter((c) => c.address?.trim() || (c.street && c.city)),
    [contacts],
  );
  const contactsWithoutAddress = useMemo(
    () => contacts.filter((c) => !c.address?.trim() && !(c.street && c.city)),
    [contacts],
  );

  const isGeocoding =
    geocodeProgress.total > 0 && geocodeProgress.done < geocodeProgress.total;
  const geocodePercent =
    geocodeProgress.total > 0
      ? Math.round((geocodeProgress.done / geocodeProgress.total) * 100)
      : 0;

  return (
    <div className="h-screen w-screen overflow-hidden relative" style={{ background: '#0A0E17' }}>
      {/* ---- Map container ---- */}
      <div ref={mapContainerRef} className="absolute inset-0 z-0" />

      {/* ---- HUD grid overlay ---- */}
      {gridVisible && (
        <div
          className="absolute inset-0 z-[5] pointer-events-none"
          style={{
            backgroundImage:
              'linear-gradient(rgba(0,212,255,0.07) 1px, transparent 1px), linear-gradient(90deg, rgba(0,212,255,0.07) 1px, transparent 1px)',
            backgroundSize: '80px 80px',
          }}
        />
      )}

      {/* -- Top Bar -- */}
      <div className="absolute top-0 left-0 right-0 z-20 pointer-events-none">
        <div
          className="flex items-center justify-between px-3 h-11 pointer-events-auto"
          style={{
            background: 'linear-gradient(to bottom, rgba(5, 5, 16, 0.95), rgba(5, 5, 16, 0.7), transparent)',
            borderBottom: '1px solid rgba(0, 212, 255, 0.08)',
            backdropFilter: 'blur(16px)',
            WebkitBackdropFilter: 'blur(16px)',
          }}
        >
          <button
            onClick={() => navigate('/')}
            className="h-7 px-2.5 flex items-center gap-1.5 rounded transition-colors hover:bg-white/[0.05]"
          >
            <ArrowLeft size={13} className="text-jarvis-blue/50" />
            <span className="text-[9px] font-mono tracking-widest text-jarvis-blue/40 uppercase hidden sm:inline">
              Back
            </span>
          </button>

          <div className="flex items-center gap-2">
            <span
              className="text-[10px] font-mono font-semibold tracking-[0.25em] text-jarvis-blue/70 uppercase"
              style={{ textShadow: '0 0 12px rgba(0, 212, 255, 0.2)' }}
            >
              Contact Atlas
            </span>
            {landmarks.length > 0 && (
              <span className="text-[8px] font-mono text-jarvis-gold/50 tracking-wider">
                {landmarks.length} LANDMARK{landmarks.length !== 1 ? 'S' : ''}
              </span>
            )}
          </div>

          <button
            onClick={() => setSidebarOpen((p) => !p)}
            className="h-7 px-2.5 flex items-center gap-1.5 rounded transition-colors hover:bg-white/[0.05]"
          >
            <Users size={13} className="text-jarvis-blue/50" />
            <span className="text-[9px] font-mono tracking-wider text-jarvis-blue/40 hidden sm:inline">
              {geocodedContacts.length}
            </span>
          </button>
        </div>
      </div>

      {/* -- Geocode Progress -- */}
      {isGeocoding && (
        <div className="absolute top-[52px] left-0 right-0 z-20 pointer-events-none flex justify-center">
          <div
            className="flex items-center gap-3 px-4 py-2 boot-2"
            style={{
              background: 'rgba(10, 14, 23, 0.9)',
              border: '1px solid rgba(0, 212, 255, 0.15)',
              borderRadius: '0 0 8px 8px',
              borderTop: 'none',
            }}
          >
            <Loader size={11} className="animate-spin text-jarvis-blue/60" />
            <span className="text-[9px] font-mono text-jarvis-blue/60 tracking-wider">
              GEOCODING
            </span>
            <div
              className="w-20 h-[3px] rounded-full overflow-hidden"
              style={{ background: 'rgba(0, 212, 255, 0.08)' }}
            >
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${geocodePercent}%`,
                  background: 'linear-gradient(90deg, rgba(0,212,255,0.4), rgba(0,212,255,0.7))',
                  boxShadow: '0 0 6px rgba(0, 212, 255, 0.3)',
                }}
              />
            </div>
            <span className="text-[9px] font-mono text-gray-500 tabular-nums">
              {geocodeProgress.done}/{geocodeProgress.total}
            </span>
          </div>
        </div>
      )}

      {/* -- Loading Overlay -- */}
      {isLoading && (
        <div
          className="absolute inset-0 z-30 flex items-center justify-center"
          style={{ background: 'rgba(10, 14, 23, 0.9)' }}
        >
          <div className="text-center boot-1">
            <div className="relative w-16 h-16 mx-auto mb-4">
              <div className="absolute inset-0 rounded-full border border-jarvis-blue/20 animate-spin-slow" />
              <div className="absolute inset-2 rounded-full border border-jarvis-blue/10 animate-spin-reverse" />
              <div className="absolute inset-0 flex items-center justify-center">
                <MapPin size={20} className="text-jarvis-blue/60" />
              </div>
            </div>
            <span className="text-[10px] font-mono tracking-[0.25em] text-jarvis-blue/40">
              LOADING CONTACT ATLAS
            </span>
          </div>
        </div>
      )}

      {/* -- Map Controls -- */}
      <MapControls
        onResetView={resetView}
        onToggleGrid={() => setGridVisible((p) => !p)}
        gridVisible={gridVisible}
      />

      {/* -- Context Menu -- */}
      {contextMenu && (
        <MapContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          onAddLandmark={handleAddLandmark}
          onCopyCoords={handleCopyCoords}
          onOpenInAppleMaps={handleOpenInAppleMaps}
          onLookAround={handleLookAround}
          onClose={() => setContextMenu(null)}
        />
      )}

      {/* -- Landmark Form -- */}
      {landmarkForm && (
        <LandmarkForm
          lat={landmarkForm.lat}
          lng={landmarkForm.lng}
          onSave={saveLandmark}
          onCancel={() => setLandmarkForm(null)}
        />
      )}

      {/* -- Look Around -- */}
      {lookAroundCoords && (
        <LookAroundPanel
          lat={lookAroundCoords.lat}
          lng={lookAroundCoords.lng}
          onClose={() => setLookAroundCoords(null)}
        />
      )}

      {/* -- Callout overlay layer (above sidebar) -- */}
      <div ref={calloutLayerRef} className="absolute inset-0 z-[15] pointer-events-none" />

      {/* -- Sidebar -- */}
      <div
        className="absolute top-0 right-0 bottom-0 z-10 flex flex-col transition-transform duration-300 ease-out"
        style={{
          width: '340px',
          maxWidth: '85vw',
          background: 'rgba(8, 12, 22, 0.92)',
          borderLeft: '1px solid rgba(0, 212, 255, 0.08)',
          backdropFilter: 'blur(24px) saturate(1.3)',
          WebkitBackdropFilter: 'blur(24px) saturate(1.3)',
          transform: sidebarOpen ? 'translateX(0)' : 'translateX(100%)',
        }}
      >
        <div className="flex items-center justify-between px-4 pt-[52px] pb-3">
          <div className="flex items-center gap-2">
            <MapPin size={13} className="text-jarvis-blue/60" />
            <span className="hud-label">CONTACT ATLAS</span>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            className="glass-circle w-7 h-7 flex items-center justify-center"
            aria-label="Close sidebar"
          >
            <X size={12} className="text-gray-500" />
          </button>
        </div>

        <div className="glow-line-h mx-4" />

        <div className="px-4 py-3">
          <div className="relative">
            <Search
              size={12}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-jarvis-blue/30"
            />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search contacts..."
              className="w-full py-2 pl-8 pr-8 text-xs font-mono bg-transparent border border-white/[0.06] rounded text-gray-300 placeholder-gray-600 focus:border-jarvis-blue/25 transition-colors"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-400 transition-colors"
                aria-label="Clear search"
              >
                <X size={12} />
              </button>
            )}
          </div>
        </div>

        <div className="px-4 pb-2 flex items-center gap-2">
          <span className="text-[8px] font-mono tracking-wider text-jarvis-blue/30">
            {geocodedContacts.length} MAPPED
          </span>
          <span className="text-[8px] text-white/[0.06]">|</span>
          <span className="text-[8px] font-mono tracking-wider text-gray-600">
            {contactsWithAddress.length} ADDRESSABLE
          </span>
          <span className="text-[8px] text-white/[0.06]">|</span>
          <span className="text-[8px] font-mono tracking-wider text-gray-700">
            {contacts.length} TOTAL
          </span>
        </div>

        <div className="glow-line-h mx-4 mb-1" />

        <div className="flex-1 overflow-y-auto">
          {isLoading ? (
            <SidebarSkeleton />
          ) : filteredContacts.length === 0 ? (
            <div className="text-center py-16 px-6">
              <div className="relative w-12 h-12 mx-auto mb-3">
                <div className="absolute inset-0 rounded-full border border-white/[0.04]" />
                <div className="absolute inset-0 flex items-center justify-center">
                  <MapPin size={16} className="text-gray-700" />
                </div>
              </div>
              <p className="text-[11px] text-gray-500 font-mono">
                {searchQuery
                  ? 'No matches found'
                  : isGeocoding
                    ? 'Geocoding in progress...'
                    : 'No contacts with addresses'}
              </p>
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="text-[10px] font-mono text-jarvis-blue/40 mt-2 hover:text-jarvis-blue/60 transition-colors"
                >
                  Clear search
                </button>
              )}
            </div>
          ) : (
            <div>
              {filteredContacts.map((contact) => (
                <ContactCard
                  key={contact.id}
                  contact={contact}
                  isSelected={selectedContactId === contact.id}
                  isExpanded={expandedContactId === contact.id}
                  onSelect={() => flyToContact(contact)}
                  onToggleExpand={() =>
                    setExpandedContactId((prev) => (prev === contact.id ? null : contact.id))
                  }
                />
              ))}
            </div>
          )}

          {/* Landmarks section */}
          {landmarks.length > 0 && !searchQuery && !isLoading && (
            <div className="px-4 py-4 border-t border-white/[0.04]">
              <div className="flex items-center gap-2 mb-2">
                <LandmarkIcon size={11} className="text-jarvis-gold/60" />
                <p className="text-[8px] font-mono tracking-wider text-jarvis-gold/50 uppercase">{landmarks.length} LANDMARKS</p>
              </div>
              <div className="space-y-1">
                {landmarks.map((lm) => (
                  <button
                    key={lm.id}
                    onClick={() => {
                      const map = mapRef.current;
                      const mk = window.mapkit;
                      if (!map || !mk) return;
                      const region = new mk.CoordinateRegion(
                        new mk.Coordinate(lm.latitude, lm.longitude),
                        new mk.CoordinateSpan(0.01, 0.01),
                      );
                      map.setRegionAnimated(region, true);
                      const ann = landmarkAnnotationsRef.current.find((a) => a.data?.landmarkId === lm.id);
                      if (ann) map.selectedAnnotation = ann;
                    }}
                    className="w-full text-left px-3 py-2 rounded hover:bg-white/[0.03] transition-colors flex items-center gap-2"
                  >
                    <div
                      className="w-2 h-2 rounded-full flex-shrink-0"
                      style={{ background: lm.color || '#f0a500', boxShadow: `0 0 4px ${lm.color || '#f0a500'}44` }}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="text-[11px] text-gray-300 truncate">{lm.name}</p>
                      {lm.address && <p className="text-[9px] text-gray-600 truncate font-mono">{lm.address}</p>}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {contactsWithoutAddress.length > 0 && !searchQuery && !isLoading && (
            <div className="px-4 py-4 border-t border-white/[0.04]">
              <p className="hud-label mb-2">{contactsWithoutAddress.length} UNMAPPED</p>
              <div className="flex flex-wrap gap-1">
                {contactsWithoutAddress.slice(0, 15).map((c) => {
                  const photo = getPhotoDataUri(c);
                  return (
                    <div
                      key={c.id}
                      className="flex items-center gap-1 px-1.5 py-0.5 rounded"
                      style={{ background: 'rgba(255,255,255,0.02)' }}
                      title={`${c.first_name} ${c.last_name || ''} — no address`}
                    >
                      {photo ? (
                        <img
                          src={photo}
                          alt=""
                          className="w-3.5 h-3.5 rounded-full object-cover"
                          onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                        />
                      ) : null}
                      <span className="text-[9px] font-mono text-gray-600">
                        {c.first_name} {c.last_name?.[0] || ''}
                      </span>
                    </div>
                  );
                })}
                {contactsWithoutAddress.length > 15 && (
                  <span className="text-[8px] font-mono text-gray-700 px-1.5 py-0.5">
                    +{contactsWithoutAddress.length - 15}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="px-4 py-2 border-t border-white/[0.04]">
          <div className="flex items-center justify-between">
            <span className="text-[7px] font-mono tracking-[0.15em] text-jarvis-blue/15">
              STARK.INDUSTRIES//ATLAS
            </span>
            <span className="text-[7px] font-mono tracking-[0.15em] text-gray-800">v3.1</span>
          </div>
        </div>
      </div>

      {/* -- MapKit JS overrides -- */}
      <style>{`
        /* Hide Apple Maps logo/attribution styling to blend with dark theme */
        .mk-map-view .mk-controls-container {
          opacity: 0.4;
        }

        /* Apple Maps zoom control dark theme */
        .mk-map-view .mk-zoom-in,
        .mk-map-view .mk-zoom-out {
          background: rgba(10, 14, 23, 0.9) !important;
          border: 1px solid rgba(0, 212, 255, 0.12) !important;
          color: #00d4ff !important;
        }
        .mk-map-view .mk-zoom-in:hover,
        .mk-map-view .mk-zoom-out:hover {
          background: rgba(0, 212, 255, 0.08) !important;
        }
      `}</style>
    </div>
  );
}
