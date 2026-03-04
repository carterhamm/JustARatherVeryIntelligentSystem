import { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  X,
  Upload,
  FileText,
  Globe,
  MessageSquare,
  Mail,
  Facebook,
  CheckCircle,
  AlertCircle,
  Loader,
} from 'lucide-react';
import { api } from '@/services/api';
import clsx from 'clsx';

type ImportStatus = 'idle' | 'importing' | 'success' | 'error';

interface ImportResult {
  entities_extracted?: number;
  message?: string;
  [key: string]: unknown;
}

function StatusIndicator({ status, message }: { status: ImportStatus; message?: string }) {
  if (status === 'idle') return null;

  return (
    <div
      className={clsx('flex items-center gap-1.5 mt-2 text-xs', {
        'text-jarvis-blue': status === 'importing',
        'text-green-400': status === 'success',
        'text-red-400': status === 'error',
      })}
    >
      {status === 'importing' && <Loader size={12} className="animate-spin" />}
      {status === 'success' && <CheckCircle size={12} />}
      {status === 'error' && <AlertCircle size={12} />}
      <span>{message || status}</span>
    </div>
  );
}

function TextImportSection() {
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [status, setStatus] = useState<ImportStatus>('idle');
  const [statusMessage, setStatusMessage] = useState('');

  const handleSubmit = useCallback(async () => {
    if (!content.trim()) return;
    setStatus('importing');
    setStatusMessage('Importing text...');
    try {
      const result = await api.post<ImportResult>('/v1/data_import/text', {
        title: title.trim() || undefined,
        content: content.trim(),
      });
      const count = result.entities_extracted ?? 0;
      setStatus('success');
      setStatusMessage(`Imported successfully. ${count} entities extracted.`);
      setTitle('');
      setContent('');
    } catch (err: unknown) {
      setStatus('error');
      const message = err instanceof Error ? err.message : 'Import failed';
      setStatusMessage(message);
    }
  }, [title, content]);

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-display font-semibold tracking-wider text-jarvis-blue flex items-center gap-2">
        <FileText size={15} />
        Text Import
      </h3>
      <input
        type="text"
        placeholder="Title (optional)"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        className="w-full jarvis-input rounded-lg px-3 py-2 text-sm"
      />
      <textarea
        placeholder="Paste text content here..."
        value={content}
        onChange={(e) => setContent(e.target.value)}
        rows={4}
        className="w-full jarvis-input rounded-lg px-3 py-2 text-sm resize-none"
      />
      <button
        onClick={handleSubmit}
        disabled={!content.trim() || status === 'importing'}
        className="jarvis-button-gold jarvis-button rounded-xl px-4 py-2 text-sm font-medium flex items-center gap-2"
      >
        <Upload size={14} />
        Import Text
      </button>
      <StatusIndicator status={status} message={statusMessage} />
    </div>
  );
}

function FileUploadSection() {
  const [status, setStatus] = useState<ImportStatus>('idle');
  const [statusMessage, setStatusMessage] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const [progress, setProgress] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFiles = useCallback(async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const file = files[0];
    const allowedTypes = [
      'application/pdf',
      'text/plain',
      'text/markdown',
      'application/octet-stream',
    ];
    const allowedExtensions = ['.pdf', '.txt', '.md'];
    const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();

    if (!allowedTypes.includes(file.type) && !allowedExtensions.includes(ext)) {
      setStatus('error');
      setStatusMessage('Only PDF, TXT, and MD files are supported.');
      return;
    }

    setStatus('importing');
    setProgress(0);
    setStatusMessage(`Uploading ${file.name}...`);

    const formData = new FormData();
    formData.append('file', file);

    // Simulate progress since we can't track real upload progress with api client
    const progressInterval = setInterval(() => {
      setProgress((prev) => Math.min(prev + 10, 90));
    }, 300);

    try {
      const result = await api.postFormData<ImportResult>('/v1/data_import/file', formData);
      clearInterval(progressInterval);
      setProgress(100);
      const count = result.entities_extracted ?? 0;
      setStatus('success');
      setStatusMessage(`${file.name} imported. ${count} entities extracted.`);
    } catch (err: unknown) {
      clearInterval(progressInterval);
      setStatus('error');
      const message = err instanceof Error ? err.message : 'Upload failed';
      setStatusMessage(message);
    }
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      handleFiles(e.dataTransfer.files);
    },
    [handleFiles]
  );

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-display font-semibold tracking-wider text-jarvis-blue flex items-center gap-2">
        <Upload size={15} />
        File Upload
      </h3>
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={clsx(
          'border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all',
          {
            'border-jarvis-blue/50 bg-jarvis-blue/5': isDragging,
            'border-jarvis-blue/20 hover:border-jarvis-blue/40 hover:bg-white/[0.02]': !isDragging,
          }
        )}
      >
        <Upload size={24} className="mx-auto text-gray-500 mb-2" />
        <p className="text-sm text-gray-400">Drop PDF, TXT, or MD files here</p>
        <p className="text-xs text-gray-600 mt-1">or click to browse</p>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.txt,.md"
          onChange={(e) => handleFiles(e.target.files)}
          className="hidden"
        />
      </div>
      {status === 'importing' && (
        <div className="w-full bg-jarvis-darker rounded-full h-1.5">
          <div
            className="bg-jarvis-blue h-1.5 rounded-full transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}
      <StatusIndicator status={status} message={statusMessage} />
    </div>
  );
}

