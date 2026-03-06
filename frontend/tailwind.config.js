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
        'hud-red': '#ff3a3a',
        'hud-green': '#39ff14',
        'hud-amber': '#ffbf00',
      },
      fontFamily: {
        'sans': ['Rajdhani', 'sans-serif'],
        'display': ['Orbitron', 'sans-serif'],
        'mono': ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      borderRadius: {
        'glass': '20px',
        'capsule': '50px',
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
        'gradient-conic': 'conic-gradient(from 180deg at 50% 50%, var(--tw-gradient-stops))',
        'hud-grid': 'linear-gradient(rgba(0,212,255,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(0,212,255,0.04) 1px, transparent 1px)',
      },
      animation: {
        'pulse-glow': 'pulseGlow 2s ease-in-out infinite',
        'spin-slow': 'spin 8s linear infinite',
        'spin-reverse': 'spinReverse 12s linear infinite',
        'scan-line': 'scanLine 4s linear infinite',
        'hud-boot': 'hudBoot 0.6s ease-out forwards',
        'float-in': 'floatIn 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'float-in-up': 'floatInUp 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'fade-in': 'fadeIn 0.3s ease-out forwards',
        'slide-in-left': 'slideInLeft 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'slide-in-right': 'slideInRight 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'slide-in-up': 'slideInUp 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'glow-pulse': 'glowPulse 3s ease-in-out infinite',
        'arc-pulse': 'arcPulse 2s ease-in-out infinite',
        'arc-spin': 'arcSpin 12s linear infinite',
        'dock-bounce': 'dockBounce 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)',
      },
      keyframes: {
        pulseGlow: {
          '0%, 100%': { boxShadow: '0 0 5px rgba(0, 212, 255, 0.3), 0 0 10px rgba(0, 212, 255, 0.2)' },
          '50%': { boxShadow: '0 0 15px rgba(0, 212, 255, 0.5), 0 0 30px rgba(0, 212, 255, 0.3)' },
        },
        scanLine: {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100%)' },
        },
        hudBoot: {
          '0%': { opacity: '0', transform: 'scale(0.95)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        floatIn: {
          '0%': { opacity: '0', transform: 'translateY(12px) scale(0.97)' },
          '100%': { opacity: '1', transform: 'translateY(0) scale(1)' },
        },
        floatInUp: {
          '0%': { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideInLeft: {
          '0%': { opacity: '0', transform: 'translateX(-30px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        slideInRight: {
          '0%': { opacity: '0', transform: 'translateX(30px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        slideInUp: {
          '0%': { opacity: '0', transform: 'translateY(16px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        glowPulse: {
          '0%, 100%': { boxShadow: '0 0 20px rgba(0, 212, 255, 0.15)' },
          '50%': { boxShadow: '0 0 40px rgba(0, 212, 255, 0.3), 0 0 80px rgba(0, 212, 255, 0.1)' },
        },
        arcPulse: {
          '0%, 100%': { boxShadow: '0 0 30px rgba(0,240,255,0.8), 0 0 60px rgba(0,212,255,0.4)' },
          '50%': { boxShadow: '0 0 40px rgba(0,240,255,1), 0 0 80px rgba(0,212,255,0.6)' },
        },
        arcSpin: {
          from: { transform: 'translate(-50%, -50%) rotate(0deg)' },
          to: { transform: 'translate(-50%, -50%) rotate(360deg)' },
        },
        spinReverse: {
          '0%': { transform: 'rotate(360deg)' },
          '100%': { transform: 'rotate(0deg)' },
        },
        dockBounce: {
          '0%': { transform: 'scale(1)' },
          '40%': { transform: 'scale(1.15)' },
          '100%': { transform: 'scale(1)' },
        },
      },
      boxShadow: {
        'glass': '0 8px 32px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.04)',
        'glass-lg': '0 16px 48px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.05)',
        'glass-glow': '0 8px 32px rgba(0, 0, 0, 0.4), 0 0 20px rgba(0, 212, 255, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.04)',
        'glow-cyan': '0 0 15px rgba(0, 212, 255, 0.3)',
        'glow-gold': '0 0 15px rgba(240, 165, 0, 0.3)',
        'glow-red': '0 0 15px rgba(255, 58, 58, 0.3)',
      },
    },
  },
  plugins: [],
};
