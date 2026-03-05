import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  X,
  Search,
  Brain,
  Network,
  User,
  Calendar,
  MapPin,
  FileText,
  Building,
  ChevronLeft,
  Loader,
  AlertCircle,
} from 'lucide-react';
import { api } from '@/services/api';
import clsx from 'clsx';

/* ---------- Types ---------- */

interface KnowledgeEntity {
  id: string;
  name: string;
  type: string;
  snippet?: string;
  properties?: Record<string, unknown>;
  relationships?: EntityRelationship[];
  sources?: EntitySource[];
}

interface EntityRelationship {
  entity_id: string;
  entity_name: string;
  entity_type: string;
  relationship_type: string;
  strength?: number;
}

interface EntitySource {
  id: string;
  name: string;
  type: string;
  imported_at?: string;
}

interface SearchResponse {
  results: KnowledgeEntity[];
  total?: number;
}

interface SourcesResponse {
  sources: EntitySource[];
}

/* ---------- Helpers ---------- */

const entityTypeConfig: Record<string, { color: string; icon: React.ReactNode }> = {
  person: { color: 'bg-blue-500/20 text-blue-400 border-blue-500/30', icon: <User size={12} /> },
  event: {
    color: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
    icon: <Calendar size={12} />,
  },
  topic: {
    color: 'bg-green-500/20 text-green-400 border-green-500/30',
    icon: <Brain size={12} />,
  },
  location: {
    color: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
    icon: <MapPin size={12} />,
  },
  document: {
    color: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
    icon: <FileText size={12} />,
  },
  organization: {
    color: 'bg-red-500/20 text-red-400 border-red-500/30',
    icon: <Building size={12} />,
  },
};

function getEntityConfig(type: string) {
  return (
    entityTypeConfig[type.toLowerCase()] || {
      color: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
      icon: <Network size={12} />,
    }
  );
}

function EntityTypeBadge({ type }: { type: string }) {
  const config = getEntityConfig(type);
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium border',
        config.color
      )}
    >
      {config.icon}
      {type}
    </span>
  );
}

/* ---------- Search Section ---------- */

function SearchSection({
  onSelectEntity,
}: {
  onSelectEntity: (entity: KnowledgeEntity) => void;
}) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<KnowledgeEntity[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = useCallback(async () => {
    if (!query.trim()) return;
    setIsSearching(true);
    setError(null);
    setHasSearched(true);
    try {
      const response = await api.get<SearchResponse>('/v1/knowledge/search', {
        query: query.trim(),
      });
      setResults(response.results || []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Search failed');
      setResults([]);
    } finally {
      setIsSearching(false);
    }
  }, [query]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') handleSearch();
    },
    [handleSearch]
  );

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-display font-semibold tracking-wider text-jarvis-blue flex items-center gap-2">
        <Search size={15} />
        Search Knowledge
      </h3>

      {/* Search bar */}
      <div className="flex gap-2">
        <input
          type="text"
          placeholder="Search entities, topics, people..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          className="flex-1 jarvis-input rounded-lg px-3 py-2 text-sm"
        />
        <button
          onClick={handleSearch}
          disabled={!query.trim() || isSearching}
          className="jarvis-button rounded-xl px-4 py-2 text-sm font-medium flex-shrink-0 flex items-center gap-1.5"
        >
          {isSearching ? <Loader size={14} className="animate-spin" /> : <Search size={14} />}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-1.5 text-xs text-red-400">
          <AlertCircle size={12} />
          <span>{error}</span>
        </div>
      )}

      {/* Results */}
      {results.length > 0 && (
        <div className="space-y-2">
          {results.map((entity) => (
            <button
              key={entity.id}
              onClick={() => onSelectEntity(entity)}
              className="w-full text-left glass-panel rounded-lg px-3 py-2.5 hover:bg-white/[0.03] transition-all group"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-gray-200 font-medium group-hover:text-jarvis-blue transition-colors truncate">
                    {entity.name}
                  </p>
                  {entity.snippet && (
                    <p className="text-xs text-gray-500 mt-1 line-clamp-2">{entity.snippet}</p>
                  )}
                </div>
                <EntityTypeBadge type={entity.type} />
              </div>
            </button>
          ))}
        </div>
      )}

      {hasSearched && !isSearching && results.length === 0 && !error && (
        <p className="text-xs text-gray-500 text-center py-4">No results found.</p>
      )}
    </div>
  );
}

