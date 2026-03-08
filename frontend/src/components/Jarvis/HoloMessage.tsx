import { useState, useMemo, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { atomDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Copy, Check } from 'lucide-react';
import { Message } from '@/stores/chatStore';
import gsap from 'gsap';
import clsx from 'clsx';

interface HoloMessageProps {
  message: Message;
}

function CodeBlock({ language, children }: { language: string; children: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(children);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="relative group my-2.5 rounded-xl overflow-hidden border border-white/[0.06]">
      <div className="flex items-center justify-between px-4 py-1.5 bg-black/40 border-b border-white/[0.04]">
        <span className="text-[9px] font-mono text-jarvis-blue/60 uppercase tracking-wider">
          {language || 'code'}
        </span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 text-[10px] text-gray-500 hover:text-jarvis-blue transition-colors"
        >
          {copied ? (
            <>
              <Check size={10} /> Copied
            </>
          ) : (
            <>
              <Copy size={10} /> Copy
            </>
          )}
        </button>
      </div>
      <SyntaxHighlighter
        style={atomDark}
        language={language || 'text'}
        customStyle={{
          margin: 0,
          background: 'rgba(0, 0, 0, 0.5)',
          padding: '0.75rem 1rem',
          fontSize: '0.8rem',
          borderRadius: 0,
        }}
      >
        {children}
      </SyntaxHighlighter>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1.5 py-1 px-1">
      <div className="typing-dot w-1.5 h-1.5 rounded-full bg-jarvis-cyan" />
      <div className="typing-dot w-1.5 h-1.5 rounded-full bg-jarvis-cyan" />
      <div className="typing-dot w-1.5 h-1.5 rounded-full bg-jarvis-cyan" />
    </div>
  );
}

export default function HoloMessage({ message }: HoloMessageProps) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const msgRef = useRef<HTMLDivElement>(null);

  // Strip any leaked tool tags like {{TOGGLE_VOICE:off}} from display
  const displayContent = useMemo(
    () => message.content.replace(/\{\{\w+:\w+\}\}/g, '').trim(),
    [message.content],
  );

  const timeDisplay = useMemo(() => {
    const date = new Date(message.timestamp);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }, [message.timestamp]);

  // GSAP entry animation
  useEffect(() => {
    if (msgRef.current && !message.isStreaming) {
      gsap.fromTo(
        msgRef.current,
        {
          opacity: 0,
          y: 12,
          scale: 0.98,
        },
        {
          opacity: 1,
          y: 0,
          scale: 1,
          duration: 0.4,
          ease: 'power3.out',
        },
      );
    }
  }, []);

  // System/error messages
  if (isSystem) {
    return (
      <div className="flex justify-center my-2 animate-fade-in">
        <div className="glass-subtle rounded-xl px-4 py-2 max-w-lg border-hud-red/10">
          <p className="text-[11px] text-center text-gray-400 font-mono">{displayContent}</p>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={msgRef}
      className={clsx('flex mb-4', {
        'justify-end': isUser,
        'justify-start': !isUser,
      })}
    >
      <div className={clsx('max-w-[80%] relative group')}>
        {/* Label */}
        {!isUser && (
          <div className="flex items-center gap-2 mb-1.5">
            <div
              className="w-5 h-5 flex items-center justify-center flex-shrink-0"
              style={{
                clipPath: 'polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%)',
                background: 'linear-gradient(135deg, rgba(0, 212, 255, 0.25), rgba(0, 128, 255, 0.15))',
              }}
            >
              <span className="text-[7px] font-bold text-jarvis-blue">J</span>
            </div>
            <span className="hud-label text-[8px]">J.A.R.V.I.S.</span>
            <span className="text-[7px] font-mono text-jarvis-blue/20">{timeDisplay}</span>
          </div>
        )}
        {isUser && (
          <div className="flex items-center justify-end gap-1.5 mb-1.5">
            <span className="text-[7px] font-mono text-jarvis-gold/20">{timeDisplay}</span>
            <span className="text-[9px] font-mono text-jarvis-gold/50 tracking-wider uppercase">
              You
            </span>
          </div>
        )}

        {/* Message bubble */}
        <div
          className={clsx('rounded-2xl text-sm leading-relaxed', {
            'glass-gold text-white/90 px-5 py-3.5': isUser,
            'glass-cyan text-gray-200': !isUser,
            'px-4 py-3 w-16': !isUser && message.isStreaming && !message.content,
            'px-5 py-3.5': !isUser && !(message.isStreaming && !message.content),
          })}
        >
          {message.isStreaming && !message.content ? (
            <div className="flex justify-center">
              <TypingIndicator />
            </div>
          ) : (
            <div className="prose prose-invert prose-sm max-w-none">
              <ReactMarkdown
                components={{
                  code({ className, children, ...props }) {
                    const match = /language-(\w+)/.exec(className || '');
                    const isInline = !match;
                    const codeString = String(children).replace(/\n$/, '');

                    if (isInline) {
                      return (
                        <code
                          className="px-1.5 py-0.5 bg-black/30 text-jarvis-cyan text-xs font-mono rounded-md border border-white/[0.05]"
                          {...props}
                        >
                          {children}
                        </code>
                      );
                    }
                    return <CodeBlock language={match[1]}>{codeString}</CodeBlock>;
                  },
                  p({ children }) {
                    return <p className="mb-2 last:mb-0">{children}</p>;
                  },
                  ul({ children }) {
                    return <ul className="list-disc list-inside mb-2 space-y-1">{children}</ul>;
                  },
                  ol({ children }) {
                    return <ol className="list-decimal list-inside mb-2 space-y-1">{children}</ol>;
                  },
                  a({ href, children }) {
                    return (
                      <a
                        href={href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-jarvis-blue hover:text-jarvis-cyan underline underline-offset-2"
                      >
                        {children}
                      </a>
                    );
                  },
                  blockquote({ children }) {
                    return (
                      <blockquote className="border-l-2 border-jarvis-blue/30 pl-3 my-2 text-gray-400 italic">
                        {children}
                      </blockquote>
                    );
                  },
                }}
              >
                {displayContent}
              </ReactMarkdown>
            </div>
          )}

          {message.isStreaming && message.content && (
            <span className="inline-block w-0.5 h-4 bg-jarvis-cyan ml-0.5 animate-pulse" />
          )}
        </div>

        {/* Timestamp — shows on hover (hidden since we moved it inline) */}
        <div
          className={clsx(
            'text-[9px] text-gray-600 mt-1.5 opacity-0 group-hover:opacity-100 transition-opacity font-mono',
            { 'text-right': isUser, 'text-left': !isUser },
          )}
        >
          {timeDisplay}
        </div>
      </div>
    </div>
  );
}
