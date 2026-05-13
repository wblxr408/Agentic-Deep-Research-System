/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Xiaomi Orange - primary accent
        xm: {
          50:  '#fff7f0',
          100: '#ffeedd',
          200: '#ffdabb',
          300: '#ffcb99',
          400: '#ffaa55',
          500: '#ff8c00',  // Main orange
          600: '#e67300',
          700: '#cc5500',
          800: '#993d00',
          900: '#662600',
        },
        // Neutral grays for Xiaomi style
        xmgray: {
          50:  '#fafafa',
          100: '#f5f5f5',
          200: '#eeeeee',
          300: '#e0e0e0',
          400: '#bdbdbd',
          500: '#9e9e9e',
          600: '#757575',
          700: '#616161',
          800: '#424242',
          900: '#212121',
        },
        // Primary for backward compat
        primary: {
          50: '#fff7f0',
          100: '#ffeedd',
          200: '#ffdabb',
          300: '#ffcb99',
          400: '#ffaa55',
          500: '#ff8c00',
          600: '#e67300',
          700: '#cc5500',
          800: '#993d00',
          900: '#662600',
        },
      },
      fontFamily: {
        sans: ['"Xiaomi Simple"', 'Inter', 'PingFang SC', 'Microsoft YaHei', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'Consolas', 'monospace'],
        display: ['"Xiaomi Display"', 'Inter', 'PingFang SC', 'system-ui', 'sans-serif'],
      },
      spacing: {
        // Xiaomi uses generous spacing
        '18': '4.5rem',
        '22': '5.5rem',
        '30': '7.5rem',
      },
      borderRadius: {
        'xl': '1rem',
        '2xl': '1.5rem',
        '3xl': '2rem',
      },
      boxShadow: {
        // Xiaomi-style subtle shadows
        'xm': '0 2px 8px rgba(0, 0, 0, 0.06)',
        'xm-md': '0 4px 16px rgba(0, 0, 0, 0.08)',
        'xm-lg': '0 8px 32px rgba(0, 0, 0, 0.10)',
        'xm-hover': '0 8px 24px rgba(0, 0, 0, 0.12)',
        'xm-card': '0 1px 3px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.06)',
      },
      transitionDuration: {
        '250': '250ms',
        '350': '350ms',
      },
      animation: {
        'fade-up': 'fadeUp 0.5s ease-out',
        'fade-in': 'fadeIn 0.3s ease-out',
        'slide-right': 'slideRight 0.4s ease-out',
        'pulse-slow': 'pulse 3s ease-in-out infinite',
      },
      keyframes: {
        fadeUp: {
          '0%': { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideRight: {
          '0%': { opacity: '0', transform: 'translateX(-20px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
      },
    },
  },
  plugins: [],
}
