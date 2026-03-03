import { useEffect, useRef, useCallback } from 'react';
import { useChatStore, type Message } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import { useChat } from '@/hooks/useChat';
import { useVoice } from '@/hooks/useVoice';
import MessageBubble from '@/components/Chat/MessageBubble';
import MessageInput from '@/components/Chat/MessageInput';

function ThinkingIndicator() {
  return (
    <div className="flex items-center gap-3 px-4 py-3">
      <div className="w-5 h-5 flex items-center justify-center" style={{
        clipPath: 'polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%)',
        background: 'linear-gradient(135deg, rgba(0, 212, 255, 0.3), rgba(0, 128, 255, 0.2))',
      }}>
        <span className="text-[8px] font-bold text-jarvis-blue">J</span>
      </div>
      <div className="flex items-center gap-1.5">
        <div className="typing-dot w-1.5 h-1.5 rounded-full bg-jarvis-cyan" />
        <div className="typing-dot w-1.5 h-1.5 rounded-full bg-jarvis-cyan" />
        <div className="typing-dot w-1.5 h-1.5 rounded-full bg-jarvis-cyan" />
      </div>
      <span className="hud-label text-[9px]">PROCESSING</span>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center px-4">
      <div className="text-center max-w-sm">
        <div className="relative inline-block mb-4">
          <div className="w-16 h-16 flex items-center justify-center animate-pulse-glow" style={{
            clipPath: 'polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%)',
            background: 'linear-gradient(135deg, rgba(0, 212, 255, 0.1), rgba(0, 128, 255, 0.05))',
            border: '1px solid rgba(0, 212, 255, 0.2)',
          }}>
            <span className="text-2xl font-display font-bold text-jarvis-blue glow-text">J</span>
          </div>
        </div>

        <h2 className="text-lg font-display font-bold tracking-[0.15em] text-jarvis-blue glow-text mb-1">
          READY
        </h2>
        <p className="text-xs text-gray-500 leading-relaxed font-mono">
          Awaiting input. Type below or use voice.
        </p>

        <div className="mt-6 hud-divider">
          <div className="hud-divider-dot" />
        </div>
      </div>
    </div>
  );
}

export default function ChatArea() {
  const { messages, currentConversation, sendMessage, isStreaming } = useChat();
  const { isThinking } = useUIStore();
  const { isRecording, isTranscribing, startRecording, stopRecording, transcribeAudio } = useVoice();

  const messagesEndRef = useRef<HTMLDivElement>(null);

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

  const hasMessages = messages.length > 0;

  // Group consecutive error messages into a single collapsed block
  const displayMessages = messages.reduce<(Message | { type: 'error_stack'; errors: Message[] })[]>((acc, msg) => {
    if (msg.role === 'system' && msg.id.startsWith('error-')) {
      const last = acc[acc.length - 1];
      if (last && 'type' in last && last.type === 'error_stack') {
        last.errors.push(msg);
      } else {
        acc.push({ type: 'error_stack', errors: [msg] });
      }
    } else {
      acc.push(msg);
    }
    return acc;
  }, []);

  return (
    <div className="flex-1 flex flex-col h-full min-w-0 hud-boot-2">
      {/* Messages area — transparent background */}
      {hasMessages || currentConversation ? (
        <div className="flex-1 overflow-y-auto px-4 sm:px-8 py-4">
          {!hasMessages && currentConversation && <EmptyState />}
          {displayMessages.map((item) => {
            if ('type' in item && item.type === 'error_stack') {
              const count = item.errors.length;
              const latestError = item.errors[item.errors.length - 1];
              return (
                <div key={latestError.id} className="flex justify-center my-2">
                  <div className="px-4 py-1.5 border border-red-500/20 bg-red-500/5 max-w-lg"
                    style={{ clipPath: 'polygon(0 4px, 4px 0, calc(100% - 4px) 0, 100% 4px, 100% calc(100% - 4px), calc(100% - 4px) 100%, 4px 100%, 0 calc(100% - 4px))' }}>
                    <p className="text-[10px] text-center text-red-400 font-mono">
                      {count > 1 ? `${latestError.content} (+${count - 1} more)` : latestError.content}
                    </p>
                  </div>
                </div>
              );
            }
            return <MessageBubble key={(item as Message).id} message={item as Message} />;
          })}
          {isThinking && !isStreaming && <ThinkingIndicator />}
          <div ref={messagesEndRef} />
        </div>
      ) : (
        <EmptyState />
      )}

      {/* Input bar */}
      <div className="flex-shrink-0 px-4 sm:px-8 pb-3 pt-1">
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
