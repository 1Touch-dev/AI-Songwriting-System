import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Obsidian Studio Design System
        background: '#0e0e0e',
        surface: '#161616',
        'surface-2': '#1e1e1e',
        'surface-3': '#2a2a2a',
        primary: '#8ff5ff',      // neon cyan
        'primary-dim': '#4dd9e8',
        secondary: '#c3f400',    // cyber lime
        'secondary-dim': '#9bc200',
        tertiary: '#d277ff',     // purple
        'tertiary-dim': '#a855cc',
        'text-primary': '#f0f0f0',
        'text-secondary': '#a0a0a0',
        'text-muted': '#606060',
        'border-subtle': '#2a2a2a',
        'glass': 'rgba(255,255,255,0.04)',
        'glass-hover': 'rgba(255,255,255,0.07)',
        error: '#ff4757',
        warning: '#ffa502',
        success: '#2ed573',
      },
      fontFamily: {
        display: ['Space Grotesk', 'sans-serif'],
        body: ['Inter', 'sans-serif'],
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
        'gradient-noise': "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.03'/%3E%3C/svg%3E\")",
        'cyan-glow': 'radial-gradient(ellipse at 50% 0%, rgba(143,245,255,0.15) 0%, transparent 60%)',
        'lime-glow': 'radial-gradient(ellipse at 100% 100%, rgba(195,244,0,0.1) 0%, transparent 50%)',
      },
      boxShadow: {
        'glow-cyan': '0 0 20px rgba(143,245,255,0.25)',
        'glow-lime': '0 0 20px rgba(195,244,0,0.2)',
        'glow-purple': '0 0 20px rgba(210,119,255,0.2)',
        'glass': '0 4px 24px rgba(0,0,0,0.4)',
        'glass-lg': '0 8px 48px rgba(0,0,0,0.6)',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4,0,0.6,1) infinite',
        'spin-slow': 'spin 3s linear infinite',
        'fade-in': 'fadeIn 0.3s ease-out',
        'slide-up': 'slideUp 0.4s ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(12px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      backdropBlur: {
        xs: '2px',
      },
    },
  },
  plugins: [],
}

export default config
