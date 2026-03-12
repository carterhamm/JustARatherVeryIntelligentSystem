import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
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
  const mime = contact.photo_content_type || 'image/jpeg';
  if (contact.photo.startsWith('data:') || contact.photo.startsWith('http')) {
    return contact.photo;
  }
  return `data:${mime};base64,${contact.photo}`;
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

function createAnnotationElement(contact: Contact): HTMLDivElement {
  const photo = getPhotoDataUri(contact);
  const initials = getInitials(contact);
  const el = document.createElement('div');
  el.style.cursor = 'pointer';
  el.style.position = 'relative';

  if (photo) {
    el.innerHTML = `
      <div style="
        width: 44px; height: 44px; border-radius: 50%;
        background: rgba(0, 20, 40, 0.9);
        border: 2px solid rgba(0, 212, 255, 0.6);
        box-shadow: 0 0 16px rgba(0, 212, 255, 0.3), 0 4px 12px rgba(0,0,0,0.5);
        overflow: hidden;
        transition: all 0.25s ease;
      ">
        <img src="${photo}" alt="" style="
          width: 100%; height: 100%; object-fit: cover;
          border-radius: 50%;
        " />
      </div>
      <div style="
        width: 12px; height: 12px;
        background: rgba(0, 212, 255, 0.8);
        border: 2px solid rgba(10, 14, 23, 0.9);
        border-radius: 50%;
        position: absolute;
        bottom: -2px; right: -2px;
        box-shadow: 0 0 6px rgba(0, 212, 255, 0.5);
      "></div>
    `;
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
      `<img src="${photo}" alt="" style="width:36px;height:36px;border-radius:50%;object-fit:cover;border:1.5px solid rgba(0,212,255,0.4);flex-shrink:0;" />`,
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
    lines.push(
      `<div style="display:flex;align-items:center;gap:6px;margin:4px 0;"><span style="color:rgba(0,212,255,0.4);font-size:9px;">BDAY</span><span style="color:#999;font-size:9px;">${contact.birthday}</span></div>`,
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
            <img src={photo} alt="" className="w-full h-full object-cover rounded-full" />
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
              <span className="text-[10px] font-mono text-gray-400">{contact.birthday}</span>
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
// Component
// ---------------------------------------------------------------------------

export default function MapPage() {
  const navigate = useNavigate();
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null); // mapkit.Map
  const annotationsRef = useRef<any[]>([]);
  const calloutOverlayRef = useRef<HTMLDivElement | null>(null);

  const [contacts, setContacts] = useState<Contact[]>([]);
  const [geocodedContacts, setGeocodedContacts] = useState<GeocodedContact[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [mapReady, setMapReady] = useState(false);
  const [geocodeProgress, setGeocodeProgress] = useState({ done: 0, total: 0 });
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedContactId, setSelectedContactId] = useState<string | null>(null);
  const [expandedContactId, setExpandedContactId] = useState<string | null>(null);
  const [gridVisible, setGridVisible] = useState(false);

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
          mapType: mk.Map.MapTypes.MutedStandard,
          colorScheme: mk.Map.ColorSchemes.Dark,
          showsCompass: mk.FeatureVisibility.Hidden,
          showsZoomControl: true,
          showsMapTypeControl: false,
          isZoomEnabled: true,
          isScrollEnabled: true,
          isRotationEnabled: true,
          padding: new mk.Padding(0, 0, 0, 0),
        });

        mapRef.current = map;
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
    };
  }, []);

  // ---- Fetch contacts ----
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setIsLoading(true);
      try {
        const result = await api.get<Contact[]>('/contacts', { offset: 0, limit: 200 });
        if (!cancelled) setContacts(result);
      } catch {
        try {
          const result = await api.get<Contact[]>('/contacts/search', { q: '' });
          if (!cancelled) setContacts(result);
        } catch {
          // silently fail
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

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
          setGeocodedContacts([...results]);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [contacts, mapReady]);

  // ---- Place annotations when geocoded contacts update ----
  useEffect(() => {
    const map = mapRef.current;
    const mk = window.mapkit;
    if (!map || !mk || !mapReady) return;

    // Remove existing annotations
    if (annotationsRef.current.length > 0) {
      map.removeAnnotations(annotationsRef.current);
      annotationsRef.current = [];
    }

    // Remove old callout overlay
    if (calloutOverlayRef.current) {
      calloutOverlayRef.current.remove();
      calloutOverlayRef.current = null;
    }

    const newAnnotations: any[] = [];

    geocodedContacts.forEach((c) => {
      const coord = new mk.Coordinate(c.lat, c.lng);

      const annotation = new mk.Annotation(coord, (coordinate: any) => {
        return createAnnotationElement(c);
      }, {
        anchorOffset: new DOMPoint(0, -20),
        calloutEnabled: false, // We handle callouts ourselves
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

        // Position callout near the annotation
        const mapContainer = mapContainerRef.current;
        if (mapContainer) {
          const point = map.convertCoordinateToPointOnPage(coord);
          const rect = mapContainer.getBoundingClientRect();
          callout.style.left = `${point.x - rect.left - 140}px`;
          callout.style.top = `${point.y - rect.top - 180}px`;
          mapContainer.appendChild(callout);
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

    const centerLat = (minLat + maxLat) / 2;
    const centerLng = (minLng + maxLng) / 2;
    const spanLat = Math.max(maxLat - minLat, 0.01) * 1.4; // 40% padding
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

      // Animate to contact location
      const region = new mk.CoordinateRegion(
        new mk.Coordinate(contact.lat, contact.lng),
        new mk.CoordinateSpan(0.02, 0.02),
      );
      map.setRegionAnimated(region, true);

      // Select the matching annotation
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
  }, [geocodedContacts]);

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
          className="absolute inset-0 z-[1] pointer-events-none"
          style={{
            backgroundImage:
              'linear-gradient(rgba(0,212,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(0,212,255,0.03) 1px, transparent 1px)',
            backgroundSize: '80px 80px',
          }}
        />
      )}

      {/* -- Top Bar -- */}
      <div className="absolute top-0 left-0 right-0 z-20 pointer-events-none">
        <div
          className="flex items-center justify-between px-3 h-11 pointer-events-auto"
          style={{
            background: 'rgba(0, 0, 0, 0.6)',
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
            <span className="text-[7px] font-mono tracking-[0.15em] text-gray-800">v3.0</span>
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
