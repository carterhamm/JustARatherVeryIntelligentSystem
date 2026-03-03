import { useState, useRef, useCallback, useEffect } from 'react';
import { Send, Mic, MicOff, Loader2 } from 'lucide-react';
import clsx from 'clsx';

interface MessageInputProps {
  onSend: (content: string) => void;
  onVoiceToggle?: () => void;
  isLoading?: boolean;
  isRecording?: boolean;
  disabled?: boolean;
}

export default function MessageInput({
  onSend,
  onVoiceToggle,
  isLoading = false,
  isRecording = false,
  disabled = false,
}: MessageInputProps) {
  const [content, setContent] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const adjustHeight = useCallback(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      const maxHeight = 6 * 24;
      textarea.style.height = `${Math.min(textarea.scrollHeight, maxHeight)}px`;
    }
  }, []);

  useEffect(() => {
    adjustHeight();
  }, [content, adjustHeight]);

  const handleSend = useCallback(() => {
    const trimmed = content.trim();
    if (trimmed && !isLoading && !disabled) {
      onSend(trimmed);
      setContent('');
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  }, [content, isLoading, disabled, onSend]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  const charCount = content.length;
  const showCharCount = charCount > 500;

  return (
    <div
      className="bg-hud-panel backdrop-blur-hud border border-jarvis-blue/12 p-2.5"
      style={{
        clipPath: 'polygon(0 6px, 6px 0, calc(100% - 6px) 0, 100% 6px, 100% calc(100% - 6px), calc(100% - 6px) 100%, 6px 100%, 0 calc(100% - 6px))',
      }}
    >
      <div className="flex items-end gap-2">
        {/* Voice toggle — hexagonal */}
        {onVoiceToggle && (
          <button
            onClick={onVoiceToggle}
            disabled={disabled || isLoading}
            className={clsx(
              'flex-shrink-0 w-9 h-9 flex items-center justify-center transition-all',
              {
                'text-hud-red': isRecording,
                'text-jarvis-blue/60 hover:text-jarvis-blue': !isRecording,
              },
            )}
            style={{
              clipPath: 'polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%)',
              background: isRecording
                ? 'rgba(255, 58, 58, 0.15)'
                : 'rgba(0, 212, 255, 0.08)',
              border: `1px solid ${isRecording ? 'rgba(255, 58, 58, 0.3)' : 'rgba(0, 212, 255, 0.15)'}`,
            }}
          >
            {isRecording ? <MicOff size={15} /> : <Mic size={15} />}
          </button>
        )}

        {/* Text input */}
        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Message J.A.R.V.I.S. ..."
            disabled={disabled || isLoading}
            rows={1}
            className="w-full resize-none bg-transparent border-none text-sm text-gray-200 placeholder:text-gray-600 disabled:opacity-50 focus:outline-none px-2 py-2 font-sans"
          />
          {showCharCount && (
            <span className="absolute right-2 bottom-0.5 text-[9px] text-gray-600 font-mono">
              {charCount}
            </span>
          )}
        </div>

        {/* Send button */}
        <button
          onClick={handleSend}
          disabled={!content.trim() || isLoading || disabled}
          className={clsx(
            'flex-shrink-0 w-9 h-9 flex items-center justify-center transition-all',
            {
              'opacity-30 cursor-not-allowed': !content.trim() || isLoading || disabled,
              'text-jarvis-gold hover:text-jarvis-gold': content.trim() && !isLoading && !disabled,
              'text-jarvis-blue/40': !content.trim(),
            },
          )}
          style={{
            clipPath: 'polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%)',
            background: content.trim() && !isLoading
              ? 'rgba(240, 165, 0, 0.12)'
              : 'rgba(0, 212, 255, 0.05)',
            border: `1px solid ${content.trim() && !isLoading ? 'rgba(240, 165, 0, 0.25)' : 'rgba(0, 212, 255, 0.1)'}`,
          }}
        >
          {isLoading ? (
            <Loader2 size={15} className="animate-spin" />
          ) : (
            <Send size={15} />
          )}
        </button>
      </div>

      {/* Bottom hints */}
      <div className="flex justify-between items-center mt-1 px-1">
        <span className="text-[9px] text-gray-700 font-mono">
          ENTER send / SHIFT+ENTER newline
        </span>
        {isRecording && (
          <span className="text-[9px] text-hud-red font-mono animate-pulse">REC</span>
        )}
      </div>
    </div>
  );
}
