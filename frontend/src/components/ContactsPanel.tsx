import { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  X,
  Upload,
  Search,
  Users,
  Phone,
  Mail,
  Building,
  Trash2,
  Loader,
  CheckCircle,
  AlertCircle,
  User,
} from 'lucide-react';
import { api } from '@/services/api';
import clsx from 'clsx';

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

interface UploadResult {
  imported: number;
  skipped: number;
  errors: number;
  message: string;
}

type UploadStatus = 'idle' | 'uploading' | 'success' | 'error';

export default function ContactsPanel() {
  const [isOpen, setIsOpen] = useState(false);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Contact[] | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [totalCount, setTotalCount] = useState(0);
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>('idle');
  const [uploadMessage, setUploadMessage] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const searchTimeoutRef = useRef<ReturnType<typeof setTimeout>>();

  // Toggle listener
  useEffect(() => {
    const handler = () => setIsOpen((prev) => !prev);
    window.addEventListener('jarvis-contacts-toggle', handler);
    return () => window.removeEventListener('jarvis-contacts-toggle', handler);
  }, []);

  // Escape key
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setIsOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Load contacts when panel opens
  useEffect(() => {
    if (isOpen) {
      loadContacts();
      loadCount();
    }
  }, [isOpen]);

  const loadContacts = useCallback(async () => {
    setIsLoading(true);
    try {
      const result = await api.get<Contact[]>('/contacts', { limit: 50 });
      setContacts(result);
    } catch {
      // silently fail
    } finally {
      setIsLoading(false);
    }
  }, []);

  const loadCount = useCallback(async () => {
    try {
      const result = await api.get<{ count: number }>('/contacts/count');
      setTotalCount(result.count);
    } catch {
      // silently fail
    }
  }, []);

  // Debounced search
  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults(null);
      return;
    }
    clearTimeout(searchTimeoutRef.current);
    searchTimeoutRef.current = setTimeout(async () => {
      setIsSearching(true);
      try {
        const result = await api.get<Contact[]>('/contacts/search', { q: searchQuery.trim() });
        setSearchResults(result);
      } catch {
        setSearchResults([]);
      } finally {
        setIsSearching(false);
      }
    }, 300);
    return () => clearTimeout(searchTimeoutRef.current);
  }, [searchQuery]);

  const handleUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploadStatus('uploading');
    setUploadMessage('Importing contacts...');

    const formData = new FormData();
    formData.append('file', file);

    try {
      const result = await api.postFormData<UploadResult>('/contacts/upload', formData);
      setUploadStatus('success');
      setUploadMessage(result.message);
      loadContacts();
      loadCount();
    } catch (err: unknown) {
      setUploadStatus('error');
      setUploadMessage(err instanceof Error ? err.message : 'Upload failed');
    }

    // Reset file input
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, [loadContacts, loadCount]);

  const handleDelete = useCallback(async (id: string) => {
    try {
      await api.delete(`/contacts/${id}`);
      setContacts((prev) => prev.filter((c) => c.id !== id));
      setTotalCount((prev) => prev - 1);
      if (searchResults) {
        setSearchResults((prev) => prev?.filter((c) => c.id !== id) ?? null);
      }
    } catch {
      // silently fail
    }
  }, [searchResults]);

  const handleDeleteAll = useCallback(async () => {
    try {
      await api.delete('/contacts');
      setContacts([]);
      setSearchResults(null);
      setTotalCount(0);
    } catch {
      // silently fail
    }
  }, []);

  const handleClose = useCallback(() => setIsOpen(false), []);

  const displayList = searchResults ?? contacts;

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
            className="fixed left-5 top-5 bottom-5 w-full max-w-md z-50 glass-heavy hud-clip flex flex-col overflow-hidden"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-jarvis-blue/10">
              <h2 className="font-display text-sm font-semibold tracking-wider text-jarvis-blue flex items-center gap-2">
                <Users size={16} />
                Contacts
                {totalCount > 0 && (
                  <span className="text-[10px] text-gray-500 font-mono">({totalCount})</span>
                )}
              </h2>
              <button onClick={handleClose} className="text-gray-500 hover:text-jarvis-blue transition-colors">
                <X size={16} />
              </button>
            </div>

            {/* Upload section */}
            <div className="px-4 py-3 border-b border-white/[0.04]">
              <input
                ref={fileInputRef}
                type="file"
                accept=".vcf,.csv"
                onChange={handleUpload}
                className="hidden"
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={uploadStatus === 'uploading'}
                className="jarvis-button hud-clip-sm w-full px-4 py-2.5 text-sm font-medium flex items-center justify-center gap-2"
              >
                {uploadStatus === 'uploading' ? (
                  <Loader size={14} className="animate-spin" />
                ) : (
                  <Upload size={14} />
                )}
                Upload Contacts (.vcf / .csv)
              </button>
              {uploadStatus !== 'idle' && (
                <div
                  className={clsx('flex items-center gap-1.5 mt-2 text-xs', {
                    'text-jarvis-blue': uploadStatus === 'uploading',
                    'text-green-400': uploadStatus === 'success',
                    'text-red-400': uploadStatus === 'error',
                  })}
                >
                  {uploadStatus === 'uploading' && <Loader size={12} className="animate-spin" />}
                  {uploadStatus === 'success' && <CheckCircle size={12} />}
                  {uploadStatus === 'error' && <AlertCircle size={12} />}
                  <span>{uploadMessage}</span>
                </div>
              )}
            </div>

            {/* Search */}
            <div className="px-4 py-2 border-b border-white/[0.04]">
              <div className="relative">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-jarvis-blue/40" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search contacts..."
                  className="w-full jarvis-input hud-clip-sm pl-9 pr-3 py-2 text-sm font-mono"
                />
                {isSearching && (
                  <Loader size={12} className="absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-jarvis-blue" />
                )}
              </div>
            </div>

            {/* Contact list */}
            <div className="flex-1 overflow-y-auto scrollbar-thin">
              {isLoading && !contacts.length ? (
                <div className="flex items-center justify-center py-12 text-gray-500">
                  <Loader size={16} className="animate-spin" />
                </div>
              ) : displayList.length === 0 ? (
                <div className="text-center py-12 px-4">
                  <User size={24} className="mx-auto text-gray-600 mb-2" />
                  <p className="text-sm text-gray-500">
                    {searchQuery ? 'No contacts match your search.' : 'No contacts yet. Upload a .vcf or .csv file to get started.'}
                  </p>
                </div>
              ) : (
                <div className="divide-y divide-white/[0.03]">
                  {displayList.map((contact) => (
                    <div
                      key={contact.id}
                      className="px-4 py-3 hover:bg-white/[0.02] transition-colors group"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium text-gray-200 truncate">
                            {contact.first_name} {contact.last_name || ''}
                          </p>
                          {contact.company && (
                            <div className="flex items-center gap-1 mt-0.5">
                              <Building size={10} className="text-gray-600 flex-shrink-0" />
                              <span className="text-[11px] text-gray-500 truncate">
                                {contact.title ? `${contact.title} at ` : ''}
                                {contact.company}
                              </span>
                            </div>
                          )}
                          <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1">
                            {contact.phone && (
                              <span className="flex items-center gap-1 text-[11px] text-gray-400">
                                <Phone size={9} className="text-jarvis-blue/40" />
                                {contact.phone}
                              </span>
                            )}
                            {contact.email && (
                              <span className="flex items-center gap-1 text-[11px] text-gray-400">
                                <Mail size={9} className="text-jarvis-blue/40" />
                                {contact.email}
                              </span>
                            )}
                          </div>
                        </div>
                        <button
                          onClick={() => handleDelete(contact.id)}
                          className="opacity-0 group-hover:opacity-100 text-gray-600 hover:text-red-400 transition-all p-1"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Footer */}
            {totalCount > 0 && (
              <div className="px-4 py-2 border-t border-white/[0.04] flex items-center justify-between">
                <span className="text-[10px] text-gray-600 font-mono">{totalCount} CONTACTS ENCRYPTED</span>
                <button
                  onClick={handleDeleteAll}
                  className="text-[10px] text-gray-600 hover:text-red-400 transition-colors font-mono"
                >
                  DELETE ALL
                </button>
              </div>
            )}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
