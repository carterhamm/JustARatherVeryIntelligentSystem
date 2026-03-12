import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
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
import arcReactorIcon from '@/assets/arc-reactor-icon.png';

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

interface NominatimResult {
  lat: string;
  lon: string;
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

  try {
    const resp = await fetch(
      `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(address)}&format=json&limit=1`,
      { headers: { 'User-Agent': 'JARVIS-Map/1.0' } },
    );
    const data: NominatimResult[] = await resp.json();
    if (data.length > 0) {
      const result = { lat: parseFloat(data[0].lat), lng: parseFloat(data[0].lon) };
      cache[key] = result;
      saveGeocodeCache(cache);
      return result;
    }
  } catch {
    // geocode failed — skip
  }
  return null;
}

function getInitials(contact: Contact): string {
  const first = contact.first_name?.[0] ?? '';
  const last = contact.last_name?.[0] ?? '';
  return (first + last).toUpperCase() || '?';
}

function getPhotoDataUri(contact: Contact): string | null {
  if (!contact.photo) return null;
  const mime = contact.photo_content_type || 'image/jpeg';
  // Check if it's already a data URI or URL
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
    // Try to get last 2 parts of comma-separated address
    const parts = contact.address.split(',').map((s) => s.trim());
    return parts.slice(-2).join(', ');
  }
  return '';
}

function createContactIcon(contact: Contact): L.DivIcon {
  const photo = getPhotoDataUri(contact);
  const initials = getInitials(contact);

  if (photo) {
    return L.divIcon({
      className: 'jarvis-contact-marker',
      html: `
        <div class="jarvis-pin-photo" style="
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
      `,
      iconSize: [44, 44],
      iconAnchor: [22, 22],
      popupAnchor: [0, -26],
    });
  }

  return L.divIcon({
    className: 'jarvis-contact-marker',
    html: `
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
    `,
    iconSize: [40, 40],
    iconAnchor: [20, 20],
    popupAnchor: [0, -24],
  });
}

