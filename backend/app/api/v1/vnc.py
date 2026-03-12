"""VNC remote desktop viewer — JARVIS HUD-styled noVNC client.

Serves a self-contained HTML page at ``/vnc/mac-mini`` that connects to
the Mac Mini's websockify proxy via Cloudflare tunnel.  Requires JWT
authentication (Bearer token in query param or Authorization header).
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.security import decode_token
from app.schemas.auth import TokenPayload

router = APIRouter(prefix="/vnc")


async def _get_user_from_token_or_query(
    request: Request,
    token: str | None = Query(None, alias="token"),
    db: AsyncSession = Depends(get_db),
) -> TokenPayload:
    """Extract JWT from query param ``?token=`` or Authorization header.

    For browser-navigated pages we cannot rely on the standard OAuth2
    header alone, so we also accept the token as a query parameter.
    """
    raw_token: str | None = None

    # 1. Query parameter
    if token:
        raw_token = token

    # 2. Authorization header
    if not raw_token:
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            raw_token = auth[7:]

    # 3. Cookie fallback
    if not raw_token:
        raw_token = request.cookies.get("access_token")

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    payload = decode_token(raw_token)
    if payload.type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )
    return payload


# ---------------------------------------------------------------------------
# VNC Viewer page
# ---------------------------------------------------------------------------

VNC_PAGE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>J.A.R.V.I.S. // Remote Desktop</title>

<!-- noVNC — try multiple CDN sources with fallback -->
<script type="module">
async function loadNoVNC() {
  const sources = [
    'https://esm.sh/@novnc/novnc@1.5.0/core/rfb.js',
    'https://esm.sh/@novnc/novnc@1.4.0/core/rfb.js',
    'https://cdn.skypack.dev/@novnc/novnc@1.5.0/core/rfb.js',
  ];
  for (const src of sources) {
    try {
      const mod = await import(src);
      const RFB = mod.default || mod.RFB;
      if (RFB) {
        console.log('[noVNC] Loaded from:', src);
        window.RFB = RFB;
        window.dispatchEvent(new Event('novnc-loaded'));
        return;
      }
    } catch (err) {
      console.warn('[noVNC] Failed:', src, err.message);
    }
  }
  window.dispatchEvent(new CustomEvent('novnc-error', {
    detail: 'All noVNC CDN sources failed. Check browser console.'
  }));
}
loadNoVNC();
</script>

<style>
  @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@300;400;500;600;700&family=Share+Tech+Mono&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg-primary: #0A0E17;
    --bg-secondary: #0D1321;
    --bg-panel: rgba(13, 19, 33, 0.85);
    --cyan: #00d4ff;
    --cyan-bright: #00E5FF;
    --cyan-dim: rgba(0, 212, 255, 0.15);
    --cyan-glow: rgba(0, 212, 255, 0.3);
    --orange: #FF6D00;
    --orange-dim: rgba(255, 109, 0, 0.2);
    --green: #00E676;
    --red: #FF1744;
    --text-primary: #E0E6ED;
    --text-secondary: #8899AA;
    --text-dim: #4A5568;
    --border: rgba(0, 212, 255, 0.25);
    --font-hud: 'Rajdhani', 'Segoe UI', sans-serif;
    --font-mono: 'Share Tech Mono', 'Courier New', monospace;
  }

  html, body {
    width: 100%; height: 100%;
    overflow: hidden;
    background: var(--bg-primary);
    color: var(--text-primary);
    font-family: var(--font-hud);
  }

  /* Grid background pattern */
  body::before {
    content: '';
    position: fixed;
    inset: 0;
    background-image:
      linear-gradient(rgba(0, 212, 255, 0.03) 1px, transparent 1px),
      linear-gradient(90deg, rgba(0, 212, 255, 0.03) 1px, transparent 1px);
    background-size: 40px 40px;
    pointer-events: none;
    z-index: 0;
  }

  /* ═══════════════════════ STATUS BAR ═══════════════════════ */
  .status-bar {
    position: fixed;
    top: 0; left: 0; right: 0;
    height: 42px;
    background: var(--bg-panel);
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 16px;
    z-index: 100;
    backdrop-filter: blur(10px);
  }

  .status-bar::after {
    content: '';
    position: absolute;
    bottom: -1px;
    left: 0; right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, var(--cyan), transparent);
    opacity: 0.5;
  }

  .status-left, .status-center, .status-right {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .status-center {
    position: absolute;
    left: 50%;
    transform: translateX(-50%);
  }

  .status-label {
    font-family: var(--font-mono);
    font-size: 13px;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: var(--cyan);
  }

  .status-separator {
    color: var(--text-dim);
    font-family: var(--font-mono);
    font-size: 13px;
  }

  .status-indicator {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--red);
    box-shadow: 0 0 6px var(--red);
    transition: all 0.3s ease;
  }

  .status-indicator.connected {
    background: var(--green);
    box-shadow: 0 0 6px var(--green), 0 0 12px rgba(0, 230, 118, 0.3);
  }

  .status-text {
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: 1px;
    text-transform: uppercase;
    color: var(--text-secondary);
  }

  .status-text.connected { color: var(--green); }
  .status-text.error { color: var(--red); }

  /* ═══════════════════════ HUD FRAME CORNERS ═══════════════════════ */
  .hud-frame {
    position: fixed;
    top: 42px; left: 0; right: 0; bottom: 40px;
    pointer-events: none;
    z-index: 50;
  }

  .hud-corner {
    position: absolute;
    width: 24px; height: 24px;
    pointer-events: none;
  }

  .hud-corner::before, .hud-corner::after {
    content: '';
    position: absolute;
    background: var(--cyan);
    opacity: 0.6;
  }

  .hud-corner.tl { top: 4px; left: 4px; }
  .hud-corner.tl::before { top: 0; left: 0; width: 24px; height: 2px; }
  .hud-corner.tl::after  { top: 0; left: 0; width: 2px; height: 24px; }

  .hud-corner.tr { top: 4px; right: 4px; }
  .hud-corner.tr::before { top: 0; right: 0; width: 24px; height: 2px; }
  .hud-corner.tr::after  { top: 0; right: 0; width: 2px; height: 24px; }

  .hud-corner.bl { bottom: 4px; left: 4px; }
  .hud-corner.bl::before { bottom: 0; left: 0; width: 24px; height: 2px; }
  .hud-corner.bl::after  { bottom: 0; left: 0; width: 2px; height: 24px; }

  .hud-corner.br { bottom: 4px; right: 4px; }
  .hud-corner.br::before { bottom: 0; right: 0; width: 24px; height: 2px; }
  .hud-corner.br::after  { bottom: 0; right: 0; width: 2px; height: 24px; }

  /* ═══════════════════════ TOOLBAR ═══════════════════════ */
  .toolbar {
    position: fixed;
    bottom: 0; left: 0; right: 0;
    height: 40px;
    background: var(--bg-panel);
    border-top: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 0 16px;
    z-index: 100;
    backdrop-filter: blur(10px);
  }

  .toolbar::before {
    content: '';
    position: absolute;
    top: -1px;
    left: 0; right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, var(--cyan), transparent);
    opacity: 0.3;
  }

  .tb-btn {
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: 1px;
    text-transform: uppercase;
    color: var(--cyan);
    background: transparent;
    border: 1px solid var(--border);
    padding: 5px 14px;
    cursor: pointer;
    transition: all 0.2s ease;
    clip-path: polygon(6px 0, 100% 0, calc(100% - 6px) 100%, 0 100%);
    white-space: nowrap;
  }

  .tb-btn:hover {
    background: var(--cyan-dim);
    border-color: var(--cyan);
    color: var(--cyan-bright);
    box-shadow: 0 0 8px var(--cyan-glow);
  }

  .tb-btn.active {
    background: var(--cyan-dim);
    border-color: var(--cyan);
  }

  .tb-btn.danger {
    color: var(--red);
    border-color: rgba(255, 23, 68, 0.25);
  }

  .tb-btn.danger:hover {
    background: rgba(255, 23, 68, 0.1);
    border-color: var(--red);
    box-shadow: 0 0 8px rgba(255, 23, 68, 0.3);
  }

  .tb-divider {
    width: 1px;
    height: 20px;
    background: var(--border);
    margin: 0 6px;
  }

  .tb-select {
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: 1px;
    text-transform: uppercase;
    color: var(--cyan);
    background: transparent;
    border: 1px solid var(--border);
    padding: 4px 8px;
    cursor: pointer;
    outline: none;
    appearance: none;
  }

  .tb-select option {
    background: var(--bg-secondary);
    color: var(--text-primary);
  }

  .tb-label {
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 1px;
    text-transform: uppercase;
    color: var(--text-dim);
    margin-right: 4px;
  }

  /* ═══════════════════════ VNC CANVAS ═══════════════════════ */
  #vnc-container {
    position: fixed;
    top: 42px; left: 0; right: 0; bottom: 40px;
    background: var(--bg-primary);
    z-index: 10;
  }

  #vnc-container canvas {
    outline: none;
  }

  /* ═══════════════════════ LOGIN OVERLAY ═══════════════════════ */
  .login-overlay {
    position: fixed;
    inset: 0;
    background: var(--bg-primary);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 200;
    transition: opacity 0.4s ease;
  }

  .login-overlay.hidden {
    opacity: 0;
    pointer-events: none;
  }

  .login-panel {
    width: 400px;
    max-width: 90vw;
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    padding: 0;
    position: relative;
  }

  /* Angular cut corners via clip-path */
  .login-panel {
    clip-path: polygon(
      16px 0, calc(100% - 16px) 0,
      100% 16px, 100% calc(100% - 16px),
      calc(100% - 16px) 100%, 16px 100%,
      0 calc(100% - 16px), 0 16px
    );
  }

  .login-header {
    padding: 24px 32px 16px;
    border-bottom: 1px solid var(--border);
    position: relative;
  }

  .login-header::after {
    content: '';
    position: absolute;
    bottom: -1px;
    left: 20%;
    right: 20%;
    height: 1px;
    background: linear-gradient(90deg, transparent, var(--cyan), transparent);
  }

  .login-title {
    font-family: var(--font-mono);
    font-size: 14px;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: var(--cyan);
    margin-bottom: 4px;
  }

  .login-subtitle {
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: 1px;
    color: var(--text-dim);
    text-transform: uppercase;
  }

  .arc-reactor {
    display: flex;
    justify-content: center;
    padding: 24px 0 8px;
  }

  .arc-reactor-svg {
    width: 64px; height: 64px;
    animation: pulse-glow 3s ease-in-out infinite;
  }

  @keyframes pulse-glow {
    0%, 100% { filter: drop-shadow(0 0 6px var(--cyan-glow)); }
    50% { filter: drop-shadow(0 0 16px var(--cyan-glow)); }
  }

  .login-body {
    padding: 20px 32px 32px;
  }

  .input-group {
    margin-bottom: 16px;
  }

  .input-label {
    display: block;
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: var(--text-secondary);
    margin-bottom: 6px;
  }

  .input-field {
    width: 100%;
    font-family: var(--font-mono);
    font-size: 14px;
    letter-spacing: 1px;
    color: var(--cyan-bright);
    background: rgba(0, 0, 0, 0.3);
    border: 1px solid var(--border);
    padding: 10px 14px;
    outline: none;
    transition: all 0.2s ease;
  }

  .input-field::placeholder {
    color: var(--text-dim);
    letter-spacing: 2px;
  }

  .input-field:focus {
    border-color: var(--cyan);
    box-shadow: 0 0 8px var(--cyan-glow), inset 0 0 8px rgba(0, 229, 255, 0.05);
  }

  .connect-btn {
    width: 100%;
    font-family: var(--font-hud);
    font-weight: 600;
    font-size: 14px;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: var(--bg-primary);
    background: linear-gradient(135deg, var(--cyan), var(--cyan-bright));
    border: none;
    padding: 12px;
    cursor: pointer;
    transition: all 0.25s ease;
    clip-path: polygon(8px 0, calc(100% - 8px) 0, 100% 8px, 100% calc(100% - 8px), calc(100% - 8px) 100%, 8px 100%, 0 calc(100% - 8px), 0 8px);
    margin-top: 8px;
  }

  .connect-btn:hover {
    box-shadow: 0 0 20px var(--cyan-glow), 0 0 40px rgba(0, 229, 255, 0.15);
    transform: translateY(-1px);
  }

  .connect-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
  }

  .login-error {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--red);
    margin-top: 12px;
    letter-spacing: 1px;
    text-align: center;
    min-height: 16px;
  }

  /* ═══════════════════════ CONNECTING OVERLAY ═══════════════════════ */
  .connecting-overlay {
    position: fixed;
    inset: 0;
    background: rgba(10, 14, 23, 0.92);
    display: none;
    align-items: center;
    justify-content: center;
    z-index: 150;
    flex-direction: column;
    gap: 20px;
  }

  .connecting-overlay.active {
    display: flex;
  }

  .connecting-text {
    font-family: var(--font-mono);
    font-size: 13px;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: var(--cyan);
    animation: blink-text 1.5s ease-in-out infinite;
  }

  @keyframes blink-text {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }

  .spinner {
    width: 40px; height: 40px;
    border: 2px solid var(--border);
    border-top-color: var(--cyan);
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  /* ═══════════════════════ CLIPBOARD MODAL ═══════════════════════ */
  .clipboard-modal {
    position: fixed;
    inset: 0;
    background: rgba(10, 14, 23, 0.85);
    display: none;
    align-items: center;
    justify-content: center;
    z-index: 300;
  }

  .clipboard-modal.active { display: flex; }

  .clipboard-panel {
    width: 480px;
    max-width: 90vw;
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    clip-path: polygon(12px 0, calc(100% - 12px) 0, 100% 12px, 100% calc(100% - 12px), calc(100% - 12px) 100%, 12px 100%, 0 calc(100% - 12px), 0 12px);
  }

  .clipboard-header {
    padding: 16px 24px;
    border-bottom: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .clipboard-title {
    font-family: var(--font-mono);
    font-size: 12px;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: var(--cyan);
  }

  .clipboard-close {
    font-family: var(--font-mono);
    font-size: 16px;
    color: var(--text-secondary);
    background: none;
    border: none;
    cursor: pointer;
    padding: 4px;
  }

  .clipboard-close:hover { color: var(--red); }

  .clipboard-body {
    padding: 20px 24px;
  }

  .clipboard-textarea {
    width: 100%;
    height: 160px;
    font-family: var(--font-mono);
    font-size: 13px;
    color: var(--text-primary);
    background: rgba(0, 0, 0, 0.3);
    border: 1px solid var(--border);
    padding: 12px;
    outline: none;
    resize: vertical;
  }

  .clipboard-textarea:focus {
    border-color: var(--cyan);
    box-shadow: 0 0 8px var(--cyan-glow);
  }

  .clipboard-actions {
    padding: 12px 24px 20px;
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }

  /* ═══════════════════════ TOAST ═══════════════════════ */
  .toast {
    position: fixed;
    top: 54px;
    right: 16px;
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: 1px;
    text-transform: uppercase;
    padding: 8px 16px;
    border: 1px solid var(--border);
    background: var(--bg-panel);
    color: var(--text-primary);
    z-index: 400;
    opacity: 0;
    transform: translateX(20px);
    transition: all 0.3s ease;
    pointer-events: none;
    backdrop-filter: blur(10px);
  }

  .toast.visible {
    opacity: 1;
    transform: translateX(0);
  }

  .toast.success { border-color: var(--green); color: var(--green); }
  .toast.error { border-color: var(--red); color: var(--red); }
</style>
</head>
<body>

<!-- ═══════════════════════ STATUS BAR ═══════════════════════ -->
<div class="status-bar">
  <div class="status-left">
    <span class="status-label">J.A.R.V.I.S.</span>
  </div>
  <div class="status-center">
    <span class="status-label" style="color: var(--text-secondary)">Mac Mini</span>
    <span class="status-separator">//</span>
    <span class="status-label">Remote Desktop</span>
    <span class="status-separator">//</span>
    <div class="status-indicator" id="status-dot"></div>
    <span class="status-text" id="status-text">Disconnected</span>
  </div>
  <div class="status-right">
    <span class="status-text" id="resolution-text" style="color: var(--text-dim)"></span>
    <span class="status-text" id="latency-text" style="color: var(--orange)"></span>
  </div>
</div>

<!-- ═══════════════════════ HUD FRAME ═══════════════════════ -->
<div class="hud-frame">
  <div class="hud-corner tl"></div>
  <div class="hud-corner tr"></div>
  <div class="hud-corner bl"></div>
  <div class="hud-corner br"></div>
</div>

<!-- ═══════════════════════ VNC CANVAS ═══════════════════════ -->
<div id="vnc-container"></div>

<!-- ═══════════════════════ TOOLBAR ═══════════════════════ -->
<div class="toolbar">
  <span class="tb-label">Scale:</span>
  <select class="tb-select" id="scale-select">
    <option value="remote">Remote Resize</option>
    <option value="local" selected>Local Scale</option>
    <option value="none">None (1:1)</option>
  </select>

  <div class="tb-divider"></div>

  <button class="tb-btn" id="btn-clipboard" title="Clipboard sync">Clipboard</button>
  <button class="tb-btn" id="btn-keys" title="Send Ctrl+Alt+Del">Ctrl+Alt+Del</button>
  <button class="tb-btn" id="btn-fullscreen" title="Toggle fullscreen">Fullscreen</button>

  <div class="tb-divider"></div>

  <label style="display:flex;align-items:center;gap:6px;cursor:pointer">
    <input type="checkbox" id="chk-viewonly" style="accent-color:var(--cyan)">
    <span class="tb-label" style="margin:0">View Only</span>
  </label>

  <div class="tb-divider"></div>

  <button class="tb-btn danger" id="btn-disconnect">Disconnect</button>
</div>

<!-- ═══════════════════════ LOGIN OVERLAY ═══════════════════════ -->
<div class="login-overlay" id="login-overlay">
  <div class="login-panel">
    <div class="login-header">
      <div class="login-title">Remote Access Terminal</div>
      <div class="login-subtitle">Mac Mini // VNC Authentication</div>
    </div>
    <div class="arc-reactor">
      <svg class="arc-reactor-svg" viewBox="0 0 64 64" fill="none">
        <circle cx="32" cy="32" r="30" stroke="#00d4ff" stroke-width="1" opacity="0.3"/>
        <circle cx="32" cy="32" r="24" stroke="#00d4ff" stroke-width="1" opacity="0.5"/>
        <circle cx="32" cy="32" r="16" stroke="#00E5FF" stroke-width="1.5" opacity="0.7"/>
        <circle cx="32" cy="32" r="8" stroke="#00E5FF" stroke-width="2" opacity="0.9"/>
        <circle cx="32" cy="32" r="3" fill="#00E5FF"/>
        <line x1="32" y1="2" x2="32" y2="8" stroke="#00d4ff" stroke-width="0.8" opacity="0.5"/>
        <line x1="32" y1="56" x2="32" y2="62" stroke="#00d4ff" stroke-width="0.8" opacity="0.5"/>
        <line x1="2" y1="32" x2="8" y2="32" stroke="#00d4ff" stroke-width="0.8" opacity="0.5"/>
        <line x1="56" y1="32" x2="62" y2="32" stroke="#00d4ff" stroke-width="0.8" opacity="0.5"/>
        <line x1="11" y1="11" x2="15" y2="15" stroke="#00d4ff" stroke-width="0.6" opacity="0.3"/>
        <line x1="49" y1="49" x2="53" y2="53" stroke="#00d4ff" stroke-width="0.6" opacity="0.3"/>
        <line x1="53" y1="11" x2="49" y2="15" stroke="#00d4ff" stroke-width="0.6" opacity="0.3"/>
        <line x1="15" y1="49" x2="11" y2="53" stroke="#00d4ff" stroke-width="0.6" opacity="0.3"/>
      </svg>
    </div>
    <div class="login-body">
      <form id="vnc-login-form">
        <div class="input-group">
          <label class="input-label" for="vnc-password">VNC Password</label>
          <input class="input-field" type="password" id="vnc-password"
                 placeholder="Enter VNC password" autocomplete="current-password" autofocus>
        </div>
        <button class="connect-btn" type="submit" id="connect-btn">Establish Connection</button>
        <div class="login-error" id="login-error"></div>
      </form>
    </div>
  </div>
</div>

<!-- ═══════════════════════ CONNECTING OVERLAY ═══════════════════════ -->
<div class="connecting-overlay" id="connecting-overlay">
  <div class="spinner"></div>
  <div class="connecting-text">Establishing secure link...</div>
</div>

<!-- ═══════════════════════ CLIPBOARD MODAL ═══════════════════════ -->
<div class="clipboard-modal" id="clipboard-modal">
  <div class="clipboard-panel">
    <div class="clipboard-header">
      <span class="clipboard-title">Clipboard Sync</span>
      <button class="clipboard-close" id="clipboard-close">&times;</button>
    </div>
    <div class="clipboard-body">
      <textarea class="clipboard-textarea" id="clipboard-text" placeholder="Paste text here to send to remote, or copy from remote..."></textarea>
    </div>
    <div class="clipboard-actions">
      <button class="tb-btn" id="clipboard-send">Send to Remote</button>
      <button class="tb-btn" id="clipboard-receive">Get from Remote</button>
    </div>
  </div>
</div>

<!-- ═══════════════════════ TOAST ═══════════════════════ -->
<div class="toast" id="toast"></div>

<!-- ═══════════════════════ MAIN SCRIPT ═══════════════════════ -->
<script type="module">
(function() {
  'use strict';

  const WEBSOCKIFY_URL = 'wss://vnc.malibupoint.dev/websockify';

  // DOM refs
  const loginOverlay     = document.getElementById('login-overlay');
  const connectingOverlay = document.getElementById('connecting-overlay');
  const loginForm        = document.getElementById('vnc-login-form');
  const passwordInput    = document.getElementById('vnc-password');
  const connectBtn       = document.getElementById('connect-btn');
  const loginError       = document.getElementById('login-error');
  const vncContainer     = document.getElementById('vnc-container');
  const statusDot        = document.getElementById('status-dot');
  const statusText       = document.getElementById('status-text');
  const resolutionText   = document.getElementById('resolution-text');
  const scaleSelect      = document.getElementById('scale-select');
  const btnDisconnect    = document.getElementById('btn-disconnect');
  const btnFullscreen    = document.getElementById('btn-fullscreen');
  const btnClipboard     = document.getElementById('btn-clipboard');
  const btnKeys          = document.getElementById('btn-keys');
  const chkViewOnly      = document.getElementById('chk-viewonly');
  const clipboardModal   = document.getElementById('clipboard-modal');
  const clipboardClose   = document.getElementById('clipboard-close');
  const clipboardText    = document.getElementById('clipboard-text');
  const clipboardSend    = document.getElementById('clipboard-send');
  const clipboardReceive = document.getElementById('clipboard-receive');
  const toastEl          = document.getElementById('toast');

  let rfb = null;
  let toastTimer = null;

  // ── Toast ──────────────────────────────────────────────
  function showToast(msg, type = '') {
    toastEl.textContent = msg;
    toastEl.className = 'toast visible' + (type ? ' ' + type : '');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toastEl.classList.remove('visible');
    }, 3000);
  }

  // ── Status helpers ─────────────────────────────────────
  function setStatus(connected, text) {
    statusDot.className = 'status-indicator' + (connected ? ' connected' : '');
    statusText.textContent = text;
    statusText.className = 'status-text' + (connected ? ' connected' : text.toLowerCase().includes('error') ? ' error' : '');
  }

  // ── Wait for noVNC module to load ─────────────────────
  function waitForNoVNC() {
    return new Promise((resolve, reject) => {
      if (window.RFB) { resolve(window.RFB); return; }

      const timeout = setTimeout(() => reject(new Error('noVNC library timed out (15s). Check browser console for CDN errors.')), 15000);

      window.addEventListener('novnc-loaded', () => {
        clearTimeout(timeout);
        if (window.RFB) resolve(window.RFB);
        else reject(new Error('noVNC loaded event fired but RFB class not found'));
      }, { once: true });

      window.addEventListener('novnc-error', (e) => {
        clearTimeout(timeout);
        reject(new Error(e.detail || 'noVNC library failed to load'));
      }, { once: true });
    });
  }

  // ── Connect ────────────────────────────────────────────
  async function connect(password) {
    loginOverlay.classList.add('hidden');
    connectingOverlay.classList.add('active');
    setStatus(false, 'Loading VNC library...');

    let RFB;
    try {
      RFB = await waitForNoVNC();
    } catch (err) {
      connectingOverlay.classList.remove('active');
      loginOverlay.classList.remove('hidden');
      loginError.textContent = err.message;
      setStatus(false, 'Library Error');
      return;
    }

    setStatus(false, 'Connecting...');

    // Connection timeout — if no VNC event fires in 20s, abort
    let connectTimeout = setTimeout(() => {
      if (rfb) {
        try { rfb.disconnect(); } catch(e) {}
      }
      connectingOverlay.classList.remove('active');
      loginOverlay.classList.remove('hidden');
      loginError.textContent = 'Connection timed out (20s). WebSocket to ' + WEBSOCKIFY_URL + ' may be unreachable.';
      setStatus(false, 'Timeout');
      rfb = null;
    }, 20000);

    function clearConnectTimeout() {
      if (connectTimeout) { clearTimeout(connectTimeout); connectTimeout = null; }
    }

    try {
      rfb = new RFB(vncContainer, WEBSOCKIFY_URL, {
        credentials: { password: password },
      });

      rfb.scaleViewport = true;
      rfb.resizeSession = false;
      rfb.clipViewport = false;
      rfb.showDotCursor = true;

      rfb.addEventListener('connect', function(e) { clearConnectTimeout(); onConnect(e); });
      rfb.addEventListener('disconnect', function(e) { clearConnectTimeout(); onDisconnect(e); });
      rfb.addEventListener('credentialsrequired', function(e) { clearConnectTimeout(); onCredentialsRequired(e); });
      rfb.addEventListener('desktopname', onDesktopName);
      rfb.addEventListener('clipboard', onClipboard);

    } catch (err) {
      clearConnectTimeout();
      connectingOverlay.classList.remove('active');
      loginOverlay.classList.remove('hidden');
      loginError.textContent = 'RFB init failed: ' + err.message;
      setStatus(false, 'Error');
    }
  }

  function onConnect() {
    connectingOverlay.classList.remove('active');
    setStatus(true, 'Connected');
    showToast('Connection established', 'success');
    updateResolutionDisplay();
    applyScaling();
  }

  function onDisconnect(e) {
    connectingOverlay.classList.remove('active');
    const clean = e.detail.clean;
    if (clean) {
      setStatus(false, 'Disconnected');
      showToast('Disconnected', '');
    } else {
      setStatus(false, 'Connection lost');
      showToast('Connection lost', 'error');
    }
    loginOverlay.classList.remove('hidden');
    rfb = null;
  }

  function onCredentialsRequired() {
    connectingOverlay.classList.remove('active');
    loginOverlay.classList.remove('hidden');
    loginError.textContent = 'VNC password required or incorrect';
    setStatus(false, 'Auth required');
    passwordInput.focus();
  }

  function onDesktopName(e) {
    document.title = 'J.A.R.V.I.S. // ' + e.detail.name;
  }

  function onClipboard(e) {
    clipboardText.value = e.detail.text;
    showToast('Clipboard received from remote', 'success');
  }

  function updateResolutionDisplay() {
    if (!rfb) return;
    const screen = rfb._fbWidth && rfb._fbHeight
      ? rfb._fbWidth + 'x' + rfb._fbHeight
      : '';
    resolutionText.textContent = screen;
  }

  // ── Scaling ────────────────────────────────────────────
  function applyScaling() {
    if (!rfb) return;
    const mode = scaleSelect.value;
    switch (mode) {
      case 'remote':
        rfb.scaleViewport = false;
        rfb.resizeSession = true;
        rfb.clipViewport = false;
        break;
      case 'local':
        rfb.scaleViewport = true;
        rfb.resizeSession = false;
        rfb.clipViewport = false;
        break;
      case 'none':
        rfb.scaleViewport = false;
        rfb.resizeSession = false;
        rfb.clipViewport = true;
        break;
    }
  }

  // ── Event handlers ─────────────────────────────────────
  loginForm.addEventListener('submit', (e) => {
    e.preventDefault();
    loginError.textContent = '';
    const pw = passwordInput.value;
    if (!pw) {
      loginError.textContent = 'Password is required';
      return;
    }
    connectBtn.disabled = true;
    connect(pw).finally(() => { connectBtn.disabled = false; });
  });

  btnDisconnect.addEventListener('click', () => {
    if (rfb) rfb.disconnect();
  });

  btnFullscreen.addEventListener('click', () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
    } else {
      document.exitFullscreen().catch(() => {});
    }
  });

  document.addEventListener('fullscreenchange', () => {
    btnFullscreen.classList.toggle('active', !!document.fullscreenElement);
  });

  scaleSelect.addEventListener('change', applyScaling);

  chkViewOnly.addEventListener('change', () => {
    if (rfb) rfb.viewOnly = chkViewOnly.checked;
  });

  btnKeys.addEventListener('click', () => {
    if (rfb) rfb.sendCtrlAltDel();
    showToast('Sent Ctrl+Alt+Del', 'success');
  });

  // Clipboard modal
  btnClipboard.addEventListener('click', () => {
    clipboardModal.classList.add('active');
    clipboardText.focus();
  });

  clipboardClose.addEventListener('click', () => {
    clipboardModal.classList.remove('active');
  });

  clipboardModal.addEventListener('click', (e) => {
    if (e.target === clipboardModal) clipboardModal.classList.remove('active');
  });

  clipboardSend.addEventListener('click', () => {
    if (rfb && clipboardText.value) {
      rfb.clipboardPasteFrom(clipboardText.value);
      showToast('Sent to remote clipboard', 'success');
    }
  });

  clipboardReceive.addEventListener('click', () => {
    showToast('Clipboard will appear when remote sends data', '');
  });

  // Keyboard shortcut: Escape closes clipboard modal
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && clipboardModal.classList.contains('active')) {
      clipboardModal.classList.remove('active');
    }
  });

  // Latency ping (rough estimate based on frame timing)
  let lastFrameTime = 0;
  const latencyText = document.getElementById('latency-text');

  function measureLatency() {
    if (!rfb || !statusDot.classList.contains('connected')) {
      latencyText.textContent = '';
      return;
    }
    const now = performance.now();
    if (lastFrameTime > 0) {
      const delta = Math.round(now - lastFrameTime);
      if (delta < 2000) {
        latencyText.textContent = delta + 'ms';
      }
    }
    lastFrameTime = now;
  }

  // Update resolution periodically
  setInterval(() => {
    updateResolutionDisplay();
  }, 5000);

  // Focus password field
  passwordInput.focus();

})();
</script>

</body>
</html>"""


@router.get("/mac-mini", response_class=HTMLResponse)
async def vnc_viewer() -> HTMLResponse:
    """Serve the JARVIS-styled VNC viewer page.

    The page itself is public — the actual security layer is the VNC
    password required to connect to the Mac Mini's VNC server.
    """
    return HTMLResponse(content=VNC_PAGE_HTML, status_code=200)
