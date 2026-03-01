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
    <div className="relative group my-2 rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 bg-[#1a1a2e] border-b border-jarvis-blue/20">
        <span className="text-xs text-jarvis-blue/70 font-mono">{language || 'code'}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 text-xs text-jarvis-blue/50 hover:text-jarvis-blue transition-colors"
        >
          {copied ? (
            <>
              <Check size={12} />
              <span>Copied</span>
            </>
          ) : (
            <>
              <Copy size={12} />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>
      <SyntaxHighlighter
        style={atomDark}
        language={language || 'text'}
        customStyle={{
          margin: 0,
          background: '#0d0d1a',
          padding: '1rem',
          fontSize: '0.85rem',
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
        <div className="px-4 py-2 rounded-lg bg-jarvis-darker/50 border border-jarvis-blue/10 max-w-lg">
          <p className="text-xs text-center text-gray-400">{message.content}</p>
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
      <div
        className={clsx('max-w-[75%] relative group', {
          'order-1': isUser,
        })}
      >
        {/* Avatar indicator */}
        {!isUser && (
          <div className="flex items-center gap-2 mb-1">
            <div className="w-5 h-5 rounded-full bg-gradient-to-br from-jarvis-blue to-jarvis-cyan flex items-center justify-center">
              <span className="text-[10px] font-bold text-jarvis-darker">J</span>
            </div>
            <span className="text-xs text-jarvis-blue/60 font-display tracking-wider">J.A.R.V.I.S.</span>
          </div>
        )}

        {/* Message bubble */}
        <div
          className={clsx('rounded-2xl px-4 py-3 text-sm leading-relaxed', {
            'bg-gradient-to-br from-jarvis-blue/20 to-blue-600/20 border border-jarvis-blue/30 text-white':
              isUser,
            'bg-jarvis-darker/80 border border-jarvis-blue/15 text-gray-200': !isUser,
          })}
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
                          className="px-1.5 py-0.5 rounded bg-jarvis-darker/60 text-jarvis-cyan text-xs font-mono border border-jarvis-blue/20"
                          {...props}
                        >
                          {children}
                        </code>
                      );
                    }

                    return (
                      <CodeBlock language={match[1]}>{codeString}</CodeBlock>
                    );
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
                        className="text-jarvis-blue hover:text-jarvis-cyan underline"
                      >
                        {children}
                      </a>
                    );
                  },
                  blockquote({ children }) {
                    return (
                      <blockquote className="border-l-2 border-jarvis-blue/40 pl-3 my-2 text-gray-400 italic">
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
            'text-[10px] text-gray-500 mt-1 opacity-0 group-hover:opacity-100 transition-opacity',
            {
              'text-right': isUser,
              'text-left': !isUser,
            }
          )}
        >
          {timeDisplay}
        </div>
      </div>
    </div>
  );
}
