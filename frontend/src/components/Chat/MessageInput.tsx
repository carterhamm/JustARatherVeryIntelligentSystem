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
      const maxHeight = 6 * 24; // 6 lines
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
    [handleSend]
  );

  const charCount = content.length;
  const showCharCount = charCount > 500;

  return (
    <div className="glass-panel rounded-2xl p-3">
      <div className="flex items-end gap-2">
        {/* Voice toggle button */}
        {onVoiceToggle && (
          <button
            onClick={onVoiceToggle}
            disabled={disabled || isLoading}
            className={clsx(
              'flex-shrink-0 w-10 h-10 rounded-xl flex items-center justify-center transition-all',
              {
                'bg-red-500/20 border border-red-500/50 text-red-400 recording-pulse': isRecording,
                'jarvis-button': !isRecording,
              }
            )}
          >
            {isRecording ? <MicOff size={18} /> : <Mic size={18} />}
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
            className={clsx(
              'w-full resize-none jarvis-input rounded-xl px-4 py-2.5 text-sm',
              'placeholder:text-gray-500 disabled:opacity-50'
            )}
          />
          {showCharCount && (
            <span className="absolute right-3 bottom-1 text-[10px] text-gray-500">
              {charCount}
            </span>
          )}
        </div>

        {/* Send button */}
        <button
          onClick={handleSend}
          disabled={!content.trim() || isLoading || disabled}
          className={clsx(
            'flex-shrink-0 w-10 h-10 rounded-xl flex items-center justify-center transition-all',
            'jarvis-button',
            {
              'opacity-40 cursor-not-allowed': !content.trim() || isLoading || disabled,
            }
          )}
        >
          {isLoading ? (
            <Loader2 size={18} className="animate-spin" />
          ) : (
            <Send size={18} />
          )}
        </button>
      </div>

      {/* Keyboard hint */}
      <div className="flex justify-between items-center mt-1.5 px-1">
        <span className="text-[10px] text-gray-600">
          Press <kbd className="px-1 py-0.5 rounded bg-jarvis-darker text-gray-400 text-[9px]">Enter</kbd> to send,{' '}
          <kbd className="px-1 py-0.5 rounded bg-jarvis-darker text-gray-400 text-[9px]">Shift+Enter</kbd> for new line
        </span>
      </div>
    </div>
  );
}
