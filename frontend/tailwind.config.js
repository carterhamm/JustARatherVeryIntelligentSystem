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
      },
      fontFamily: {
        'sans': ['Rajdhani', 'sans-serif'],
        'display': ['Orbitron', 'sans-serif'],
      },
      animation: {
        'pulse-glow': 'pulseGlow 2s ease-in-out infinite',
        'spin-slow': 'spin 8s linear infinite',
        'gradient-border': 'gradientBorder 3s ease infinite',
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
      },
      boxShadow: {
        'jarvis': '0 0 15px rgba(0, 212, 255, 0.3)',
        'jarvis-lg': '0 0 30px rgba(0, 212, 255, 0.4), 0 0 60px rgba(0, 212, 255, 0.2)',
      },
    },
  },
  plugins: [],
};