function UrlImportSection() {
  const [url, setUrl] = useState('');
  const [status, setStatus] = useState<ImportStatus>('idle');
  const [statusMessage, setStatusMessage] = useState('');

  const handleSubmit = useCallback(async () => {
    if (!url.trim()) return;
    setStatus('importing');
    setStatusMessage('Fetching and importing page...');
    try {
      const result = await api.post<ImportResult>('/v1/data_import/url', {
        url: url.trim(),
      });
      const count = result.entities_extracted ?? 0;
      setStatus('success');
      setStatusMessage(`Page imported. ${count} entities extracted.`);
      setUrl('');
    } catch (err: unknown) {
      setStatus('error');
      const message = err instanceof Error ? err.message : 'Import failed';
      setStatusMessage(message);
    }
  }, [url]);

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-display font-semibold tracking-wider text-jarvis-blue flex items-center gap-2">
        <Globe size={15} />
        URL Import
      </h3>
      <div className="flex gap-2">
        <input
          type="url"
          placeholder="https://example.com/article"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          className="flex-1 jarvis-input rounded-lg px-3 py-2 text-sm"
        />
        <button
          onClick={handleSubmit}
          disabled={!url.trim() || status === 'importing'}
          className="jarvis-button-gold jarvis-button rounded-xl px-4 py-2 text-sm font-medium flex-shrink-0"
        >
          Import
        </button>
      </div>
      <StatusIndicator status={status} message={statusMessage} />
    </div>
  );
}

function IMessageSection() {
  const [dbPath, setDbPath] = useState('~/Library/Messages/chat.db');
  const [status, setStatus] = useState<ImportStatus>('idle');
  const [statusMessage, setStatusMessage] = useState('');

  const handleImport = useCallback(async () => {
    setStatus('importing');
    setStatusMessage('Importing iMessage data...');
    try {
      const result = await api.post<ImportResult>('/v1/data_import/imessage', {
        db_path: dbPath,
      });
      const count = result.entities_extracted ?? 0;
      setStatus('success');
      setStatusMessage(`iMessage import complete. ${count} entities extracted.`);
    } catch (err: unknown) {
      setStatus('error');
      const message = err instanceof Error ? err.message : 'Import failed';
      setStatusMessage(message);
    }
  }, [dbPath]);

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-display font-semibold tracking-wider text-jarvis-blue flex items-center gap-2">
        <MessageSquare size={15} />
        iMessage
      </h3>
      <input
        type="text"
        placeholder="Path to chat.db"
        value={dbPath}
        onChange={(e) => setDbPath(e.target.value)}
        className="w-full jarvis-input rounded-lg px-3 py-2 text-sm font-mono text-xs"
      />
      <button
        onClick={handleImport}
        disabled={status === 'importing'}
        className="jarvis-button-gold jarvis-button rounded-xl px-4 py-2 text-sm font-medium flex items-center gap-2"
      >
        <MessageSquare size={14} />
        Import iMessage
      </button>
      <StatusIndicator status={status} message={statusMessage} />
    </div>
  );
}

