/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'jarvis-blue': '#00d4ff',
        'jarvis-cyan': '#00f0ff',
        'jarvis-gold': '#f0a500',
        'jarvis-dark': '#0a0a1a',
        'jarvis-darker': '#050510',
        // HUD palette
        'hud-red': '#ff3a3a',
        'hud-green': '#39ff14',
        'hud-amber': '#ffbf00',
        'hud-panel': 'rgba(0, 20, 40, 0.55)',
        'hud-panel-solid': '#001428',
      },
      fontFamily: {
        'sans': ['Rajdhani', 'sans-serif'],
        'display': ['Orbitron', 'sans-serif'],
        'mono': ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      animation: {
        'pulse-glow': 'pulseGlow 2s ease-in-out infinite',
        'spin-slow': 'spin 8s linear infinite',
        'gradient-border': 'gradientBorder 3s ease infinite',
        'scan-line': 'scanLine 4s linear infinite',
        'hud-boot': 'hudBoot 0.6s ease-out forwards',
        'hud-flicker': 'hudFlicker 0.15s ease-in-out',
        'data-stream': 'dataStream 2s linear infinite',
      },
      keyframes: {
        pulseGlow: {
          '0%, 100%': { boxShadow: '0 0 5px rgba(0, 212, 255, 0.3), 0 0 10px rgba(0, 212, 255, 0.2)' },
          '50%': { boxShadow: '0 0 15px rgba(0, 212, 255, 0.5), 0 0 30px rgba(0, 212, 255, 0.3)' },
        },
        gradientBorder: {
          '0%, 100%': { borderColor: '#00d4ff' },
          '50%': { borderColor: '#00f0ff' },
        },
        scanLine: {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100%)' },
        },
        hudBoot: {
          '0%': { opacity: '0', transform: 'translateY(8px) scale(0.97)' },
          '100%': { opacity: '1', transform: 'translateY(0) scale(1)' },
        },
        hudFlicker: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.7' },
        },
        dataStream: {
          '0%': { backgroundPosition: '0% 0%' },
          '100%': { backgroundPosition: '0% 100%' },
        },
      },
      boxShadow: {
        'jarvis': '0 0 15px rgba(0, 212, 255, 0.3)',
        'jarvis-lg': '0 0 30px rgba(0, 212, 255, 0.4), 0 0 60px rgba(0, 212, 255, 0.2)',
        'hud': '0 0 10px rgba(0, 212, 255, 0.15), inset 0 0 10px rgba(0, 212, 255, 0.05)',
        'hud-gold': '0 0 10px rgba(240, 165, 0, 0.15), inset 0 0 10px rgba(240, 165, 0, 0.05)',
      },
      backdropBlur: {
        'hud': '12px',
      },
    },
  },
  plugins: [],
};
