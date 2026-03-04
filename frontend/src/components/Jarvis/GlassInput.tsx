import { useState, useRef, useCallback, useEffect } from 'react';
import { Send, Mic, MicOff, Loader2 } from 'lucide-react';
import clsx from 'clsx';

interface GlassInputProps {
  onSend: (content: string) => void;
  onVoiceToggle?: () => void;
  isLoading?: boolean;
  isRecording?: boolean;
  disabled?: boolean;
}

export default function GlassInput({
  onSend,
  onVoiceToggle,
  isLoading = false,
  isRecording = false,
  disabled = false,
}: GlassInputProps) {
  const [content, setContent] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const adjustHeight = useCallback(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      const maxHeight = 5 * 24;
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

  const hasContent = content.trim().length > 0;

  return (
    <div className="glass-capsule px-2.5 py-2 flex items-end gap-2 transition-all duration-300 hover:shadow-glass-glow">
      {/* Voice toggle */}
      {onVoiceToggle && (
        <button
          onClick={onVoiceToggle}
          disabled={disabled || isLoading}
          className={clsx('glass-circle flex-shrink-0 w-10 h-10 flex items-center justify-center', {
            'active !bg-hud-red/15 !border-hud-red/30': isRecording,
          })}
        >
          {isRecording ? (
            <MicOff size={16} className="text-hud-red" />
          ) : (
            <Mic size={16} className="text-jarvis-blue/60" />
          )}
        </button>
      )}

      {/* Text input */}
      <div className="flex-1 relative min-w-0">
        <textarea
          ref={textareaRef}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Message J.A.R.V.I.S. ..."
          disabled={disabled || isLoading}
          rows={1}
          className="w-full resize-none bg-transparent border-none text-sm text-gray-200 placeholder:text-gray-600 disabled:opacity-50 focus:outline-none px-3 py-2.5 font-sans leading-relaxed"
        />
      </div>

      {/* Send button */}
      <button
        onClick={handleSend}
        disabled={!hasContent || isLoading || disabled}
        className={clsx('glass-circle flex-shrink-0 w-10 h-10 flex items-center justify-center transition-all', {
          'opacity-30 cursor-not-allowed': !hasContent || isLoading || disabled,
          '!bg-jarvis-gold/12 !border-jarvis-gold/25': hasContent && !isLoading && !disabled,
        })}
      >
        {isLoading ? (
          <Loader2 size={16} className="animate-spin text-jarvis-blue/60" />
        ) : (
          <Send
            size={16}
            className={clsx({
              'text-jarvis-gold': hasContent && !disabled,
              'text-gray-600': !hasContent || disabled,
            })}
          />
        )}
      </button>
    </div>
  );
}