function GmailSection() {
  const [status, setStatus] = useState<ImportStatus>('idle');
  const [statusMessage, setStatusMessage] = useState('');

  const handleSync = useCallback(async () => {
    setStatus('importing');
    setStatusMessage('Initiating Gmail OAuth sync...');
    try {
      const result = await api.post<ImportResult>('/v1/data_import/gmail');
      const count = result.entities_extracted ?? 0;
      setStatus('success');
      setStatusMessage(`Gmail sync complete. ${count} entities extracted.`);
    } catch (err: unknown) {
      setStatus('error');
      const message = err instanceof Error ? err.message : 'Gmail sync failed. Ensure OAuth is configured.';
      setStatusMessage(message);
    }
  }, []);

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-display font-semibold tracking-wider text-jarvis-blue flex items-center gap-2">
        <Mail size={15} />
        Gmail Sync
      </h3>
      <p className="text-xs text-gray-500">
        Requires OAuth credentials configured on the server.
      </p>
      <button
        onClick={handleSync}
        disabled={status === 'importing'}
        className="jarvis-button-gold jarvis-button rounded-xl px-4 py-2 text-sm font-medium flex items-center gap-2"
      >
        <Mail size={14} />
        Sync Gmail
      </button>
      <StatusIndicator status={status} message={statusMessage} />
    </div>
  );
}

function FacebookSection() {
  const [status, setStatus] = useState<ImportStatus>('idle');
  const [statusMessage, setStatusMessage] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const file = files[0];

    if (!file.name.endsWith('.zip')) {
      setStatus('error');
      setStatusMessage('Please upload a Facebook data export ZIP file.');
      return;
    }

    setStatus('importing');
    setStatusMessage(`Uploading ${file.name}...`);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const result = await api.postFormData<ImportResult>('/v1/data_import/facebook', formData);
      const count = result.entities_extracted ?? 0;
      setStatus('success');
      setStatusMessage(`Facebook data imported. ${count} entities extracted.`);
    } catch (err: unknown) {
      setStatus('error');
      const message = err instanceof Error ? err.message : 'Import failed';
      setStatusMessage(message);
    }
  }, []);

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-display font-semibold tracking-wider text-jarvis-blue flex items-center gap-2">
        <Facebook size={15} />
        Facebook
      </h3>
      <p className="text-xs text-gray-500">
        Upload your Facebook data export ZIP file.
      </p>
      <button
        onClick={() => fileInputRef.current?.click()}
        disabled={status === 'importing'}
        className="jarvis-button-gold jarvis-button rounded-xl px-4 py-2 text-sm font-medium flex items-center gap-2"
      >
        <Upload size={14} />
        Upload Facebook Export
      </button>
      <input
        ref={fileInputRef}
        type="file"
        accept=".zip"
        onChange={(e) => handleFile(e.target.files)}
        className="hidden"
      />
      <StatusIndicator status={status} message={statusMessage} />
    </div>
  );
}

export default function DataImportPanel() {
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    const handler = () => {
      setIsOpen((prev) => !prev);
    };
    window.addEventListener('jarvis-import-toggle', handler);
    return () => window.removeEventListener('jarvis-import-toggle', handler);
  }, []);

  const handleClose = useCallback(() => {
    setIsOpen(false);
  }, []);

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

          {/* Panel - slides from left */}
          <motion.div
            initial={{ x: '-100%' }}
            animate={{ x: 0 }}
            exit={{ x: '-100%' }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
            className="fixed left-5 top-5 bottom-5 w-full max-w-md z-50 glass-heavy rounded-3xl flex flex-col overflow-hidden"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-jarvis-blue/10">
              <h2 className="font-display text-sm font-semibold tracking-wider text-jarvis-blue flex items-center gap-2">
                <Upload size={16} />
                Data Import
              </h2>
              <button
                onClick={handleClose}
                className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-500 hover:text-jarvis-blue hover:bg-white/[0.03] transition-all"
                aria-label="Close data import"
              >
                <X size={16} />
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-4 space-y-6">
              <TextImportSection />
              <div className="h-px bg-jarvis-blue/10" />
              <FileUploadSection />
              <div className="h-px bg-jarvis-blue/10" />
              <UrlImportSection />
              <div className="h-px bg-jarvis-blue/10" />
              <IMessageSection />
              <div className="h-px bg-jarvis-blue/10" />
              <GmailSection />
              <div className="h-px bg-jarvis-blue/10" />
              <FacebookSection />
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