/* ---------- Entity Detail ---------- */

function EntityDetail({
  entity,
  onBack,
  onSelectEntity,
}: {
  entity: KnowledgeEntity;
  onBack: () => void;
  onSelectEntity: (entity: KnowledgeEntity) => void;
}) {
  const [detail, setDetail] = useState<KnowledgeEntity>(entity);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const fetchDetail = async () => {
      setIsLoading(true);
      try {
        const response = await api.get<KnowledgeEntity>(`/v1/knowledge/entities/${entity.id}`);
        if (!cancelled) setDetail(response);
      } catch {
        // Fall back to the entity data we already have
        if (!cancelled) setDetail(entity);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };
    fetchDetail();
    return () => {
      cancelled = true;
    };
  }, [entity]);

  return (
    <div className="space-y-4">
      {/* Back button */}
      <button
        onClick={onBack}
        className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-jarvis-blue transition-colors"
      >
        <ChevronLeft size={14} />
        Back to results
      </button>

      {isLoading ? (
        <div className="flex items-center justify-center py-8">
          <Loader size={20} className="animate-spin text-jarvis-blue" />
        </div>
      ) : (
        <>
          {/* Entity header */}
          <div className="glass-panel rounded-lg px-4 py-3 space-y-2">
            <div className="flex items-start justify-between gap-2">
              <h3 className="text-base font-display font-semibold text-gray-200">
                {detail.name}
              </h3>
              <EntityTypeBadge type={detail.type} />
            </div>
            {detail.snippet && <p className="text-xs text-gray-400">{detail.snippet}</p>}
          </div>

          {/* Properties */}
          {detail.properties && Object.keys(detail.properties).length > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs text-gray-500 uppercase tracking-wider font-medium">
                Properties
              </h4>
              <div className="glass-panel rounded-lg divide-y divide-jarvis-blue/10">
                {Object.entries(detail.properties).map(([key, value]) => (
                  <div key={key} className="px-3 py-2 flex items-center justify-between">
                    <span className="text-xs text-gray-500">{key}</span>
                    <span className="text-xs text-gray-300">{String(value)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Relationships */}
          {detail.relationships && detail.relationships.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs text-gray-500 uppercase tracking-wider font-medium flex items-center gap-1.5">
                <Network size={12} />
                Connected Entities
              </h4>
              <div className="space-y-1.5">
                {detail.relationships.map((rel) => (
                  <button
                    key={`${rel.entity_id}-${rel.relationship_type}`}
                    onClick={() =>
                      onSelectEntity({
                        id: rel.entity_id,
                        name: rel.entity_name,
                        type: rel.entity_type,
                      })
                    }
                    className="w-full text-left glass-panel rounded-lg px-3 py-2 hover:bg-white/[0.03] transition-all group"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="text-sm text-gray-300 group-hover:text-jarvis-blue transition-colors truncate">
                          {rel.entity_name}
                        </span>
                        <EntityTypeBadge type={rel.entity_type} />
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <span className="text-[10px] text-gray-600">{rel.relationship_type}</span>
                        {rel.strength !== undefined && (
                          <div className="w-12 bg-jarvis-darker rounded-full h-1">
                            <div
                              className="bg-jarvis-blue h-1 rounded-full"
                              style={{ width: `${Math.min(rel.strength * 100, 100)}%` }}
                            />
                          </div>
                        )}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Sources */}
          {detail.sources && detail.sources.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs text-gray-500 uppercase tracking-wider font-medium flex items-center gap-1.5">
                <FileText size={12} />
                Related Sources
              </h4>
              <div className="space-y-1.5">
                {detail.sources.map((source) => (
                  <div key={source.id} className="glass-panel rounded-lg px-3 py-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-300">{source.name}</span>
                      <span className="text-[10px] text-gray-600 capitalize">{source.type}</span>
                    </div>
                    {source.imported_at && (
                      <p className="text-[10px] text-gray-600 mt-0.5">
                        Imported {new Date(source.imported_at).toLocaleDateString()}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ---------- Sources Section ---------- */

function SourcesSection() {
  const [sources, setSources] = useState<EntitySource[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const fetchSources = async () => {
      try {
        const response = await api.get<SourcesResponse>('/v1/knowledge/sources');
        if (!cancelled) setSources(response.sources || []);
      } catch {
        // Silently handle -- sources may not be available yet
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };
    fetchSources();
    return () => {
      cancelled = true;
    };
  }, []);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-6">
        <Loader size={16} className="animate-spin text-jarvis-blue" />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-display font-semibold tracking-wider text-jarvis-blue flex items-center gap-2">
        <FileText size={15} />
        Knowledge Sources
      </h3>

      {sources.length === 0 ? (
        <p className="text-xs text-gray-500 text-center py-4">
          No knowledge sources imported yet.
        </p>
      ) : (
        <div className="space-y-1.5">
          {sources.map((source) => (
            <div key={source.id} className="glass-panel rounded-lg px-3 py-2.5">
              <div className="flex items-center justify-between">
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-gray-300 truncate">{source.name}</p>
                  {source.imported_at && (
                    <p className="text-[10px] text-gray-600 mt-0.5">
                      {new Date(source.imported_at).toLocaleDateString()}
                    </p>
                  )}
                </div>
                <span className="text-[10px] text-gray-600 capitalize px-2 py-0.5 rounded-full bg-white/[0.03] border border-white/[0.05]">
                  {source.type}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------- Main Panel ---------- */

type KnowledgeView = 'search' | 'detail' | 'sources';

export default function KnowledgePanel() {
  const [isOpen, setIsOpen] = useState(false);
  const [view, setView] = useState<KnowledgeView>('search');
  const [selectedEntity, setSelectedEntity] = useState<KnowledgeEntity | null>(null);

  useEffect(() => {
    const handler = () => {
      setIsOpen((prev) => !prev);
    };
    window.addEventListener('jarvis-knowledge-toggle', handler);
    return () => window.removeEventListener('jarvis-knowledge-toggle', handler);
  }, []);

  const handleClose = useCallback(() => {
    setIsOpen(false);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setIsOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const handleSelectEntity = useCallback((entity: KnowledgeEntity) => {
    setSelectedEntity(entity);
    setView('detail');
  }, []);

  const handleBackToSearch = useCallback(() => {
    setSelectedEntity(null);
    setView('search');
  }, []);

  const tabs: { id: KnowledgeView; label: string; icon: React.ReactNode }[] = [
    { id: 'search', label: 'Search', icon: <Search size={14} /> },
    { id: 'sources', label: 'Sources', icon: <FileText size={14} /> },
  ];

  const renderContent = () => {
    switch (view) {
      case 'search':
        return <SearchSection onSelectEntity={handleSelectEntity} />;
      case 'detail':
        return selectedEntity ? (
          <EntityDetail
            entity={selectedEntity}
            onBack={handleBackToSearch}
            onSelectEntity={handleSelectEntity}
          />
        ) : (
          <SearchSection onSelectEntity={handleSelectEntity} />
        );
      case 'sources':
        return <SourcesSection />;
    }
  };

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
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
            className="fixed right-5 top-5 bottom-5 w-full max-w-md z-50 glass-heavy rounded-3xl flex flex-col overflow-hidden"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-jarvis-blue/10">
              <h2 className="font-display text-sm font-semibold tracking-wider text-jarvis-blue flex items-center gap-2">
                <Brain size={16} />
                Knowledge Graph
              </h2>
              <button
                onClick={handleClose}
                className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-500 hover:text-jarvis-blue hover:bg-white/[0.03] transition-all"
                aria-label="Close knowledge panel"
              >
                <X size={16} />
              </button>
            </div>

            {/* Tabs -- only show when not in detail view */}
            {view !== 'detail' && (
              <div className="flex border-b border-jarvis-blue/10 px-2">
                {tabs.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setView(tab.id)}
                    className={clsx(
                      'flex items-center gap-1.5 px-4 py-2.5 text-xs font-medium transition-all border-b-2 -mb-px',
                      {
                        'border-jarvis-blue text-jarvis-blue': view === tab.id,
                        'border-transparent text-gray-500 hover:text-gray-300': view !== tab.id,
                      }
                    )}
                  >
                    {tab.icon}
                    {tab.label}
                  </button>
                ))}
              </div>
            )}

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-4">{renderContent()}</div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
