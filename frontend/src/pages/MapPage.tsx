import { useEffect, useRef, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { api } from '@/services/api';
import { ArrowLeft, Loader, MapPin, Users, Search, X } from 'lucide-react';

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

function createContactIcon(contact: Contact): L.DivIcon {
  const initials = getInitials(contact);
  return L.divIcon({
    className: 'jarvis-contact-marker',
    html: `
      <div style="
        width: 38px; height: 38px; border-radius: 50%;
        background: rgba(0, 20, 40, 0.85);
        border: 2px solid rgba(0, 212, 255, 0.7);
        box-shadow: 0 0 12px rgba(0, 212, 255, 0.35), 0 0 4px rgba(0, 212, 255, 0.15) inset;
        display: flex; align-items: center; justify-content: center;
        font-family: 'JetBrains Mono', 'Fira Code', monospace;
        font-size: 12px; font-weight: 600; color: #00d4ff;
        letter-spacing: 0.5px;
        transition: all 0.2s ease;
      ">${initials}</div>
    `,
    iconSize: [38, 38],
    iconAnchor: [19, 19],
    popupAnchor: [0, -22],
  });
}

function createPopupContent(contact: Contact): string {
  const lines: string[] = [];
  lines.push(
    `<div style="font-family:'JetBrains Mono','Fira Code',monospace;font-size:11px;color:#e0e0e0;min-width:180px;">`,
  );
  lines.push(
    `<div style="font-size:13px;font-weight:600;color:#00d4ff;margin-bottom:6px;letter-spacing:0.5px;">${contact.first_name} ${contact.last_name || ''}</div>`,
  );
  if (contact.company) {
    lines.push(
      `<div style="color:#888;font-size:10px;margin-bottom:4px;">${contact.title ? contact.title + ' at ' : ''}${contact.company}</div>`,
    );
  }
  if (contact.phone) {
    lines.push(`<div style="color:#aaa;font-size:10px;margin-bottom:2px;">${contact.phone}</div>`);
  }
  if (contact.email) {
    lines.push(`<div style="color:#aaa;font-size:10px;margin-bottom:2px;">${contact.email}</div>`);
  }
  if (contact.address) {
    lines.push(
      `<div style="color:#666;font-size:9px;margin-top:4px;border-top:1px solid rgba(0,212,255,0.15);padding-top:4px;">${contact.address}</div>`,
    );
  }
  lines.push('</div>');
  return lines.join('');
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function MapPage() {
  const navigate = useNavigate();
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markersRef = useRef<L.LayerGroup | null>(null);

  const [contacts, setContacts] = useState<Contact[]>([]);
  const [geocodedContacts, setGeocodedContacts] = useState<GeocodedContact[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [geocodeProgress, setGeocodeProgress] = useState({ done: 0, total: 0 });
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedContactId, setSelectedContactId] = useState<string | null>(null);

  // ---- Fetch contacts ----
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setIsLoading(true);
      try {
        const result = await api.get<Contact[]>('/contacts/search', { q: '' });
        if (!cancelled) setContacts(result);
      } catch {
        // silently fail
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // ---- Geocode contacts with addresses ----
  useEffect(() => {
    if (contacts.length === 0) return;
    let cancelled = false;

    const withAddress = contacts.filter((c) => c.address?.trim());
    setGeocodeProgress({ done: 0, total: withAddress.length });

    (async () => {
      const cache = loadGeocodeCache();
      const results: GeocodedContact[] = [];

      for (let i = 0; i < withAddress.length; i++) {
        if (cancelled) return;
        const c = withAddress[i];
        const coords = await geocodeAddress(c.address!, cache);
        if (coords) {
          results.push({ ...c, lat: coords.lat, lng: coords.lng });
        }
        if (!cancelled) {
          setGeocodeProgress({ done: i + 1, total: withAddress.length });
          // Update geocoded contacts progressively
          setGeocodedContacts([...results]);
        }
        // Nominatim rate limit: 1 req/sec (only if not cached)
        const key = c.address!.trim().toLowerCase();
        if (!cache[key]) {
          await new Promise((r) => setTimeout(r, 1100));
        }
      }
    })();

    return () => { cancelled = true; };
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

    // Attribution (small, bottom-left)
    L.control
      .attribution({ position: 'bottomleft', prefix: false })
      .addAttribution('&copy; <a href="https://carto.com/" style="color:#00d4ff">CARTO</a> &copy; <a href="https://www.openstreetmap.org/" style="color:#00d4ff">OSM</a>')
      .addTo(map);

    const markers = L.layerGroup().addTo(map);
    markersRef.current = markers;
    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
      markersRef.current = null;
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
        maxWidth: 260,
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

  // ---- Fly to contact ----
  const flyToContact = useCallback(
    (contact: GeocodedContact) => {
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
    },
    [],
  );

  // ---- Filtered contacts for sidebar ----
  const filteredContacts = searchQuery.trim()
    ? geocodedContacts.filter((c) => {
        const q = searchQuery.toLowerCase();
        return (
          c.first_name.toLowerCase().includes(q) ||
          (c.last_name?.toLowerCase().includes(q) ?? false) ||
          (c.company?.toLowerCase().includes(q) ?? false) ||
          (c.address?.toLowerCase().includes(q) ?? false)
        );
      })
    : geocodedContacts;

  const contactsWithAddress = contacts.filter((c) => c.address?.trim());
  const contactsWithoutAddress = contacts.filter((c) => !c.address?.trim());

  return (
    <div className="h-screen w-screen overflow-hidden relative" style={{ background: '#0A0E17' }}>
      {/* ---- Map container ---- */}
      <div ref={mapContainerRef} className="absolute inset-0 z-0" />

      {/* ---- HUD Overlay: Top bar ---- */}
      <div className="absolute top-0 left-0 right-0 z-20 pointer-events-none">
        <div
          className="flex items-center justify-between px-5 py-3 pointer-events-auto"
          style={{
            background: 'linear-gradient(180deg, rgba(10, 14, 23, 0.92) 0%, rgba(10, 14, 23, 0.6) 70%, transparent 100%)',
          }}
        >
          {/* Back button */}
          <button
            onClick={() => navigate('/')}
            className="flex items-center gap-2 text-jarvis-blue/70 hover:text-jarvis-blue transition-colors"
          >
            <ArrowLeft size={16} />
            <span className="text-[11px] font-mono tracking-wider hidden sm:inline">MAIN INTERFACE</span>
          </button>

          {/* Title */}
          <div className="flex items-center gap-3">
            <div
              className="w-2 h-2 rounded-full"
              style={{
                background: '#00d4ff',
                boxShadow: '0 0 8px rgba(0, 212, 255, 0.6)',
              }}
            />
            <h1
              className="font-display text-sm sm:text-base font-bold tracking-[0.3em] text-jarvis-blue"
              style={{ textShadow: '0 0 20px rgba(0, 212, 255, 0.3)' }}
            >
              JARVIS MAP
            </h1>
            <div
              className="w-2 h-2 rounded-full"
              style={{
                background: '#00d4ff',
                boxShadow: '0 0 8px rgba(0, 212, 255, 0.6)',
              }}
            />
          </div>

          {/* Toggle sidebar */}
          <button
            onClick={() => setSidebarOpen((p) => !p)}
            className="flex items-center gap-2 text-jarvis-blue/70 hover:text-jarvis-blue transition-colors"
          >
            <Users size={16} />
            <span className="text-[11px] font-mono tracking-wider hidden sm:inline">
              {geocodedContacts.length} PINNED
            </span>
          </button>
        </div>
      </div>

      {/* ---- Geocode progress bar ---- */}
      {geocodeProgress.total > 0 && geocodeProgress.done < geocodeProgress.total && (
        <div className="absolute top-14 left-1/2 -translate-x-1/2 z-20">
          <div
            className="flex items-center gap-2 px-4 py-2 rounded-full"
            style={{
              background: 'rgba(10, 14, 23, 0.9)',
              border: '1px solid rgba(0, 212, 255, 0.2)',
              boxShadow: '0 0 20px rgba(0, 212, 255, 0.1)',
            }}
          >
            <Loader size={12} className="animate-spin text-jarvis-blue" />
            <span className="text-[10px] font-mono text-jarvis-blue/80 tracking-wider">
              GEOCODING {geocodeProgress.done}/{geocodeProgress.total}
            </span>
            <div className="w-24 h-1 rounded-full overflow-hidden" style={{ background: 'rgba(0, 212, 255, 0.1)' }}>
              <div
                className="h-full rounded-full transition-all duration-300"
                style={{
                  width: `${(geocodeProgress.done / geocodeProgress.total) * 100}%`,
                  background: 'linear-gradient(90deg, #00d4ff, #00f0ff)',
                  boxShadow: '0 0 8px rgba(0, 212, 255, 0.5)',
                }}
              />
            </div>
          </div>
        </div>
      )}

      {/* ---- Loading overlay ---- */}
      {isLoading && (
        <div className="absolute inset-0 z-30 flex items-center justify-center" style={{ background: 'rgba(10, 14, 23, 0.85)' }}>
          <div className="text-center">
            <Loader size={28} className="animate-spin text-jarvis-blue mx-auto mb-3" />
            <span className="text-[11px] font-mono tracking-[0.2em] text-jarvis-blue/60">LOADING CONTACTS</span>
          </div>
        </div>
      )}

      {/* ---- Sidebar ---- */}
      <div
        className="absolute top-0 right-0 bottom-0 z-10 flex flex-col transition-transform duration-300 ease-out"
        style={{
          width: '320px',
          maxWidth: '85vw',
          background: 'rgba(8, 12, 22, 0.92)',
          borderLeft: '1px solid rgba(0, 212, 255, 0.1)',
          backdropFilter: 'blur(20px)',
          transform: sidebarOpen ? 'translateX(0)' : 'translateX(100%)',
        }}
      >
        {/* Sidebar header */}
        <div className="flex items-center justify-between px-4 pt-16 pb-3 border-b border-jarvis-blue/10">
          <div className="flex items-center gap-2">
            <MapPin size={14} className="text-jarvis-blue" />
            <span className="font-display text-xs font-semibold tracking-wider text-jarvis-blue">
              CONTACT LOCATIONS
            </span>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            className="text-gray-500 hover:text-jarvis-blue transition-colors"
          >
            <X size={14} />
          </button>
        </div>

        {/* Search */}
        <div className="px-4 py-2 border-b border-white/[0.04]">
          <div className="relative">
            <Search size={12} className="absolute left-3 top-1/2 -translate-y-1/2 text-jarvis-blue/40" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search pinned contacts..."
              className="w-full py-2 pl-8 pr-3 text-xs font-mono bg-transparent border border-jarvis-blue/10 rounded text-gray-300 placeholder-gray-600 focus:outline-none focus:border-jarvis-blue/30"
            />
          </div>
        </div>

        {/* Stats bar */}
        <div className="px-4 py-2 border-b border-white/[0.04] flex items-center gap-3">
          <span className="text-[9px] font-mono tracking-wider text-gray-500">
            {geocodedContacts.length} GEOCODED
          </span>
          <span className="text-[9px] text-gray-700">|</span>
          <span className="text-[9px] font-mono tracking-wider text-gray-600">
            {contactsWithAddress.length} WITH ADDRESS
          </span>
          <span className="text-[9px] text-gray-700">|</span>
          <span className="text-[9px] font-mono tracking-wider text-gray-600">
            {contacts.length} TOTAL
          </span>
        </div>

        {/* Contact list */}
        <div className="flex-1 overflow-y-auto scrollbar-thin">
          {filteredContacts.length === 0 ? (
            <div className="text-center py-12 px-4">
              <MapPin size={20} className="mx-auto text-gray-600 mb-2" />
              <p className="text-xs text-gray-500 font-mono">
                {searchQuery
                  ? 'No matches found.'
                  : geocodedContacts.length === 0 && geocodeProgress.done < geocodeProgress.total
                    ? 'Geocoding addresses...'
                    : 'No contacts with valid addresses.'}
              </p>
            </div>
          ) : (
            <div>
              {filteredContacts.map((contact) => (
                <button
                  key={contact.id}
                  onClick={() => flyToContact(contact)}
                  className="w-full text-left px-4 py-3 border-b border-white/[0.03] transition-colors hover:bg-white/[0.03]"
                  style={{
                    background:
                      selectedContactId === contact.id
                        ? 'rgba(0, 212, 255, 0.06)'
                        : 'transparent',
                  }}
                >
                  <div className="flex items-center gap-3">
                    {/* Avatar circle */}
                    <div
                      className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0"
                      style={{
                        background: 'rgba(0, 20, 40, 0.8)',
                        border:
                          selectedContactId === contact.id
                            ? '1.5px solid rgba(0, 212, 255, 0.7)'
                            : '1.5px solid rgba(0, 212, 255, 0.25)',
                        boxShadow:
                          selectedContactId === contact.id
                            ? '0 0 8px rgba(0, 212, 255, 0.3)'
                            : 'none',
                      }}
                    >
                      <span className="text-[10px] font-mono font-semibold text-jarvis-blue">
                        {getInitials(contact)}
                      </span>
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-medium text-gray-200 truncate">
                        {contact.first_name} {contact.last_name || ''}
                      </p>
                      {contact.company && (
                        <p className="text-[10px] text-gray-500 truncate">{contact.company}</p>
                      )}
                      <p className="text-[9px] text-gray-600 truncate mt-0.5">{contact.address}</p>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}

          {/* Contacts without addresses */}
          {contactsWithoutAddress.length > 0 && !searchQuery && (
            <div className="px-4 py-3 border-t border-white/[0.06]">
              <p className="text-[9px] font-mono tracking-wider text-gray-600 mb-2">
                {contactsWithoutAddress.length} CONTACTS WITHOUT ADDRESS
              </p>
              <div className="flex flex-wrap gap-1">
                {contactsWithoutAddress.slice(0, 12).map((c) => (
                  <span
                    key={c.id}
                    className="text-[9px] font-mono text-gray-600 px-1.5 py-0.5 rounded"
                    style={{ background: 'rgba(255,255,255,0.03)' }}
                  >
                    {c.first_name} {c.last_name?.[0] || ''}
                  </span>
                ))}
                {contactsWithoutAddress.length > 12 && (
                  <span className="text-[9px] font-mono text-gray-700 px-1.5 py-0.5">
                    +{contactsWithoutAddress.length - 12} more
                  </span>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Sidebar footer */}
        <div className="px-4 py-2 border-t border-white/[0.06]">
          <div className="flex items-center justify-between">
            <span className="text-[8px] font-mono tracking-[0.15em] text-jarvis-blue/20">
              MALIBU.POINT//MAP.SYS
            </span>
            <span className="text-[8px] font-mono tracking-[0.15em] text-gray-700">
              v1.0
            </span>
          </div>
        </div>
      </div>

      {/* ---- Custom styles ---- */}
      <style>{`
        /* Override Leaflet popup styles for JARVIS theme */
        .jarvis-popup .leaflet-popup-content-wrapper {
          background: rgba(10, 14, 23, 0.95) !important;
          border: 1px solid rgba(0, 212, 255, 0.2) !important;
          border-radius: 4px !important;
          box-shadow: 0 0 20px rgba(0, 212, 255, 0.1), 0 8px 32px rgba(0, 0, 0, 0.5) !important;
          color: #e0e0e0 !important;
          padding: 0 !important;
        }
        .jarvis-popup .leaflet-popup-content {
          margin: 12px 14px !important;
        }
        .jarvis-popup .leaflet-popup-tip {
          background: rgba(10, 14, 23, 0.95) !important;
          border: 1px solid rgba(0, 212, 255, 0.2) !important;
          box-shadow: none !important;
        }
        .jarvis-popup .leaflet-popup-close-button {
          color: rgba(0, 212, 255, 0.5) !important;
          font-size: 16px !important;
          padding: 6px 8px 0 0 !important;
        }
        .jarvis-popup .leaflet-popup-close-button:hover {
          color: #00d4ff !important;
        }

        /* Override leaflet zoom controls */
        .leaflet-control-zoom a {
          background: rgba(10, 14, 23, 0.9) !important;
          border: 1px solid rgba(0, 212, 255, 0.15) !important;
          color: #00d4ff !important;
          width: 32px !important;
          height: 32px !important;
          line-height: 30px !important;
          font-size: 16px !important;
        }
        .leaflet-control-zoom a:hover {
          background: rgba(0, 212, 255, 0.1) !important;
          border-color: rgba(0, 212, 255, 0.3) !important;
        }
        .leaflet-control-zoom {
          border: none !important;
          box-shadow: none !important;
        }

        /* Override attribution style */
        .leaflet-control-attribution {
          background: rgba(10, 14, 23, 0.7) !important;
          color: #555 !important;
          font-size: 9px !important;
          font-family: 'JetBrains Mono', monospace !important;
          border: none !important;
          padding: 2px 6px !important;
        }
        .leaflet-control-attribution a {
          color: rgba(0, 212, 255, 0.5) !important;
        }

        /* Remove default marker icon styling */
        .jarvis-contact-marker {
          background: none !important;
          border: none !important;
        }

        /* Scrollbar for sidebar */
        .scrollbar-thin::-webkit-scrollbar {
          width: 4px;
        }
        .scrollbar-thin::-webkit-scrollbar-track {
          background: transparent;
        }
        .scrollbar-thin::-webkit-scrollbar-thumb {
          background: rgba(0, 212, 255, 0.15);
          border-radius: 2px;
        }
      `}</style>
    </div>
  );
}
