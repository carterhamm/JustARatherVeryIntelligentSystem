import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
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
  PenSquare,
  ChevronDown,
  Globe,
  MapPin,
  Cake,
  FileText,
  Plus,
  Save,
  ArrowLeft,
} from 'lucide-react';
import { api } from '@/services/api';
import clsx from 'clsx';

// ── Types ──────────────────────────────────────────────────────────────

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
  raw_vcard?: string | null;
  extra_fields?: string | null;
  created_at: string;
}

interface ExtraFields {
  all_phones?: { value: string; params?: Record<string, string> }[];
  all_emails?: { value: string; params?: Record<string, string> }[];
  all_addresses?: Record<string, string>[];
  [key: string]: unknown;
}

interface UploadResult {
  imported: number;
  skipped: number;
  errors: number;
  message: string;
}

type UploadStatus = 'idle' | 'uploading' | 'success' | 'error';
type PanelView = 'list' | 'edit' | 'create';

// ── Helpers ─────────────────────────────────────────────────────────────

function parseExtraFields(raw: string | null | undefined): ExtraFields {
  if (!raw) return {};
  try {
    return JSON.parse(raw);
  } catch {
    return {};
  }
}

function getPhotoSrc(contact: Contact): string | null {
  if (!contact.photo) return null;
  if (contact.photo.startsWith('data:')) return contact.photo;
  const mime = contact.photo_content_type || 'image/jpeg';
  return `data:${mime};base64,${contact.photo}`;
}

function getInitials(c: Contact): string {
  const f = (c.first_name || '')[0] || '';
  const l = (c.last_name || '')[0] || '';
  return (f + l).toUpperCase() || '?';
}

// ── Contact Edit Form ───────────────────────────────────────────────────

interface EditFormProps {
  contact: Contact | null; // null = create mode
  onSave: (data: Partial<Contact>) => Promise<void>;
  onCancel: () => void;
  saving: boolean;
}

