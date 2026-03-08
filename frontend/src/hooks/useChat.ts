import { useCallback, useEffect, useRef } from 'react';
import { useChatStore, Message, Conversation } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import { useSettingsStore, type ModelProvider } from '@/stores/settingsStore';
import { useAuthStore } from '@/stores/authStore';
import { useWebSocket } from './useWebSocket';
import { api } from '@/services/api';

export function useChat() {
  const {
    conversations,
    currentConversation,
    messages,
    isStreaming,
    setConversations,
    setCurrentConversation,
    setMessages,
    addMessage,
    appendToMessage,
    updateMessage,
    setIsStreaming,
    addConversation,
    clearMessages,
  } = useChatStore();

  const { setIsThinking, setJarvisActivity, setIsSpeaking } = useUIStore();
  const modelPreference = useSettingsStore((s) => s.modelPreference);
  const voiceEnabled = useSettingsStore((s) => s.voiceEnabled);

  // Track the current streaming message ID so token chunks can append
  const streamingMsgId = useRef<string | null>(null);
  // Track last error to deduplicate rapidly repeating errors
  const lastErrorRef = useRef<string>('');

  const handleWsMessage = useCallback(
    (data: unknown) => {
      const msg = data as Record<string, unknown>;

      switch (msg.type) {
        // Backend sends type="start" with conversation_id + message_id
        case 'start': {
          const msgId = String(msg.message_id);
          streamingMsgId.current = msgId;
          const assistantMsg: Message = {
            id: msgId,
            role: 'assistant',
            content: '',
            timestamp: new Date().toISOString(),
            isStreaming: true,
          };
          addMessage(assistantMsg);
          setIsStreaming(true);
          setIsThinking(false);
          setJarvisActivity(0.7);
          break;
        }

        // Backend sends type="token" with content delta
        case 'token': {
          const id = streamingMsgId.current;
          if (id && msg.content) {
            appendToMessage(id, msg.content as string);
          }
          break;
        }

        // Backend sends type="end" with done=true
        case 'end': {
          const id = streamingMsgId.current;
          if (id) {
            updateMessage(id, undefined, false);
          }
          streamingMsgId.current = null;
          setIsStreaming(false);
          setJarvisActivity(0.2);
          break;
        }

        case 'audio_response': {
          setIsSpeaking(true);
          const audio = new Audio(msg.audio_url as string);
          audio.onended = () => {
            setIsSpeaking(false);
            setJarvisActivity(0.1);
          };
          audio.play().catch(() => setIsSpeaking(false));
          break;
        }

        case 'audio_binary': {
          setIsSpeaking(true);
          const rawBlob = msg.blob as Blob;
          // Ensure blob has audio MIME type for browser playback
          const blob = rawBlob.type ? rawBlob : new Blob([rawBlob], { type: 'audio/wav' });
          const audioUrl = URL.createObjectURL(blob);
          const binaryAudio = new Audio(audioUrl);
          binaryAudio.onended = () => {
            setIsSpeaking(false);
            setJarvisActivity(0.1);
            URL.revokeObjectURL(audioUrl);
          };
          binaryAudio.play().catch(() => {
            setIsSpeaking(false);
            URL.revokeObjectURL(audioUrl);
          });
          break;
        }

        // Backend sends type="replace" — corrected text with tool tags stripped
        case 'replace': {
          const id = streamingMsgId.current;
          if (id && msg.content) {
            updateMessage(id, msg.content as string);
          }
          break;
        }

        // Backend sends type="tool_call" with tool + tool_arg
        case 'tool_call': {
          const tool = msg.tool as string;
          const arg = msg.tool_arg as string;

          if (tool === 'SWITCH_MODEL') {
            const validProviders = ['claude', 'gemini', 'stark_protocol'];
            if (validProviders.includes(arg)) {
              useSettingsStore.getState().setModelPreference(arg as ModelProvider);
            }
          } else if (tool === 'TOGGLE_VOICE') {
            useSettingsStore.getState().setVoiceEnabled(arg === 'on');
          }
          break;
        }

        // Backend sends type="error" with error field
        case 'error': {
          setIsStreaming(false);
          setIsThinking(false);
          setJarvisActivity(0);
          streamingMsgId.current = null;

          const errorText = (msg.error as string) || 'An error occurred';

          // Auth errors: log out and redirect to login — don't spam messages
          const isAuthError =
            errorText.includes('Invalid token') ||
            errorText.includes('Token required') ||
            errorText.includes('Authentication failed');
          if (isAuthError) {
            useAuthStore.getState().logout();
            break;
          }

          // Deduplicate: skip if same error text as the last one
          if (errorText === lastErrorRef.current) break;
          lastErrorRef.current = errorText;
          // Reset dedup after 5s so the same error can appear again later
          setTimeout(() => { lastErrorRef.current = ''; }, 5000);

          const errorMsg: Message = {
            id: `error-${Date.now()}`,
            role: 'system',
            content: errorText,
            timestamp: new Date().toISOString(),
          };
          addMessage(errorMsg);
          break;
        }
      }
    },
    [addMessage, appendToMessage, updateMessage, setIsStreaming, setIsThinking, setJarvisActivity, setIsSpeaking]
  );

  const { send, isConnected } = useWebSocket(handleWsMessage);

  const sendMessage = useCallback(
    async (content: string) => {
      if (!content.trim()) return;

      const userMessage: Message = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: content.trim(),
        timestamp: new Date().toISOString(),
      };

      addMessage(userMessage);
      setIsThinking(true);
      setJarvisActivity(0.5);

      // Backend ChatRequest expects "message" not "content"
      send({
        message: content.trim(),
        conversation_id: currentConversation?.id,
        model_provider: modelPreference,
        voice_enabled: voiceEnabled,
      });

      // If WS is not connected, show an error (no REST fallback endpoint)
      if (!isConnected) {
        setIsThinking(false);
        setJarvisActivity(0);
        addMessage({
          id: `error-${Date.now()}`,
          role: 'system',
          content: 'Not connected to server. Please refresh the page.',
          timestamp: new Date().toISOString(),
        });
      }
    },
    [addMessage, currentConversation, isConnected, send, setIsThinking, setJarvisActivity, modelPreference, voiceEnabled]
  );

  const createConversation = useCallback(async () => {
    try {
      const conversation = await api.post<Conversation>('/conversations', {
        title: 'New Conversation',
      });
      addConversation(conversation);
      setCurrentConversation(conversation);
      clearMessages();
      return conversation;
    } catch {
      return null;
    }
  }, [addConversation, setCurrentConversation, clearMessages]);

  const loadConversation = useCallback(
    async (id: string) => {
      try {
        const [conversation, rawMessages] = await Promise.all([
          api.get<Conversation>(`/conversations/${id}`),
          api.get<any[]>(`/conversations/${id}/messages`),
        ]);
        setCurrentConversation(conversation);
        // Map backend MessageResponse (created_at) to frontend Message (timestamp)
        const mapped: Message[] = rawMessages.map((m) => ({
          id: String(m.id),
          role: m.role,
          content: m.content,
          timestamp: m.created_at || m.timestamp || new Date().toISOString(),
        }));
        setMessages(mapped);
      } catch {
        /* silently fail */
      }
    },
    [setCurrentConversation, setMessages]
  );

  const loadConversations = useCallback(async () => {
    try {
      const data = await api.get<{ conversations: Conversation[]; total: number }>('/conversations');
      // Backend returns { conversations: [...], total } wrapper
      setConversations(data.conversations);
    } catch {
      /* silently fail */
    }
  }, [setConversations]);

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  return {
    conversations,
    currentConversation,
    messages,
    isStreaming,
    isConnected,
    sendMessage,
    createConversation,
    loadConversation,
    loadConversations,
  };
}
