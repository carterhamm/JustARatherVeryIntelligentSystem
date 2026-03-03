import { useEffect, useCallback, useRef } from 'react';
import { wsManager } from '@/services/websocket';
import { useAuthStore } from '@/stores/authStore';
import { useUIStore } from '@/stores/uiStore';

type MessageHandler = (data: unknown) => void;

// Track whether the WS connection has already been initialised so that
// multiple components calling useWebSocket don't register duplicate
// message handlers (which caused double-bubble issues).
let wsInitialised = false;

export function useWebSocket(onMessage?: MessageHandler) {
  const token = useAuthStore((state) => state.token);
  const setWsConnected = useUIStore((state) => state.setWsConnected);
  const handlerRef = useRef<MessageHandler | undefined>(onMessage);
  handlerRef.current = onMessage;

  useEffect(() => {
    if (!token) return;

    // Only the FIRST caller sets up the connection + message handler.
    // Subsequent callers (e.g. HUDNavPanel also importing useChat) are
    // no-ops — they still get send() and isConnected from the store.
    if (wsInitialised) return;
    wsInitialised = true;

    const wsUrl =
      import.meta.env.VITE_WS_URL ||
      `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/api/v1/ws/chat`;

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
      wsInitialised = false;
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