function EditForm({ contact, onSave, onCancel, saving }: EditFormProps) {
  const isCreate = !contact;
  const extra = useMemo(() => parseExtraFields(contact?.extra_fields), [contact?.extra_fields]);

  const [form, setForm] = useState({
    first_name: contact?.first_name || '',
    last_name: contact?.last_name || '',
    phone: contact?.phone || '',
    email: contact?.email || '',
    company: contact?.company || '',
    title: contact?.title || '',
    street: contact?.street || '',
    city: contact?.city || '',
    state: contact?.state || '',
    postal_code: contact?.postal_code || '',
    country: contact?.country || '',
    birthday: contact?.birthday || '',
    url: contact?.url || '',
    notes: contact?.notes || '',
  });

  const set = (field: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm((prev) => ({ ...prev, [field]: e.target.value }));

  // Get all phone numbers and emails for default selection
  const allPhones = useMemo(() => {
    const phones: { value: string; label: string }[] = [];
    if (contact?.phone) phones.push({ value: contact.phone, label: contact.phone });
    if (extra.all_phones) {
      for (const p of extra.all_phones) {
        if (p.value && !phones.find((x) => x.value === p.value)) {
          const typeLabel = p.params?.TYPE || p.params?.type || '';
          phones.push({ value: p.value, label: `${p.value}${typeLabel ? ` (${typeLabel})` : ''}` });
        }
      }
    }
    return phones;
  }, [contact, extra]);

  const allEmails = useMemo(() => {
    const emails: { value: string; label: string }[] = [];
    if (contact?.email) emails.push({ value: contact.email, label: contact.email });
    if (extra.all_emails) {
      for (const e of extra.all_emails) {
        if (e.value && !emails.find((x) => x.value === e.value)) {
          const typeLabel = e.params?.TYPE || e.params?.type || '';
          emails.push({ value: e.value, label: `${e.value}${typeLabel ? ` (${typeLabel})` : ''}` });
        }
      }
    }
    return emails;
  }, [contact, extra]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.first_name.trim()) return;

    // Build address from components
    const parts = [form.street, form.city, form.state, form.postal_code, form.country].filter(Boolean);
    const address = parts.join(', ');

    const data: Partial<Contact> = {
      ...form,
      address: address || undefined,
    };

    // Clean empty strings to undefined for update
    if (!isCreate) {
      for (const [k, v] of Object.entries(data)) {
        if (v === '' && k !== 'first_name') {
          (data as Record<string, unknown>)[k] = null;
        }
      }
    }

    await onSave(data);
  };

  const photoSrc = contact ? getPhotoSrc(contact) : null;

  return (
    <form onSubmit={handleSubmit} className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-jarvis-blue/10">
        <button type="button" onClick={onCancel} className="text-gray-500 hover:text-jarvis-blue transition-colors">
          <ArrowLeft size={16} />
        </button>
        <h2 className="font-display text-sm font-semibold tracking-wider text-jarvis-blue">
          {isCreate ? 'NEW CONTACT' : 'EDIT CONTACT'}
        </h2>
      </div>

      {/* Scrollable form body */}
      <div className="flex-1 overflow-y-auto scrollbar-thin px-4 py-4 space-y-4">
        {/* Photo & Name header */}
        <div className="flex items-center gap-3 mb-2">
          {photoSrc ? (
            <img src={photoSrc} alt="" className="w-12 h-12 rounded-full object-cover border border-jarvis-blue/20" />
          ) : (
            <div className="w-12 h-12 rounded-full bg-jarvis-blue/10 border border-jarvis-blue/20 flex items-center justify-center">
              <span className="text-sm font-mono text-jarvis-blue/60">
                {form.first_name ? getInitials({ ...contact!, first_name: form.first_name, last_name: form.last_name }) : '?'}
              </span>
            </div>
          )}
          <div className="flex-1 space-y-2">
            <FormField label="First Name" value={form.first_name} onChange={set('first_name')} required />
            <FormField label="Last Name" value={form.last_name} onChange={set('last_name')} />
          </div>
        </div>

        {/* Default Phone selector */}
        <FieldGroup label="PHONE" icon={<Phone size={10} />}>
          {allPhones.length > 1 ? (
            <div className="space-y-1.5">
              <select
                value={form.phone}
                onChange={(e) => setForm((prev) => ({ ...prev, phone: e.target.value }))}
                className="w-full jarvis-input hud-clip-sm px-3 py-2 text-sm font-mono bg-transparent appearance-none"
              >
                {allPhones.map((p) => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
              <p className="text-[8px] text-gray-600 font-mono tracking-wider">DEFAULT PHONE — SHOWN ON CONTACT CARD</p>
            </div>
          ) : (
            <FormField label="Phone" value={form.phone} onChange={set('phone')} type="tel" />
          )}
        </FieldGroup>

        {/* Default Email selector */}
        <FieldGroup label="EMAIL" icon={<Mail size={10} />}>
          {allEmails.length > 1 ? (
            <div className="space-y-1.5">
              <select
                value={form.email}
                onChange={(e) => setForm((prev) => ({ ...prev, email: e.target.value }))}
                className="w-full jarvis-input hud-clip-sm px-3 py-2 text-sm font-mono bg-transparent appearance-none"
              >
                {allEmails.map((em) => (
                  <option key={em.value} value={em.value}>{em.label}</option>
                ))}
              </select>
              <p className="text-[8px] text-gray-600 font-mono tracking-wider">DEFAULT EMAIL — SHOWN ON CONTACT CARD</p>
            </div>
          ) : (
            <FormField label="Email" value={form.email} onChange={set('email')} type="email" />
          )}
        </FieldGroup>

        {/* Organization */}
        <FieldGroup label="ORGANIZATION" icon={<Building size={10} />}>
          <FormField label="Company" value={form.company} onChange={set('company')} />
          <FormField label="Title" value={form.title} onChange={set('title')} />
        </FieldGroup>

        {/* Address */}
        <FieldGroup label="ADDRESS" icon={<MapPin size={10} />}>
          <FormField label="Street" value={form.street} onChange={set('street')} />
          <div className="grid grid-cols-2 gap-2">
            <FormField label="City" value={form.city} onChange={set('city')} />
            <FormField label="State" value={form.state} onChange={set('state')} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <FormField label="Postal Code" value={form.postal_code} onChange={set('postal_code')} />
            <FormField label="Country" value={form.country} onChange={set('country')} />
          </div>
        </FieldGroup>

        {/* Other */}
        <FieldGroup label="OTHER" icon={<FileText size={10} />}>
          <FormField label="Birthday" value={form.birthday} onChange={set('birthday')} placeholder="YYYY-MM-DD" />
          <FormField label="Website" value={form.url} onChange={set('url')} placeholder="https://" />
          <div>
            <label className="text-[9px] text-gray-500 font-mono tracking-wider block mb-1">Notes</label>
            <textarea
              value={form.notes}
              onChange={set('notes')}
              rows={3}
              className="w-full jarvis-input hud-clip-sm px-3 py-2 text-sm font-mono resize-none"
            />
          </div>
        </FieldGroup>

        {/* Extra fields (read-only display) */}
        {contact?.extra_fields && Object.keys(extra).filter((k) => !['all_phones', 'all_emails', 'all_addresses'].includes(k)).length > 0 && (
          <FieldGroup label="ADDITIONAL DATA" icon={<ChevronDown size={10} />}>
            <div className="space-y-1">
              {Object.entries(extra)
                .filter(([k]) => !['all_phones', 'all_emails', 'all_addresses'].includes(k))
                .map(([key, val]) => (
                  <div key={key} className="flex items-start gap-2">
                    <span className="text-[9px] text-gray-600 font-mono uppercase w-20 flex-shrink-0 pt-0.5">{key}</span>
                    <span className="text-[10px] text-gray-400 font-mono break-all">
                      {typeof val === 'object' ? JSON.stringify(val) : String((val as { value?: string })?.value ?? val)}
                    </span>
                  </div>
                ))}
            </div>
          </FieldGroup>
        )}
      </div>

      {/* Save button */}
      <div className="px-4 py-3 border-t border-white/[0.04]">
        <button
          type="submit"
          disabled={saving || !form.first_name.trim()}
          className="jarvis-button hud-clip-sm w-full px-4 py-2.5 text-sm font-medium flex items-center justify-center gap-2 disabled:opacity-40"
        >
          {saving ? <Loader size={14} className="animate-spin" /> : <Save size={14} />}
          {isCreate ? 'Create Contact' : 'Save Changes'}
        </button>
      </div>
    </form>
  );
}

// ── Shared form components ──────────────────────────────────────────────

function FormField({
  label,
  value,
  onChange,
  type = 'text',
  required = false,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  type?: string;
  required?: boolean;
  placeholder?: string;
}) {
  return (
    <div>
      <label className="text-[9px] text-gray-500 font-mono tracking-wider block mb-1">{label}</label>
      <input
        type={type}
        value={value}
        onChange={onChange}
        required={required}
        placeholder={placeholder}
        className="w-full jarvis-input hud-clip-sm px-3 py-1.5 text-sm font-mono"
      />
    </div>
  );
}

function FieldGroup({ label, icon, children }: { label: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1.5 mb-1">
        <span className="text-jarvis-blue/40">{icon}</span>
        <span className="text-[8px] text-gray-600 font-mono tracking-[0.2em]">{label}</span>
      </div>
      <div className="space-y-2 pl-1 border-l border-white/[0.04]">
        <div className="pl-3 space-y-2">{children}</div>
      </div>
    </div>
  );
}

// ── Main Panel ──────────────────────────────────────────────────────────

export default function ContactsPanel() {
  const [isOpen, setIsOpen] = useState(false);
  const [view, setView] = useState<PanelView>('list');
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [editingContact, setEditingContact] = useState<Contact | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Contact[] | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
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
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (view !== 'list') {
          setView('list');
          setEditingContact(null);
        } else {
          setIsOpen(false);
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [view]);

  // Load contacts when panel opens
  useEffect(() => {
    if (isOpen) {
      loadContacts();
      loadCount();
      setView('list');
      setEditingContact(null);
    }
  }, [isOpen]);

  const loadContacts = useCallback(async () => {
    setIsLoading(true);
    try {
      const result = await api.get<Contact[]>('/contacts', { limit: 200 });
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

  // Multi-file upload
  const handleUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setUploadStatus('uploading');
    setUploadMessage(`Importing ${files.length} file${files.length > 1 ? 's' : ''}...`);

    let totalImported = 0;
    let totalErrors = 0;

    for (const file of Array.from(files)) {
      const formData = new FormData();
      formData.append('file', file);
      try {
        const result = await api.postFormData<UploadResult>('/contacts/upload', formData);
        totalImported += result.imported;
        totalErrors += result.errors;
      } catch {
        totalErrors++;
      }
    }

    setUploadStatus(totalErrors > 0 && totalImported === 0 ? 'error' : 'success');
    setUploadMessage(
      `Imported ${totalImported} contact${totalImported !== 1 ? 's' : ''}.${totalErrors > 0 ? ` ${totalErrors} error${totalErrors !== 1 ? 's' : ''}.` : ''}`
    );
    loadContacts();
    loadCount();

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

  const handleEdit = useCallback((contact: Contact) => {
    setEditingContact(contact);
    setView('edit');
  }, []);

  const handleCreate = useCallback(() => {
    setEditingContact(null);
    setView('create');
  }, []);

  const handleSave = useCallback(async (data: Partial<Contact>) => {
    setIsSaving(true);
    try {
      if (editingContact) {
        // Update existing
        const updated = await api.put<Contact>(`/contacts/${editingContact.id}`, data);
        setContacts((prev) => prev.map((c) => (c.id === editingContact.id ? updated : c)));
        if (searchResults) {
          setSearchResults((prev) => prev?.map((c) => (c.id === editingContact.id ? updated : c)) ?? null);
        }
      } else {
        // Create new
        await api.post<Contact>('/contacts', data);
        loadContacts();
        loadCount();
      }
      setView('list');
      setEditingContact(null);
    } catch {
      // silently fail
    } finally {
      setIsSaving(false);
    }
  }, [editingContact, searchResults, loadContacts, loadCount]);

  const handleCancelEdit = useCallback(() => {
    setView('list');
    setEditingContact(null);
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
            {view === 'list' ? (
              <>
                {/* Header */}
                <div className="flex items-center justify-between px-4 py-3 border-b border-jarvis-blue/10">
                  <h2 className="font-display text-sm font-semibold tracking-wider text-jarvis-blue flex items-center gap-2">
                    <Users size={16} />
                    Contacts
                    {totalCount > 0 && (
                      <span className="text-[10px] text-gray-500 font-mono">({totalCount})</span>
                    )}
                  </h2>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleCreate}
                      className="text-gray-500 hover:text-jarvis-blue transition-colors p-1"
                      title="New Contact"
                    >
                      <Plus size={16} />
                    </button>
                    <button onClick={handleClose} className="text-gray-500 hover:text-jarvis-blue transition-colors">
                      <X size={16} />
                    </button>
                  </div>
                </div>

                {/* Upload section */}
                <div className="px-4 py-3 border-b border-white/[0.04]">
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".vcf,.csv"
                    multiple
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
                        <ContactRow
                          key={contact.id}
                          contact={contact}
                          onEdit={handleEdit}
                          onDelete={handleDelete}
                        />
                      ))}
                    </div>
                  )}
                </div>

                {/* Footer */}
                {totalCount > 0 && (
                  <div className="px-4 py-2 border-t border-white/[0.04] flex items-center justify-between">
                    <span className="text-[10px] text-gray-600 font-mono">{totalCount} CONTACTS ENCRYPTED</span>
                  </div>
                )}
              </>
            ) : (
              <EditForm
                contact={view === 'edit' ? editingContact : null}
                onSave={handleSave}
                onCancel={handleCancelEdit}
                saving={isSaving}
              />
            )}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

// ── Contact Row ─────────────────────────────────────────────────────────

function ContactRow({
  contact,
  onEdit,
  onDelete,
}: {
  contact: Contact;
  onEdit: (c: Contact) => void;
  onDelete: (id: string) => void;
}) {
  const photoSrc = getPhotoSrc(contact);

  return (
    <div className="px-4 py-3 hover:bg-white/[0.02] transition-colors group">
      <div className="flex items-start gap-3">
        {/* Avatar */}
        <div className="flex-shrink-0 mt-0.5">
          {photoSrc ? (
            <img src={photoSrc} alt="" className="w-8 h-8 rounded-full object-cover border border-jarvis-blue/15" />
          ) : (
            <div className="w-8 h-8 rounded-full bg-jarvis-blue/[0.06] border border-jarvis-blue/15 flex items-center justify-center">
              <span className="text-[10px] font-mono text-jarvis-blue/50">{getInitials(contact)}</span>
            </div>
          )}
        </div>

        {/* Info */}
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

        {/* Actions */}
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-all">
          <button
            onClick={() => onEdit(contact)}
            className="text-gray-600 hover:text-jarvis-blue transition-colors p-1"
            title="Edit contact"
          >
            <PenSquare size={12} />
          </button>
          <button
            onClick={() => onDelete(contact.id)}
            className="text-gray-600 hover:text-red-400 transition-colors p-1"
            title="Delete contact"
          >
            <Trash2 size={12} />
          </button>
        </div>
      </div>
    </div>
  );
}
