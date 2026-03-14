import { useState, useEffect, useCallback } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Plus, MessageSquare, Trash2, X } from 'lucide-react';
import { useChatStore, type Conversation, type Message } from '@/stores/chatStore';
import { api } from '@/services/api';
import clsx from 'clsx';

function formatTimestamp(dateStr: string): string {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return '';
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return date.toLocaleDateString([], { weekday: 'short' });
  return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

export default function SessionsPanel() {
  const [open, setOpen] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const {
    conversations,
    currentConversation,
    addConversation,
    setCurrentConversation,
    setConversations,
    setMessages,
    clearMessages,
  } = useChatStore();

  // Listen for toggle event
  useEffect(() => {
    const handler = () => setOpen((prev) => !prev);
    window.addEventListener('jarvis-sessions-toggle', handler);
    return () => window.removeEventListener('jarvis-sessions-toggle', handler);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const handleNewConversation = useCallback(async () => {
    if (isCreating) return;
    setIsCreating(true);
    try {
      const conversation = await api.post<Conversation>('/conversations', {
        title: 'New Conversation',
      });
      addConversation(conversation);
      setCurrentConversation(conversation);
      clearMessages();
    } catch {
      /* ignore */
    }
    setIsCreating(false);
  }, [isCreating, addConversation, setCurrentConversation, clearMessages]);

  const handleSelect = useCallback(
    async (conv: Conversation) => {
      if (conv.id === currentConversation?.id) return;
      try {
        const [conversation, messagesData] = await Promise.all([
          api.get<Conversation>(`/conversations/${conv.id}`),
          api.get<Message[]>(`/conversations/${conv.id}/messages`),
        ]);
        setCurrentConversation(conversation);
        setMessages(messagesData);
      } catch {
        /* ignore */
      }
    },
    [currentConversation, setCurrentConversation, setMessages],
  );

  const handleDelete = useCallback(
    async (e: React.MouseEvent, convId: string) => {
      e.stopPropagation();
      if (deletingId === convId) {
        try {
          await api.delete(`/conversations/${convId}`);
          const updated = conversations.filter((c) => c.id !== convId);
          setConversations(updated);
          if (currentConversation?.id === convId) {
            setCurrentConversation(null);
            clearMessages();
          }
        } catch {
          /* ignore */
        }
        setDeletingId(null);
      } else {
        setDeletingId(convId);
        setTimeout(() => setDeletingId(null), 3000);
      }
    },
    [deletingId, conversations, currentConversation, setConversations, setCurrentConversation, clearMessages],
  );

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-40 panel-backdrop"
            onClick={() => setOpen(false)}
          />

          {/* Panel */}
          <motion.div
            initial={{ opacity: 0, x: -40, scale: 0.97 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: -40, scale: 0.97 }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
            className="fixed left-5 top-20 bottom-24 z-50 w-80 glass-heavy hud-clip flex flex-col overflow-hidden"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.05]">
              <div className="flex items-center gap-2">
                <span className="hud-label text-[10px]">SESSIONS</span>
                <span className="text-[9px] font-mono text-gray-600">
                  {conversations.length}
                </span>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="glass-circle w-8 h-8 flex items-center justify-center"
              >
                <X size={14} className="text-gray-400" />
              </button>
            </div>

            {/* New conversation */}
            <div className="px-4 py-3">
              <button
                onClick={handleNewConversation}
                disabled={isCreating}
                className="jarvis-button w-full py-2.5 px-4 text-xs font-semibold flex items-center justify-center gap-2 tracking-wider uppercase"
              >
                <Plus size={14} />
                New Session
              </button>
            </div>

            {/* Conversation list */}
            <div className="flex-1 overflow-y-auto px-3 pb-3">
              {conversations.length === 0 ? (
                <div className="text-center py-10 px-4">
                  <MessageSquare size={24} className="mx-auto text-gray-700 mb-2" />
                  <p className="text-[11px] text-gray-600">No sessions yet</p>
                </div>
              ) : (
                <div className="space-y-1.5">
                  {conversations.map((conv) => (
                    <button
                      key={conv.id}
                      onClick={() => handleSelect(conv)}
                      className={clsx(
                        'w-full text-left px-4 py-3 hud-clip-sm group transition-all relative',
                        {
                          'glass-cyan': currentConversation?.id === conv.id,
                          'hover:bg-white/[0.03]': currentConversation?.id !== conv.id,
                        },
                      )}
                    >
                      <div className="flex items-start gap-3 min-w-0">
                        <MessageSquare
                          size={13}
                          className={clsx('mt-0.5 flex-shrink-0', {
                            'text-jarvis-blue': currentConversation?.id === conv.id,
                            'text-gray-700': currentConversation?.id !== conv.id,
                          })}
                        />
                        <div className="flex-1 min-w-0">
                          <p
                            className={clsx('text-sm truncate', {
                              'text-jarvis-blue': currentConversation?.id === conv.id,
                              'text-gray-300': currentConversation?.id !== conv.id,
                            })}
                          >
                            {conv.title || 'New Session'}
                          </p>
                          <p className="text-[9px] text-gray-600 mt-0.5 font-mono">
                            {formatTimestamp(conv.updated_at)}
                            {conv.message_count > 0 && ` · ${conv.message_count} msgs`}
                          </p>
                        </div>
                        <button
                          onClick={(e) => handleDelete(e, conv.id)}
                          className={clsx(
                            'flex-shrink-0 p-1 hud-clip-sm transition-all',
                            {
                              'opacity-0 group-hover:opacity-100 text-gray-700 hover:text-hud-red hover:bg-hud-red/10':
                                deletingId !== conv.id,
                              'opacity-100 text-hud-red bg-hud-red/10': deletingId === conv.id,
                            },
                          )}
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