function createPopupContent(contact: Contact): string {
  const photo = getPhotoDataUri(contact);
  const lines: string[] = [];

  lines.push(`<div style="font-family:'JetBrains Mono','Fira Code',monospace;min-width:200px;max-width:280px;">`);

  // Header with photo
  lines.push(`<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">`);
  if (photo) {
    lines.push(`<img src="${photo}" alt="" style="width:36px;height:36px;border-radius:50%;object-fit:cover;border:1.5px solid rgba(0,212,255,0.4);flex-shrink:0;" />`);
  } else {
    lines.push(`<div style="width:36px;height:36px;border-radius:50%;background:rgba(0,20,40,0.8);border:1.5px solid rgba(0,212,255,0.3);display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:600;color:#00d4ff;flex-shrink:0;">${getInitials(contact)}</div>`);
  }
  lines.push(`<div>`);
  lines.push(`<div style="font-size:13px;font-weight:600;color:#00d4ff;letter-spacing:0.3px;line-height:1.3;">${contact.first_name} ${contact.last_name || ''}</div>`);
  if (contact.title && contact.company) {
    lines.push(`<div style="font-size:9px;color:#888;margin-top:1px;">${contact.title} at ${contact.company}</div>`);
  } else if (contact.company) {
    lines.push(`<div style="font-size:9px;color:#888;margin-top:1px;">${contact.company}</div>`);
  }
  lines.push(`</div></div>`);

  // Divider
  lines.push(`<div style="height:1px;background:linear-gradient(90deg,transparent,rgba(0,212,255,0.15),transparent);margin:6px 0;"></div>`);

  // Contact details
  if (contact.phone) {
    lines.push(`<div style="display:flex;align-items:center;gap:6px;margin:4px 0;"><span style="color:rgba(0,212,255,0.4);font-size:9px;">TEL</span><span style="color:#ccc;font-size:10px;">${contact.phone}</span></div>`);
  }
  if (contact.email) {
    lines.push(`<div style="display:flex;align-items:center;gap:6px;margin:4px 0;"><span style="color:rgba(0,212,255,0.4);font-size:9px;">EMAIL</span><span style="color:#ccc;font-size:10px;">${contact.email}</span></div>`);
  }

  const addr = getDisplayAddress(contact);
  if (addr) {
    lines.push(`<div style="display:flex;align-items:flex-start;gap:6px;margin:4px 0;"><span style="color:rgba(0,212,255,0.4);font-size:9px;margin-top:1px;">LOC</span><span style="color:#999;font-size:9px;line-height:1.4;">${addr}</span></div>`);
  }

  if (contact.birthday) {
    lines.push(`<div style="display:flex;align-items:center;gap:6px;margin:4px 0;"><span style="color:rgba(0,212,255,0.4);font-size:9px;">BDAY</span><span style="color:#999;font-size:9px;">${contact.birthday}</span></div>`);
  }

  lines.push('</div>');
  return lines.join('');
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
      {/* Main row — clickable to fly to contact */}
      <button
        onClick={onSelect}
        className="w-full text-left px-4 py-3 flex items-center gap-3 hover:bg-white/[0.03] transition-colors"
        style={{ minHeight: '52px' }}
      >
        {/* Avatar */}
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

        {/* Name + location */}
        <div className="min-w-0 flex-1">
          <p className="text-[13px] font-medium text-gray-200 truncate leading-tight">
            {contact.first_name} {contact.last_name || ''}
          </p>
          {shortLoc && (
            <p className="text-[10px] text-gray-500 truncate mt-0.5 font-mono">{shortLoc}</p>
          )}
        </div>

        {/* Expand toggle */}
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

      {/* Expandable detail section — progressive disclosure */}
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
        className={clsx('glass-circle w-9 h-9 flex items-center justify-center', gridVisible && 'active')}
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
  const mapRef = useRef<L.Map | null>(null);
  const markersRef = useRef<L.LayerGroup | null>(null);
  const gridLayerRef = useRef<L.LayerGroup | null>(null);

  const [contacts, setContacts] = useState<Contact[]>([]);
  const [geocodedContacts, setGeocodedContacts] = useState<GeocodedContact[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [geocodeProgress, setGeocodeProgress] = useState({ done: 0, total: 0 });
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedContactId, setSelectedContactId] = useState<string | null>(null);
  const [expandedContactId, setExpandedContactId] = useState<string | null>(null);
  const [gridVisible, setGridVisible] = useState(false);

  // ---- Fetch contacts ----
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setIsLoading(true);
      try {
        // Fetch all contacts (with limit=200 to get more)
        const result = await api.get<Contact[]>('/contacts', { offset: 0, limit: 200 });
        if (!cancelled) setContacts(result);
      } catch {
        try {
          // Fallback to search endpoint
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

  // ---- Geocode contacts with addresses ----
  useEffect(() => {
    if (contacts.length === 0) return;
    let cancelled = false;

    const withAddress = contacts.filter((c) => c.address?.trim() || (c.street && c.city));
    setGeocodeProgress({ done: 0, total: withAddress.length });

    (async () => {
      const cache = loadGeocodeCache();
      const results: GeocodedContact[] = [];

      for (let i = 0; i < withAddress.length; i++) {
        if (cancelled) return;
        const c = withAddress[i];
        const addrToGeocode = c.address?.trim() || [c.street, c.city, c.state, c.postal_code].filter(Boolean).join(', ');
        const coords = await geocodeAddress(addrToGeocode, cache);
        if (coords) {
          results.push({ ...c, lat: coords.lat, lng: coords.lng });
        }
        if (!cancelled) {
          setGeocodeProgress({ done: i + 1, total: withAddress.length });
          setGeocodedContacts([...results]);
        }
        // Nominatim rate limit: 1 req/sec (only if not cached)
        const key = addrToGeocode.trim().toLowerCase();
        if (!cache[key]) {
          await new Promise((r) => setTimeout(r, 1100));
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [contacts]);

  // ---- Initialize map ----
  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    const map = L.map(mapContainerRef.current, {
      center: [40.2969, -111.6946], // Orem, Utah
      zoom: 5,
      zoomControl: false,
      attributionControl: false,
    });

    // CartoDB Dark Matter tiles
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      maxZoom: 19,
      subdomains: 'abcd',
    }).addTo(map);

    // Custom zoom control in bottom-right
    L.control.zoom({ position: 'bottomright' }).addTo(map);

    // Attribution
    L.control
      .attribution({ position: 'bottomleft', prefix: false })
      .addAttribution(
        '&copy; <a href="https://carto.com/" style="color:#00d4ff">CARTO</a> &copy; <a href="https://www.openstreetmap.org/" style="color:#00d4ff">OSM</a>',
      )
      .addTo(map);

    const markers = L.layerGroup().addTo(map);
    markersRef.current = markers;

    const gridLayer = L.layerGroup();
    gridLayerRef.current = gridLayer;

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
      markersRef.current = null;
      gridLayerRef.current = null;
    };
  }, []);

  // ---- Place markers when geocoded contacts update ----
  useEffect(() => {
    const map = mapRef.current;
    const markers = markersRef.current;
    if (!map || !markers) return;

    markers.clearLayers();

    geocodedContacts.forEach((c) => {
      const marker = L.marker([c.lat, c.lng], { icon: createContactIcon(c) });
      marker.bindPopup(createPopupContent(c), {
        className: 'jarvis-popup',
        closeButton: true,
        maxWidth: 280,
      });
      marker.on('click', () => {
        setSelectedContactId(c.id);
      });
      markers.addLayer(marker);
    });

    // Fit bounds if we have markers
    if (geocodedContacts.length > 0) {
      const bounds = L.latLngBounds(geocodedContacts.map((c) => [c.lat, c.lng]));
      map.fitBounds(bounds, { padding: [60, 60], maxZoom: 12 });
    }
  }, [geocodedContacts]);

  // ---- Toggle grid overlay ----
  useEffect(() => {
    const map = mapRef.current;
    const gridLayer = gridLayerRef.current;
    if (!map || !gridLayer) return;

    if (gridVisible) {
      gridLayer.addTo(map);
    } else {
      gridLayer.remove();
    }
  }, [gridVisible]);

  // ---- Fly to contact ----
  const flyToContact = useCallback((contact: GeocodedContact) => {
    const map = mapRef.current;
    if (!map) return;
    setSelectedContactId(contact.id);
    map.flyTo([contact.lat, contact.lng], 14, { duration: 1.2 });

    // Open popup
    markersRef.current?.eachLayer((layer) => {
      if (layer instanceof L.Marker) {
        const latlng = layer.getLatLng();
        if (Math.abs(latlng.lat - contact.lat) < 0.0001 && Math.abs(latlng.lng - contact.lng) < 0.0001) {
          layer.openPopup();
        }
      }
    });
  }, []);

  // ---- Reset view ----
  const resetView = useCallback(() => {
    const map = mapRef.current;
    if (!map || geocodedContacts.length === 0) return;
    const bounds = L.latLngBounds(geocodedContacts.map((c) => [c.lat, c.lng]));
    map.flyToBounds(bounds, { padding: [60, 60], maxZoom: 12, duration: 0.8 });
    setSelectedContactId(null);
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

  const isGeocoding = geocodeProgress.total > 0 && geocodeProgress.done < geocodeProgress.total;
  const geocodePercent = geocodeProgress.total > 0 ? Math.round((geocodeProgress.done / geocodeProgress.total) * 100) : 0;

  return (
    <div className="h-screen w-screen overflow-hidden relative" style={{ background: '#0A0E17' }}>
      {/* ---- Map container ---- */}
      <div ref={mapContainerRef} className="absolute inset-0 z-0" />

      {/* ---- HUD grid overlay (optional, toggleable) ---- */}
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

      {/* ── Top Bar ─────────────────────────────────────────────── */}
      <div className="absolute top-0 left-0 right-0 z-20 pointer-events-none">
        <div
          className="flex items-center justify-between px-4 py-3 pointer-events-auto"
          style={{
            background: 'linear-gradient(180deg, rgba(10, 14, 23, 0.95) 0%, rgba(10, 14, 23, 0.7) 60%, transparent 100%)',
          }}
        >
          {/* Back — glass capsule style */}
          <button
            onClick={() => navigate('/')}
            className="glass-capsule h-9 px-3 flex items-center gap-2 hover:bg-white/[0.04] transition-all"
          >
            <ArrowLeft size={14} className="text-jarvis-blue/60" />
            <span className="text-[10px] font-mono tracking-wider text-jarvis-blue/60 hidden sm:inline">
              MAIN
            </span>
          </button>

          {/* Title — centered */}
          <div className="flex items-center gap-3 boot-1">
            <img
              src={arcReactorIcon}
              alt=""
              className="w-5 h-5 object-contain"
              style={{ filter: 'drop-shadow(0 0 4px rgba(0, 212, 255, 0.5))' }}
            />
            <h1
              className="font-display text-sm sm:text-base font-bold tracking-[0.3em] text-jarvis-blue"
              style={{ textShadow: '0 0 20px rgba(0, 212, 255, 0.3)' }}
            >
              JARVIS MAP
            </h1>
          </div>

          {/* Toggle sidebar */}
          <button
            onClick={() => setSidebarOpen((p) => !p)}
            className="glass-capsule h-9 px-3 flex items-center gap-2 hover:bg-white/[0.04] transition-all"
          >
            <Users size={14} className="text-jarvis-blue/60" />
            <span className="text-[10px] font-mono tracking-wider text-jarvis-blue/60 hidden sm:inline">
              {geocodedContacts.length} <span className="text-gray-600">PINNED</span>
            </span>
          </button>
        </div>
      </div>

      {/* ── Geocode Progress ─────────────────────────────────────── */}
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
            <div className="w-20 h-[3px] rounded-full overflow-hidden" style={{ background: 'rgba(0, 212, 255, 0.08)' }}>
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

      {/* ── Loading Overlay ──────────────────────────────────────── */}
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

      {/* ── Map Controls ─────────────────────────────────────────── */}
      <MapControls
        onResetView={resetView}
        onToggleGrid={() => setGridVisible((p) => !p)}
        gridVisible={gridVisible}
      />

      {/* ── Sidebar ──────────────────────────────────────────────── */}
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
        {/* Sidebar header */}
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

        {/* Glow line divider */}
        <div className="glow-line-h mx-4" />

        {/* Search */}
        <div className="px-4 py-3">
          <div className="relative">
            <Search size={12} className="absolute left-3 top-1/2 -translate-y-1/2 text-jarvis-blue/30" />
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

        {/* Stats */}
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

        {/* Contact list */}
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

          {/* Unmapped contacts */}
          {contactsWithoutAddress.length > 0 && !searchQuery && !isLoading && (
            <div className="px-4 py-4 border-t border-white/[0.04]">
              <p className="hud-label mb-2">
                {contactsWithoutAddress.length} UNMAPPED
              </p>
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
                        <img src={photo} alt="" className="w-3.5 h-3.5 rounded-full object-cover" />
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

        {/* Sidebar footer */}
        <div className="px-4 py-2 border-t border-white/[0.04]">
          <div className="flex items-center justify-between">
            <span className="text-[7px] font-mono tracking-[0.15em] text-jarvis-blue/15">
              STARK.INDUSTRIES//ATLAS
            </span>
            <span className="text-[7px] font-mono tracking-[0.15em] text-gray-800">
              v2.0
            </span>
          </div>
        </div>
      </div>

      {/* ── Inline styles for Leaflet overrides ─────────────────── */}
      <style>{`
        /* Popup */
        .jarvis-popup .leaflet-popup-content-wrapper {
          background: rgba(10, 14, 23, 0.95) !important;
          border: 1px solid rgba(0, 212, 255, 0.15) !important;
          border-radius: 6px !important;
          box-shadow: 0 0 24px rgba(0, 212, 255, 0.08), 0 12px 40px rgba(0, 0, 0, 0.6) !important;
          color: #e0e0e0 !important;
          padding: 0 !important;
          backdrop-filter: blur(20px);
          -webkit-backdrop-filter: blur(20px);
        }
        .jarvis-popup .leaflet-popup-content {
          margin: 14px 16px !important;
        }
        .jarvis-popup .leaflet-popup-tip {
          background: rgba(10, 14, 23, 0.95) !important;
          border: 1px solid rgba(0, 212, 255, 0.15) !important;
          box-shadow: none !important;
        }
        .jarvis-popup .leaflet-popup-close-button {
          color: rgba(0, 212, 255, 0.4) !important;
          font-size: 16px !important;
          padding: 6px 8px 0 0 !important;
        }
        .jarvis-popup .leaflet-popup-close-button:hover {
          color: #00d4ff !important;
        }

        /* Zoom controls */
        .leaflet-control-zoom a {
          background: rgba(10, 14, 23, 0.9) !important;
          border: 1px solid rgba(0, 212, 255, 0.12) !important;
          color: rgba(0, 212, 255, 0.6) !important;
          width: 34px !important;
          height: 34px !important;
          line-height: 32px !important;
          font-size: 16px !important;
          transition: all 0.2s ease !important;
        }
        .leaflet-control-zoom a:hover {
          background: rgba(0, 212, 255, 0.08) !important;
          border-color: rgba(0, 212, 255, 0.25) !important;
          color: #00d4ff !important;
        }
        .leaflet-control-zoom {
          border: none !important;
          box-shadow: none !important;
          margin-bottom: 12px !important;
        }

        /* Attribution */
        .leaflet-control-attribution {
          background: rgba(10, 14, 23, 0.6) !important;
          color: #444 !important;
          font-size: 8px !important;
          font-family: 'JetBrains Mono', monospace !important;
          border: none !important;
          padding: 2px 6px !important;
        }
        .leaflet-control-attribution a {
          color: rgba(0, 212, 255, 0.4) !important;
        }

        /* Marker base */
        .jarvis-contact-marker {
          background: none !important;
          border: none !important;
        }

        /* Marker hover effect */
        .jarvis-contact-marker:hover .jarvis-pin-photo,
        .jarvis-contact-marker:hover > div:first-child {
          border-color: rgba(0, 212, 255, 0.9) !important;
          box-shadow: 0 0 24px rgba(0, 212, 255, 0.5), 0 4px 16px rgba(0,0,0,0.5) !important;
          transform: scale(1.12) !important;
        }
      `}</style>
    </div>
  );
}
