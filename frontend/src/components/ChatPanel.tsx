import { useEffect, useRef, useCallback, useState } from 'react';
import { Settings, Wifi, WifiOff } from 'lucide-react';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useChat } from '@/hooks/useChat';
import { useVoice } from '@/hooks/useVoice';
import MessageBubble from '@/components/Chat/MessageBubble';
import MessageInput from '@/components/Chat/MessageInput';
import clsx from 'clsx';

const providerLabels: Record<string, { label: string; color: string }> = {
  claude: { label: 'Claude', color: 'text-orange-400 bg-orange-400/10 border-orange-400/20' },
  gemini: { label: 'Gemini', color: 'text-blue-400 bg-blue-400/10 border-blue-400/20' },
  stark_protocol: { label: 'Stark', color: 'text-cyan-400 bg-cyan-400/10 border-cyan-400/20' },
};

function ThinkingIndicator() {
  return (
    <div className="flex items-center gap-3 px-4 py-3">
      <div className="w-5 h-5 rounded-full bg-gradient-to-br from-jarvis-blue to-jarvis-cyan flex items-center justify-center">
        <span className="text-[10px] font-bold text-jarvis-darker">J</span>
      </div>
      <div className="flex items-center gap-1.5">
        <div className="typing-dot w-1.5 h-1.5 rounded-full bg-jarvis-cyan" />
        <div className="typing-dot w-1.5 h-1.5 rounded-full bg-jarvis-cyan" />
        <div className="typing-dot w-1.5 h-1.5 rounded-full bg-jarvis-cyan" />
      </div>
      <span className="text-xs text-jarvis-blue/50">Processing...</span>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center px-4">
      <div className="text-center max-w-sm">
        {/* Animated JARVIS identity */}
        <div className="relative inline-block mb-6">
          <div className="w-20 h-20 rounded-full bg-gradient-to-br from-jarvis-blue/10 to-jarvis-cyan/5 border border-jarvis-blue/20 flex items-center justify-center animate-pulse-glow">
            <span className="text-3xl font-display font-bold text-jarvis-blue glow-text">J</span>
          </div>
        </div>

        <h2 className="text-xl font-display font-bold tracking-wider text-jarvis-blue glow-text mb-2">
          Hello, I am J.A.R.V.I.S.
        </h2>
        <p className="text-sm text-gray-400 leading-relaxed mb-1">
          Just A Rather Very Intelligent System
        </p>
        <p className="text-xs text-gray-500 leading-relaxed mt-4">
          How can I assist you today? You can type a message below or use the microphone for voice input.
        </p>

        {/* Subtle HUD decorations */}
        <div className="mt-8 flex items-center justify-center gap-3">
          <div className="h-px w-12 bg-gradient-to-r from-transparent to-jarvis-blue/30" />
          <div className="w-1.5 h-1.5 rounded-full bg-jarvis-blue/30" />
          <span className="text-[10px] text-jarvis-blue/30 font-display tracking-[0.3em] uppercase">
            Ready
          </span>
          <div className="w-1.5 h-1.5 rounded-full bg-jarvis-blue/30" />
          <div className="h-px w-12 bg-gradient-to-l from-transparent to-jarvis-blue/30" />
        </div>
      </div>
    </div>
  );
}

function RecordingIndicator() {
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-red-500/10 border border-red-500/30">
      <div className="w-2 h-2 rounded-full bg-red-500 recording-pulse" />
      <span className="text-xs text-red-400 font-medium">Recording...</span>
    </div>
  );
}

export default function ChatPanel() {
  const { messages, currentConversation, sendMessage, isStreaming } = useChat();
  const { isThinking, wsConnected } = useUIStore();
  const { isRecording, isTranscribing, startRecording, stopRecording, transcribeAudio } = useVoice();

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);

  // Store settingsOpen in a way SettingsPanel can access it
  // We use a custom event to communicate with SettingsPanel
  const toggleSettings = useCallback(() => {
    setSettingsOpen((prev) => {
      const next = !prev;
      window.dispatchEvent(new CustomEvent('jarvis-settings-toggle', { detail: { open: next } }));
      return next;
    });
  }, []);

  // Listen for settings close events from SettingsPanel
  useEffect(() => {
    const handler = (e: Event) => {
      const customEvent = e as CustomEvent<{ open: boolean }>;
      setSettingsOpen(customEvent.detail.open);
    };
    window.addEventListener('jarvis-settings-toggle', handler);
    return () => window.removeEventListener('jarvis-settings-toggle', handler);
  }, []);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isThinking]);

  const handleVoiceToggle = useCallback(async () => {
    if (isRecording) {
      const audioBlob = await stopRecording();
      if (audioBlob) {
        const text = await transcribeAudio(audioBlob);
        if (text && text.trim()) {
          sendMessage(text);
        }
      }
    } else {
      startRecording();
    }
  }, [isRecording, stopRecording, startRecording, transcribeAudio, sendMessage]);

  const { modelPreference } = useSettingsStore();
  const providerInfo = providerLabels[modelPreference] || providerLabels.claude;

  const conversationTitle = currentConversation?.title || 'New Conversation';
  const hasMessages = messages.length > 0;

  return (
    <div className="flex-1 flex flex-col h-full min-w-0">
      {/* Header */}
      <header className="flex items-center justify-between px-4 sm:px-6 py-3 glass-panel border-b border-jarvis-blue/10 flex-shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <h1 className="text-sm font-display font-semibold tracking-wider text-gray-200 truncate">
            {conversationTitle}
          </h1>
          {/* Model indicator badge */}
          <span className={clsx(
            'px-2 py-0.5 rounded text-[10px] font-medium border',
            providerInfo.color,
          )}>
            {providerInfo.label}
          </span>
          {isRecording && <RecordingIndicator />}
          {isTranscribing && (
            <span className="text-xs text-jarvis-blue/50 animate-pulse">Transcribing...</span>
          )}
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {/* Connection status */}
          <div
            className={clsx('flex items-center gap-1.5 px-2 py-1 hud-clip-sm text-[11px]', {
              'text-green-400': wsConnected,
              'text-gray-500': !wsConnected,
            })}
            title={wsConnected ? 'WebSocket connected' : 'WebSocket disconnected'}
          >
            {wsConnected ? <Wifi size={13} /> : <WifiOff size={13} />}
          </div>

          {/* Settings button */}
          <button
            onClick={toggleSettings}
            className={clsx(
              'w-8 h-8 hud-clip-sm flex items-center justify-center transition-all',
              {
                'text-jarvis-blue bg-jarvis-blue/10': settingsOpen,
                'text-gray-500 hover:text-jarvis-blue hover:bg-white/[0.03]': !settingsOpen,
              }
            )}
            aria-label="Toggle settings"
          >
            <Settings size={16} />
          </button>
        </div>
      </header>

      {/* Messages Area */}
      {hasMessages || currentConversation ? (
        <div
          ref={messagesContainerRef}
          className="flex-1 overflow-y-auto px-4 sm:px-6 py-4"
        >
          {!hasMessages && currentConversation && <EmptyState />}

          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}

          {isThinking && !isStreaming && <ThinkingIndicator />}

          <div ref={messagesEndRef} />
        </div>
      ) : (
        <EmptyState />
      )}

      {/* Input Area */}
      <div className="flex-shrink-0 px-4 sm:px-6 pb-4 pt-2">
        <MessageInput
          onSend={sendMessage}
          onVoiceToggle={handleVoiceToggle}
          isLoading={isStreaming || isThinking}
          isRecording={isRecording}
          disabled={isTranscribing}
        />
      </div>
    </div>
  );
}
