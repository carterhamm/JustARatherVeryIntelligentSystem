import { useEffect, useRef, useCallback } from 'react';
import { useChatStore, type Message } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import { useChat } from '@/hooks/useChat';
import { useVoice } from '@/hooks/useVoice';
import HoloMessage from './HoloMessage';
import GlassInput from './GlassInput';

function EmptyState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center px-4 boot-2">
      <div className="text-center">
        {/* Arc Reactor */}
        <div className="relative inline-block mb-6">
          <div className="arc-reactor">
            <div className="arc-ring arc-ring-1" />
            <div className="arc-ring arc-ring-2" />
            <div className="arc-ring arc-ring-3" />
            <div className="arc-ring arc-ring-4" />
            <div className="arc-segment arc-segment-1" />
            <div className="arc-segment arc-segment-2" />
            <div className="arc-segment arc-segment-3" />
            <div className="arc-reactor-core" />
          </div>
        </div>

        <h2 className="text-sm font-display font-bold tracking-[0.25em] text-jarvis-blue glow-text mb-2">
          SYSTEMS ONLINE
        </h2>
        <p className="text-[11px] text-gray-500 leading-relaxed font-mono tracking-wide mb-6">
          All subsystems operational. Awaiting directives.
        </p>

        <div className="flex items-center justify-center gap-5">
          <div className="flex flex-col items-center gap-1">
            <div className="status-dot online" style={{ width: 5, height: 5 }} />
            <span className="text-[8px] font-mono text-gray-600 tracking-wider">CORE</span>
          </div>
          <div className="w-px h-4 bg-white/[0.05]" />
          <div className="flex flex-col items-center gap-1">
            <div className="status-dot online" style={{ width: 5, height: 5 }} />
            <span className="text-[8px] font-mono text-gray-600 tracking-wider">UPLINK</span>
          </div>
          <div className="w-px h-4 bg-white/[0.05]" />
          <div className="flex flex-col items-center gap-1">
            <div className="status-dot online" style={{ width: 5, height: 5 }} />
            <span className="text-[8px] font-mono text-gray-600 tracking-wider">VOICE</span>
          </div>
        </div>

        <div className="mt-6 hud-divider max-w-[200px] mx-auto">
          <div className="hud-divider-dot" />
        </div>

        <p className="mt-4 text-[9px] text-gray-600 font-mono tracking-wider">
          TYPE OR SPEAK TO BEGIN
        </p>
      </div>
    </div>
  );
}

export default function FloatingChat() {
  const { messages, currentConversation, sendMessage, isStreaming } = useChat();
  const isThinking = useUIStore((s) => s.isThinking);
  const { isRecording, isTranscribing, startRecording, stopRecording, transcribeAudio } =
    useVoice();

  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

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

  // Group consecutive error messages
  const displayMessages = messages.reduce<
    (Message | { type: 'error_stack'; errors: Message[] })[]
  >((acc, msg) => {
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

  // Derive thinking state from chat data
  const lastMessage = messages[messages.length - 1];
  const awaitingResponse =
    !!lastMessage && lastMessage.role === 'user' && lastMessage.id.startsWith('user-');
  const showThinking = awaitingResponse && !isStreaming;

  return (
    <div className="fixed inset-x-0 top-[72px] bottom-[24px] z-20 flex flex-col items-center pointer-events-none">
      {/* Messages area */}
      {hasMessages || currentConversation || showThinking ? (
        <div className="w-full max-w-3xl flex-1 overflow-y-auto px-5 sm:px-8 py-6 pointer-events-auto chat-scroll-mask">
          {!hasMessages && !showThinking && currentConversation && <EmptyState />}
          {displayMessages.map((item) => {
            if ('type' in item && item.type === 'error_stack') {
              const count = item.errors.length;
              const latestError = item.errors[item.errors.length - 1];
              return (
                <div key={latestError.id} className="flex justify-center my-3">
                  <div className="glass-subtle rounded-xl px-4 py-2 max-w-lg border border-hud-red/10">
                    <p className="text-[10px] text-center text-red-400 font-mono">
                      {count > 1
                        ? `${latestError.content} (+${count - 1} more)`
                        : latestError.content}
                    </p>
                  </div>
                </div>
              );
            }
            return <HoloMessage key={(item as Message).id} message={item as Message} />;
          })}

          {/* Thinking indicator */}
          {showThinking && (
            <HoloMessage
              message={{
                id: 'thinking-placeholder',
                role: 'assistant',
                content: '',
                timestamp: new Date().toISOString(),
                isStreaming: true,
              }}
            />
          )}
          <div ref={messagesEndRef} />
        </div>
      ) : (
        <EmptyState />
      )}

      {/* Input bar */}
      <div className="w-full max-w-3xl px-5 sm:px-8 pt-2 pb-2 pointer-events-auto boot-3">
        <GlassInput
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
