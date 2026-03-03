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
      <div className="w-6 h-6 flex items-center justify-center" style={{
        clipPath: 'polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%)',
        background: 'linear-gradient(135deg, rgba(0, 212, 255, 0.3), rgba(0, 128, 255, 0.2))',
      }}>
        <span className="text-[8px] font-bold text-jarvis-blue animate-pulse">J</span>
      </div>
      <div className="flex items-center gap-1.5">
        <div className="typing-dot w-1.5 h-1.5 rounded-full bg-jarvis-cyan" />
        <div className="typing-dot w-1.5 h-1.5 rounded-full bg-jarvis-cyan" />
        <div className="typing-dot w-1.5 h-1.5 rounded-full bg-jarvis-cyan" />
      </div>
      <span className="hud-label text-[9px]">PROCESSING QUERY</span>
    </div>
  );
}

function ArcReactorEmptyState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center px-4">
      <div className="text-center">
        {/* Arc Reactor */}
        <div className="relative inline-block mb-8">
          <div className="arc-reactor">
            {/* Concentric rings */}
            <div className="arc-ring arc-ring-1" />
            <div className="arc-ring arc-ring-2" />
            <div className="arc-ring arc-ring-3" />
            <div className="arc-ring arc-ring-4" />
            {/* Spinning segments */}
            <div className="arc-segment arc-segment-1" />
            <div className="arc-segment arc-segment-2" />
            <div className="arc-segment arc-segment-3" />
            {/* Core glow */}
            <div className="arc-reactor-core" />
          </div>
        </div>

        <h2 className="text-base font-display font-bold tracking-[0.25em] text-jarvis-blue glow-text mb-2">
          SYSTEMS ONLINE
        </h2>
        <p className="text-[11px] text-gray-500 leading-relaxed font-mono tracking-wide">
          All subsystems operational. Awaiting directives.
        </p>

        <div className="mt-8 flex items-center justify-center gap-6">
          <div className="flex flex-col items-center gap-1">
            <div className="hud-status-dot online" style={{ width: 5, height: 5 }} />
            <span className="text-[8px] font-mono text-gray-600 tracking-wider">CORE</span>
          </div>
          <div className="h-3 w-px bg-jarvis-blue/10" />
          <div className="flex flex-col items-center gap-1">
            <div className="hud-status-dot online" style={{ width: 5, height: 5 }} />
            <span className="text-[8px] font-mono text-gray-600 tracking-wider">UPLINK</span>
          </div>
          <div className="h-3 w-px bg-jarvis-blue/10" />
          <div className="flex flex-col items-center gap-1">
            <div className="hud-status-dot online" style={{ width: 5, height: 5 }} />
            <span className="text-[8px] font-mono text-gray-600 tracking-wider">VOICE</span>
          </div>
        </div>

        <div className="mt-6 hud-divider max-w-xs mx-auto">
          <div className="hud-divider-dot" />
        </div>

        <p className="mt-4 text-[9px] text-gray-600 font-mono">
          TYPE OR SPEAK TO BEGIN
        </p>
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
    <div className="flex-1 flex flex-col h-full min-w-0 hud-boot-2 relative">
      {/* Messages area */}
      {hasMessages || currentConversation ? (
        <div className="flex-1 overflow-y-auto px-4 sm:px-8 py-4">
          {!hasMessages && currentConversation && <ArcReactorEmptyState />}
          {displayMessages.map((item) => {
            if ('type' in item && item.type === 'error_stack') {
              const count = item.errors.length;
              const latestError = item.errors[item.errors.length - 1];
              return (
                <div key={latestError.id} className="flex justify-center my-2">
                  <div className="px-4 py-1.5 border border-red-500/20 bg-red-500/5 max-w-lg hud-glitch"
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
        <ArcReactorEmptyState />
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
