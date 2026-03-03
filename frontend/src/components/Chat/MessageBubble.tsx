import { useState, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { atomDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Copy, Check } from 'lucide-react';
import { Message } from '@/stores/chatStore';
import clsx from 'clsx';

interface MessageBubbleProps {
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
    <div className="relative group my-2 overflow-hidden border border-jarvis-blue/15"
      style={{ clipPath: 'polygon(0 6px, 6px 0, calc(100% - 6px) 0, 100% 6px, 100% calc(100% - 6px), calc(100% - 6px) 100%, 6px 100%, 0 calc(100% - 6px))' }}>
      <div className="flex items-center justify-between px-4 py-1.5 bg-[#0a0a1e] border-b border-jarvis-blue/15">
        <span className="hud-label text-[8px]">{language || 'code'}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 text-[10px] text-jarvis-blue/50 hover:text-jarvis-blue transition-colors"
        >
          {copied ? <><Check size={10} /> Copied</> : <><Copy size={10} /> Copy</>}
        </button>
      </div>
      <SyntaxHighlighter
        style={atomDark}
        language={language || 'text'}
        customStyle={{
          margin: 0,
          background: '#060612',
          padding: '0.75rem 1rem',
          fontSize: '0.8rem',
        }}
      >
        {children}
      </SyntaxHighlighter>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 py-1">
      <div className="typing-dot w-1.5 h-1.5 rounded-full bg-jarvis-cyan" />
      <div className="typing-dot w-1.5 h-1.5 rounded-full bg-jarvis-cyan" />
      <div className="typing-dot w-1.5 h-1.5 rounded-full bg-jarvis-cyan" />
    </div>
  );
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';

  const timeDisplay = useMemo(() => {
    const date = new Date(message.timestamp);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }, [message.timestamp]);

  if (isSystem) {
    return (
      <div className="flex justify-center my-3">
        <div className="px-4 py-1.5 border border-jarvis-blue/10 bg-hud-panel/50 max-w-lg"
          style={{ clipPath: 'polygon(0 4px, 4px 0, calc(100% - 4px) 0, 100% 4px, 100% calc(100% - 4px), calc(100% - 4px) 100%, 4px 100%, 0 calc(100% - 4px))' }}>
          <p className="text-[10px] text-center text-gray-500 font-mono">{message.content}</p>
        </div>
      </div>
    );
  }

  return (
    <div
      className={clsx('flex mb-4', {
        'justify-end': isUser,
        'justify-start': !isUser,
      })}
    >
      <div className={clsx('max-w-[75%] relative group', { 'order-1': isUser })}>
        {/* Label */}
        {!isUser && (
          <div className="flex items-center gap-2 mb-1">
            <div className="w-4 h-4 flex items-center justify-center" style={{
              clipPath: 'polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%)',
              background: 'linear-gradient(135deg, rgba(0, 212, 255, 0.3), rgba(0, 128, 255, 0.2))',
            }}>
              <span className="text-[6px] font-bold text-jarvis-blue">J</span>
            </div>
            <span className="hud-label text-[8px]">J.A.R.V.I.S.</span>
          </div>
        )}
        {isUser && (
          <div className="flex items-center justify-end gap-1.5 mb-1">
            <span className="hud-label text-[8px] text-jarvis-gold/50">YOU</span>
          </div>
        )}

        {/* Bubble */}
        <div
          className={clsx('px-4 py-3 text-sm leading-relaxed', {
            'bg-jarvis-gold/[0.08] border border-jarvis-gold/25 text-white': isUser,
            'bg-hud-panel border border-jarvis-blue/15 text-gray-200': !isUser,
          })}
          style={{
            clipPath: 'polygon(0 6px, 6px 0, calc(100% - 6px) 0, 100% 6px, 100% calc(100% - 6px), calc(100% - 6px) 100%, 6px 100%, 0 calc(100% - 6px))',
            backdropFilter: 'blur(8px)',
          }}
        >
          {message.isStreaming && !message.content ? (
            <TypingIndicator />
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
                          className="px-1.5 py-0.5 bg-jarvis-darker/80 text-jarvis-cyan text-xs font-mono border border-jarvis-blue/15"
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
                      <a href={href} target="_blank" rel="noopener noreferrer"
                        className="text-jarvis-blue hover:text-jarvis-cyan underline">
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
                {message.content}
              </ReactMarkdown>
            </div>
          )}

          {message.isStreaming && message.content && (
            <span className="inline-block w-0.5 h-4 bg-jarvis-cyan ml-0.5 animate-pulse" />
          )}
        </div>

        {/* Timestamp */}
        <div
          className={clsx(
            'text-[9px] text-gray-600 mt-1 opacity-0 group-hover:opacity-100 transition-opacity font-mono',
            { 'text-right': isUser, 'text-left': !isUser },
          )}
        >
          {timeDisplay}
        </div>
      </div>
    </div>
  );
}
