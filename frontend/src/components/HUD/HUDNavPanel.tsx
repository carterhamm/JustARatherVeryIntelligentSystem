import { useState, useCallback } from 'react';
import { Plus, MessageSquare, Trash2, ChevronLeft, ChevronRight, Brain, Upload } from 'lucide-react';
import { useChatStore, Conversation } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import { useChat } from '@/hooks/useChat';
import { api } from '@/services/api';
import clsx from 'clsx';

function formatTimestamp(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return date.toLocaleDateString([], { weekday: 'short' });
  return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

export default function HUDNavPanel() {
  const { sidebarOpen, toggleSidebar } = useUIStore();
  const { conversations, currentConversation } = useChatStore();
  const { createConversation, loadConversation } = useChat();

  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  const handleNewConversation = useCallback(async () => {
    if (isCreating) return;
    setIsCreating(true);
    try {
      await createConversation();
    } finally {
      setIsCreating(false);
    }
  }, [createConversation, isCreating]);

  const handleSelectConversation = useCallback(
    (conv: Conversation) => {
      if (conv.id === currentConversation?.id) return;
      loadConversation(conv.id);
    },
    [currentConversation, loadConversation],
  );

  const handleDeleteConversation = useCallback(
    async (e: React.MouseEvent, convId: string) => {
      e.stopPropagation();
      if (deletingId === convId) {
        try {
          await api.delete(`/conversations/${convId}`);
          const { setConversations, setCurrentConversation, clearMessages } = useChatStore.getState();
          const updated = conversations.filter((c) => c.id !== convId);
          setConversations(updated);
          if (currentConversation?.id === convId) {
            setCurrentConversation(null);
            clearMessages();
          }
        } catch { /* ignore */ }
        setDeletingId(null);
      } else {
        setDeletingId(convId);
        setTimeout(() => setDeletingId(null), 3000);
      }
    },
    [deletingId, conversations, currentConversation],
  );

  // Collapsed: icon strip
  if (!sidebarOpen) {
    return (
      <div className="flex flex-col items-center py-2 w-12 border-r border-jarvis-blue/10 bg-hud-panel backdrop-blur-hud flex-shrink-0 hud-boot-2">
        <button onClick={toggleSidebar} className="w-8 h-8 flex items-center justify-center text-gray-500 hover:text-jarvis-blue transition-colors mb-2">
          <ChevronRight size={14} />
        </button>
        <button onClick={handleNewConversation} className="w-8 h-8 flex items-center justify-center text-jarvis-blue/60 hover:text-jarvis-blue transition-colors mb-1">
          <Plus size={14} />
        </button>
        <div className="flex-1 overflow-y-auto w-full flex flex-col items-center gap-0.5 py-1">
          {conversations.slice(0, 20).map((conv) => (
            <button
              key={conv.id}
              onClick={() => handleSelectConversation(conv)}
              className={clsx('w-7 h-7 rounded flex items-center justify-center transition-all', {
                'bg-jarvis-blue/15 text-jarvis-blue': currentConversation?.id === conv.id,
                'text-gray-600 hover:text-gray-400 hover:bg-white/[0.03]': currentConversation?.id !== conv.id,
              })}
              title={conv.title || 'Conversation'}
            >
              <MessageSquare size={11} />
            </button>
          ))}
        </div>
        <div className="flex flex-col items-center gap-1 mb-1">
          <button onClick={() => window.dispatchEvent(new CustomEvent('jarvis-knowledge-toggle'))}
            className="w-8 h-8 flex items-center justify-center text-gray-600 hover:text-jarvis-blue transition-colors" title="Knowledge">
            <Brain size={13} />
          </button>
          <button onClick={() => window.dispatchEvent(new CustomEvent('jarvis-import-toggle'))}
            className="w-8 h-8 flex items-center justify-center text-gray-600 hover:text-jarvis-blue transition-colors" title="Import">
            <Upload size={13} />
          </button>
        </div>
      </div>
    );
  }

  // Expanded
  return (
    <div className="flex flex-col w-64 border-r border-jarvis-blue/10 bg-hud-panel backdrop-blur-hud flex-shrink-0 hud-boot-2">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-jarvis-blue/8">
        <div className="flex items-center gap-2">
          <span className="hud-label text-[9px]">SESSIONS</span>
          <span className="text-[8px] font-mono text-gray-600">{conversations.length}</span>
        </div>
        <button onClick={toggleSidebar} className="text-gray-500 hover:text-jarvis-blue transition-colors">
          <ChevronLeft size={14} />
        </button>
      </div>

      {/* New conversation */}
      <div className="px-2 py-2">
        <button
          onClick={handleNewConversation}
          disabled={isCreating}
          className="w-full py-2 px-3 text-xs font-medium flex items-center justify-center gap-1.5 tracking-wider text-jarvis-blue border border-jarvis-blue/20 bg-jarvis-blue/5 hover:bg-jarvis-blue/10 transition-all"
          style={{ clipPath: 'polygon(0 4px, 4px 0, calc(100% - 4px) 0, 100% 4px, 100% calc(100% - 4px), calc(100% - 4px) 100%, 4px 100%, 0 calc(100% - 4px))' }}
        >
          <Plus size={12} />
          NEW SESSION
        </button>
      </div>

      {/* Conversation list */}
      <div className="flex-1 overflow-y-auto px-1.5 pb-2">
        {conversations.length === 0 ? (
          <div className="text-center py-6 px-3">
            <MessageSquare size={20} className="mx-auto text-gray-700 mb-1.5" />
            <p className="text-[10px] text-gray-600">No sessions</p>
          </div>
        ) : (
          <div className="space-y-0.5">
            {conversations.map((conv) => (
              <button
                key={conv.id}
                onClick={() => handleSelectConversation(conv)}
                className={clsx(
                  'w-full text-left px-2.5 py-2 group transition-all relative',
                  {
                    'bg-jarvis-blue/8 border-l-2 border-jarvis-blue': currentConversation?.id === conv.id,
                    'hover:bg-white/[0.02] border-l-2 border-transparent': currentConversation?.id !== conv.id,
                  },
                )}
              >
                <div className="flex items-start gap-2 min-w-0">
                  <MessageSquare
                    size={11}
                    className={clsx('mt-0.5 flex-shrink-0', {
                      'text-jarvis-blue': currentConversation?.id === conv.id,
                      'text-gray-700': currentConversation?.id !== conv.id,
                    })}
                  />
                  <div className="flex-1 min-w-0">
                    <p className={clsx('text-xs truncate', {
                      'text-jarvis-blue': currentConversation?.id === conv.id,
                      'text-gray-400': currentConversation?.id !== conv.id,
                    })}>
                      {conv.title || 'New Session'}
                    </p>
                    <p className="text-[9px] text-gray-600 mt-0.5 font-mono">
                      {formatTimestamp(conv.updated_at)}
                      {conv.message_count > 0 && ` / ${conv.message_count}`}
                    </p>
                  </div>
                  <button
                    onClick={(e) => handleDeleteConversation(e, conv.id)}
                    className={clsx('flex-shrink-0 p-0.5 transition-all', {
                      'opacity-0 group-hover:opacity-100 text-gray-700 hover:text-hud-red': deletingId !== conv.id,
                      'opacity-100 text-hud-red': deletingId === conv.id,
                    })}
                  >
                    <Trash2 size={11} />
                  </button>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Bottom actions */}
      <div className="px-2 pb-2 space-y-1 border-t border-jarvis-blue/8 pt-2">
        <button
          onClick={() => window.dispatchEvent(new CustomEvent('jarvis-knowledge-toggle'))}
          className="w-full py-1.5 px-3 text-[10px] font-medium flex items-center gap-1.5 text-gray-500 hover:text-jarvis-blue transition-colors"
        >
          <Brain size={12} />
          KNOWLEDGE
        </button>
        <button
          onClick={() => window.dispatchEvent(new CustomEvent('jarvis-import-toggle'))}
          className="w-full py-1.5 px-3 text-[10px] font-medium flex items-center gap-1.5 text-gray-500 hover:text-jarvis-blue transition-colors"
        >
          <Upload size={12} />
          IMPORT
        </button>
      </div>
    </div>
  );
}
