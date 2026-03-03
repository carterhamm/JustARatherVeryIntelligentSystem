import { useCallback, useEffect } from 'react';
import { useChatStore, Message, Conversation } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import { useSettingsStore } from '@/stores/settingsStore';
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

  const handleWsMessage = useCallback(
    (data: unknown) => {
      const msg = data as Record<string, unknown>;

      switch (msg.type) {
        case 'stream_start': {
          const assistantMsg: Message = {
            id: msg.message_id as string,
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

        case 'stream_chunk': {
          appendToMessage(msg.message_id as string, msg.content as string);
          break;
        }

        case 'stream_end': {
          updateMessage(msg.message_id as string, (msg.full_content as string) || '', false);
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
          const blob = msg.blob as Blob;
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

        case 'error': {
          setIsStreaming(false);
          setIsThinking(false);
          setJarvisActivity(0);
          const errorMsg: Message = {
            id: `error-${Date.now()}`,
            role: 'system',
            content: (msg.message as string) || 'An error occurred',
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

      if (isConnected) {
        send({
          type: 'chat_message',
          content: content.trim(),
          conversation_id: currentConversation?.id,
          model_provider: modelPreference,
          voice_enabled: voiceEnabled,
        });
      } else {
        try {
          const response = await api.post<{
            message: Message;
            conversation_id: string;
          }>('/chat/message', {
            content: content.trim(),
            conversation_id: currentConversation?.id,
            model_provider: modelPreference,
          });

          addMessage(response.message);
          setIsThinking(false);
          setJarvisActivity(0.2);
        } catch {
          setIsThinking(false);
          setJarvisActivity(0);
          addMessage({
            id: `error-${Date.now()}`,
            role: 'system',
            content: 'Failed to send message. Please try again.',
            timestamp: new Date().toISOString(),
          });
        }
      }
    },
    [addMessage, currentConversation, isConnected, send, setIsThinking, setJarvisActivity, modelPreference, voiceEnabled]
  );

  const createConversation = useCallback(async () => {
    try {
      const conversation = await api.post<Conversation>('/chat/conversations', {
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
        const [conversation, messagesData] = await Promise.all([
          api.get<Conversation>(`/chat/conversations/${id}`),
          api.get<Message[]>(`/chat/conversations/${id}/messages`),
        ]);
        setCurrentConversation(conversation);
        setMessages(messagesData);
      } catch {
        /* silently fail */
      }
    },
    [setCurrentConversation, setMessages]
  );

  const loadConversations = useCallback(async () => {
    try {
      const data = await api.get<Conversation[]>('/chat/conversations');
      setConversations(data);
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
