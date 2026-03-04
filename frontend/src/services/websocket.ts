type MessageHandler = (data: unknown) => void;
type ConnectionHandler = () => void;

interface WebSocketConfig {
  url: string;
  token?: string;
  onMessage?: MessageHandler;
  onConnect?: ConnectionHandler;
  onDisconnect?: ConnectionHandler;
}

// Close codes that should NOT trigger reconnection
const NO_RECONNECT_CODES = new Set([
  1000, // Normal closure
  1008, // Policy violation (invalid token / auth failure)
]);

class WebSocketManager {
  private static instance: WebSocketManager;
  private ws: WebSocket | null = null;
  private config: WebSocketConfig | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private reconnectDelay = 1000;
  private heartbeatInterval: ReturnType<typeof setInterval> | null = null;
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
  private messageHandlers: Set<MessageHandler> = new Set();
  private connectHandlers: Set<ConnectionHandler> = new Set();
  private disconnectHandlers: Set<ConnectionHandler> = new Set();
  private _isConnected = false;
  private _authFailed = false;

  static getInstance(): WebSocketManager {
    if (!WebSocketManager.instance) {
      WebSocketManager.instance = new WebSocketManager();
    }
    return WebSocketManager.instance;
  }

  get isConnected(): boolean {
    return this._isConnected;
  }

  get authFailed(): boolean {
    return this._authFailed;
  }

  connect(config: WebSocketConfig): void {
    this.config = config;
    this._authFailed = false;

    if (config.onMessage) this.messageHandlers.add(config.onMessage);
    if (config.onConnect) this.connectHandlers.add(config.onConnect);
    if (config.onDisconnect) this.disconnectHandlers.add(config.onDisconnect);

    this.createConnection();
  }

  private createConnection(): void {
    if (!this.config) return;
    // Don't reconnect if auth already failed
    if (this._authFailed) return;

    const url = this.config.token
      ? `${this.config.url}?token=${this.config.token}`
      : this.config.url;

    try {
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        this._isConnected = true;
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;
        this.startHeartbeat();
        this.connectHandlers.forEach((handler) => handler());
      };

      this.ws.onmessage = (event: MessageEvent) => {
        // Binary frame = TTS audio blob
        if (event.data instanceof Blob) {
          this.messageHandlers.forEach((h) =>
            h({ type: 'audio_binary', blob: event.data })
          );
          return;
        }

        try {
          const data = JSON.parse(event.data);

          if (data.type === 'pong') return;

          // Detect auth errors from the server — these arrive as error
          // messages just before the server closes the connection.
          if (data.type === 'error') {
            const err = (data.error || '') as string;
            const isAuthError =
              err.includes('Invalid token') ||
              err.includes('Token required') ||
              err.includes('Authentication failed');
            if (isAuthError) {
              this._authFailed = true;
            }
          }

          this.messageHandlers.forEach((handler) => handler(data));
        } catch {
          this.messageHandlers.forEach((handler) => handler(event.data));
        }
      };

      this.ws.onclose = (event: CloseEvent) => {
        this._isConnected = false;
        this.stopHeartbeat();
        this.disconnectHandlers.forEach((handler) => handler());

        // Don't reconnect on auth failures or deliberate closures
        if (this._authFailed || NO_RECONNECT_CODES.has(event.code)) {
          return;
        }

        this.attemptReconnect();
      };

      this.ws.onerror = () => {
        this._isConnected = false;
      };
    } catch {
      this.attemptReconnect();
    }
  }

  private attemptReconnect(): void {
    if (this._authFailed) return;
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      return;
    }

    this.reconnectAttempts++;
    const delay = Math.min(
      this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
      30000
    );

    this.reconnectTimeout = setTimeout(() => {
      this.createConnection();
    }, delay);
  }

  private startHeartbeat(): void {
    this.heartbeatInterval = setInterval(() => {
      this.send({ type: 'ping' });
    }, 30000);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  send(data: unknown): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(typeof data === 'string' ? data : JSON.stringify(data));
    }
  }

  onMessage(handler: MessageHandler): () => void {
    this.messageHandlers.add(handler);
    return () => this.messageHandlers.delete(handler);
  }

  onConnect(handler: ConnectionHandler): () => void {
    this.connectHandlers.add(handler);
    return () => this.connectHandlers.delete(handler);
  }

  onDisconnect(handler: ConnectionHandler): () => void {
    this.disconnectHandlers.add(handler);
    return () => this.disconnectHandlers.delete(handler);
  }

  disconnect(): void {
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
    this.stopHeartbeat();
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
      this.ws = null;
    }
    this._isConnected = false;
    this._authFailed = false;
    this.messageHandlers.clear();
    this.connectHandlers.clear();
    this.disconnectHandlers.clear();
  }
}

export const wsManager = WebSocketManager.getInstance();
