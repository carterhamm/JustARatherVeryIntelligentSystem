import { useEffect, useCallback, useRef } from 'react';
import { wsManager } from '@/services/websocket';
import { useAuthStore } from '@/stores/authStore';
import { useUIStore } from '@/stores/uiStore';

type MessageHandler = (data: unknown) => void;

export function useWebSocket(onMessage?: MessageHandler) {
  const token = useAuthStore((state) => state.token);
  const setWsConnected = useUIStore((state) => state.setWsConnected);
  const handlerRef = useRef<MessageHandler | undefined>(onMessage);
  handlerRef.current = onMessage;

  useEffect(() => {
    if (!token) return;

    const wsUrl = import.meta.env.VITE_WS_URL || `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/chat`;

    wsManager.connect({
      url: wsUrl,
      token,
      onMessage: (data) => {
        handlerRef.current?.(data);
      },
      onConnect: () => {
        setWsConnected(true);
      },
      onDisconnect: () => {
        setWsConnected(false);
      },
    });

    return () => {
      wsManager.disconnect();
      setWsConnected(false);
    };
  }, [token, setWsConnected]);

  const send = useCallback((data: unknown) => {
    wsManager.send(data);
  }, []);

  const isConnected = useUIStore((state) => state.wsConnected);

  return {
    send,
    isConnected,
  };
}
