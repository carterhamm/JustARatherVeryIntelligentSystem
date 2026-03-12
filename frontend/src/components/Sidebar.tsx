import { useState, useCallback } from 'react';
import { Plus, MessageSquare, Trash2, PanelLeftClose, PanelLeftOpen, Brain, Upload } from 'lucide-react';
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

  if (diffDays === 0) {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  if (diffDays === 1) {
    return 'Yesterday';
  }
  if (diffDays < 7) {
    return date.toLocaleDateString([], { weekday: 'short' });
  }
  return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

export default function Sidebar() {
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
    [currentConversation, loadConversation]
  );

  const handleDeleteConversation = useCallback(
    async (e: React.MouseEvent, convId: string) => {
      e.stopPropagation();
      if (deletingId === convId) {
        // Confirmed -- perform delete
        try {
          await api.delete(`/chat/conversations/${convId}`);
          const { setConversations, setCurrentConversation, clearMessages } = useChatStore.getState();
          const updated = conversations.filter((c) => c.id !== convId);
          setConversations(updated);
          if (currentConversation?.id === convId) {
            setCurrentConversation(null);
            clearMessages();
          }
        } catch {
          // silently fail
        }
        setDeletingId(null);
      } else {
        setDeletingId(convId);
        // Auto-clear confirmation after 3 seconds
        setTimeout(() => setDeletingId(null), 3000);
      }
    },
    [deletingId, conversations, currentConversation]
  );

  return (
    <>
      {/* Toggle button when sidebar is collapsed */}
      {!sidebarOpen && (
        <button
          onClick={toggleSidebar}
          className="fixed top-4 left-4 z-30 jarvis-button w-10 h-10 flex items-center justify-center"
          aria-label="Open sidebar"
        >
          <PanelLeftOpen size={18} />
        </button>
      )}

      {/* Sidebar panel */}
      <div
        className={clsx(
          'flex flex-col h-full glass-panel border-r border-jarvis-blue/15 transition-all duration-300 flex-shrink-0',
          {
            'w-72': sidebarOpen,
            'w-0 overflow-hidden opacity-0 pointer-events-none': !sidebarOpen,
          }
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-jarvis-blue/10">
          <div className="flex items-center gap-2 min-w-0">
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-jarvis-blue/20 to-jarvis-cyan/10 border border-jarvis-blue/30 flex items-center justify-center flex-shrink-0">
              <span className="text-xs font-display font-bold text-jarvis-blue">J</span>
            </div>
            <h2 className="font-display text-sm font-bold tracking-wider text-jarvis-blue glow-text truncate">
              J.A.R.V.I.S.
            </h2>
          </div>
          <button
            onClick={toggleSidebar}
            className="text-gray-500 hover:text-jarvis-blue transition-colors flex-shrink-0"
            aria-label="Close sidebar"
          >
            <PanelLeftClose size={18} />
          </button>
        </div>

        {/* New Conversation Button */}
        <div className="p-3">
          <button
            onClick={handleNewConversation}
            disabled={isCreating}
            className="w-full jarvis-button py-2.5 px-4 text-sm font-medium flex items-center justify-center gap-2 tracking-wide"
          >
            <Plus size={16} />
            New Conversation
          </button>
        </div>

        {/* Conversation List */}
        <div className="flex-1 overflow-y-auto px-2 pb-4">
          {conversations.length === 0 ? (
            <div className="text-center py-8 px-4">
              <MessageSquare size={28} className="mx-auto text-gray-600 mb-2" />
              <p className="text-xs text-gray-500">No conversations yet.</p>
              <p className="text-xs text-gray-600 mt-1">Start a new one above.</p>
            </div>
          ) : (
            <div className="space-y-1">
              {conversations.map((conv) => (
                <button
                  key={conv.id}
                  onClick={() => handleSelectConversation(conv)}
                  className={clsx(
                    'w-full text-left hud-clip-sm px-3 py-2.5 group transition-all relative',
                    {
                      'bg-jarvis-blue/10 border border-jarvis-blue/20':
                        currentConversation?.id === conv.id,
                      'hover:bg-white/[0.03] border border-transparent':
                        currentConversation?.id !== conv.id,
                    }
                  )}
                >
                  <div className="flex items-start gap-2.5 min-w-0">
                    <MessageSquare
                      size={14}
                      className={clsx('mt-0.5 flex-shrink-0', {
                        'text-jarvis-blue': currentConversation?.id === conv.id,
                        'text-gray-600': currentConversation?.id !== conv.id,
                      })}
                    />
                    <div className="flex-1 min-w-0">
                      <p
                        className={clsx('text-sm truncate', {
                          'text-jarvis-blue': currentConversation?.id === conv.id,
                          'text-gray-300': currentConversation?.id !== conv.id,
                        })}
                      >
                        {conv.title || 'New Conversation'}
                      </p>
                      <p className="text-[10px] text-gray-600 mt-0.5">
                        {formatTimestamp(conv.updated_at)}
                        {conv.message_count > 0 && ` -- ${conv.message_count} msg${conv.message_count !== 1 ? 's' : ''}`}
                      </p>
                    </div>
                    {/* Delete button */}
                    <button
                      onClick={(e) => handleDeleteConversation(e, conv.id)}
                      className={clsx(
                        'flex-shrink-0 p-1 hud-clip-sm transition-all',
                        {
                          'opacity-0 group-hover:opacity-100 text-gray-600 hover:text-red-400 hover:bg-red-500/10':
                            deletingId !== conv.id,
                          'opacity-100 text-red-400 bg-red-500/10': deletingId === conv.id,
                        }
                      )}
                      aria-label={deletingId === conv.id ? 'Confirm delete' : 'Delete conversation'}
                      title={deletingId === conv.id ? 'Click again to confirm' : 'Delete'}
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                  {deletingId === conv.id && (
                    <p className="text-[10px] text-red-400 mt-1 ml-6">Click again to confirm</p>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Knowledge & Import Buttons */}
        <div className="px-3 pb-2 space-y-1.5">
          <button
            onClick={() => window.dispatchEvent(new CustomEvent('jarvis-knowledge-toggle'))}
            className="w-full jarvis-button py-2 px-4 text-sm font-medium flex items-center gap-2 tracking-wide"
          >
            <Brain size={16} />
            Knowledge
          </button>
          <button
            onClick={() => window.dispatchEvent(new CustomEvent('jarvis-import-toggle'))}
            className="w-full jarvis-button py-2 px-4 text-sm font-medium flex items-center gap-2 tracking-wide"
          >
            <Upload size={16} />
            Import Data
          </button>
        </div>

        {/* Connection Status */}
        <div className="p-3 border-t border-jarvis-blue/10">
          <ConnectionStatus />
        </div>
      </div>
    </>
  );
}

function ConnectionStatus() {
  const wsConnected = useUIStore((s) => s.wsConnected);

  return (
    <div className="flex items-center gap-2">
      <div
        className={clsx('w-2 h-2 rounded-full', {
          'bg-green-400 shadow-[0_0_6px_rgba(74,222,128,0.5)]': wsConnected,
          'bg-gray-600': !wsConnected,
        })}
      />
      <span className="text-[11px] text-gray-500">
        {wsConnected ? 'Connected' : 'Disconnected'}
      </span>
    </div>
  );
}
