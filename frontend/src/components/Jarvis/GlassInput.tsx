import { useState, useRef, useCallback, useEffect } from 'react';
import { Send, Mic, MicOff, Loader2 } from 'lucide-react';
import gsap from 'gsap';
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
  const containerRef = useRef<HTMLDivElement>(null);
  const sendBtnRef = useRef<HTMLButtonElement>(null);

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

  // CMD+K / Ctrl+K to focus input
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        textareaRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // GSAP boot animation
  useEffect(() => {
    if (containerRef.current) {
      gsap.fromTo(
        containerRef.current,
        { opacity: 0, y: 20, scale: 0.95 },
        { opacity: 1, y: 0, scale: 1, duration: 0.5, ease: 'power3.out', delay: 0.6 },
      );
    }
  }, []);

  const handleFocus = () => {
    if (containerRef.current) {
      gsap.to(containerRef.current, {
        boxShadow: '0 0 30px rgba(0, 212, 255, 0.15), 0 8px 32px rgba(0, 0, 0, 0.4)',
        borderColor: 'rgba(0, 212, 255, 0.15)',
        duration: 0.3,
        ease: 'power2.out',
      });
    }
  };

  const handleBlur = () => {
    if (containerRef.current) {
      gsap.to(containerRef.current, {
        boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.04)',
        borderColor: 'rgba(255, 255, 255, 0.08)',
        duration: 0.3,
        ease: 'power2.out',
      });
    }
  };

  const handleSend = useCallback(() => {
    const trimmed = content.trim();
    if (trimmed && !isLoading && !disabled) {
      // Send pulse animation
      if (sendBtnRef.current) {
        gsap.fromTo(
          sendBtnRef.current,
          { scale: 0.85 },
          { scale: 1, duration: 0.4, ease: 'elastic.out(1, 0.3)' },
        );
      }
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
    <div
      ref={containerRef}
      className="glass-capsule px-2 py-1.5 flex items-center gap-1.5 transition-all duration-300 opacity-0"
    >
      {/* Voice toggle */}
      {onVoiceToggle && (
        <button
          onClick={onVoiceToggle}
          disabled={disabled || isLoading}
          className={clsx('glass-circle flex-shrink-0 w-9 h-9 flex items-center justify-center', {
            'active !bg-hud-red/15 !border-hud-red/30': isRecording,
          })}
        >
          {isRecording ? (
            <MicOff size={15} className="text-hud-red" />
          ) : (
            <Mic size={15} className="text-jarvis-blue/60" />
          )}
        </button>
      )}

      {/* Text input */}
      <div className="flex-1 relative min-w-0 flex items-center">
        <textarea
          ref={textareaRef}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={handleFocus}
          onBlur={handleBlur}
          placeholder="Message J.A.R.V.I.S."
          disabled={disabled || isLoading}
          rows={1}
          className={clsx(
            'w-full resize-none bg-transparent border-none text-sm text-gray-200 placeholder:text-gray-600 placeholder:text-center disabled:opacity-50 focus:outline-none px-3 py-[8px] font-sans leading-5',
            !content && 'text-center',
          )}
        />
      </div>

      {/* Send button */}
      <button
        ref={sendBtnRef}
        onClick={handleSend}
        disabled={!hasContent || isLoading || disabled}
        className={clsx('glass-circle flex-shrink-0 w-9 h-9 flex items-center justify-center transition-all', {
          'opacity-30 cursor-not-allowed': !hasContent || isLoading || disabled,
          '!bg-jarvis-gold/12 !border-jarvis-gold/25': hasContent && !isLoading && !disabled,
        })}
      >
        {isLoading ? (
          <Loader2 size={15} className="animate-spin text-jarvis-blue/60" />
        ) : (
          <Send
            size={15}
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
