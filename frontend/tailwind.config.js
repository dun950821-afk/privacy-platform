/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: '#2B5AED',
        'primary-light': '#5B7DF2',
        'primary-dark': '#1F47C4',
        secondary: '#6B7A99',
        success: '#18A058',
        warning: '#F0A020',
        danger: '#D03050',
        info: '#2080F0',
        bg: {
          page: '#F7F8FA',
          card: '#FFFFFF',
        },
        text: {
          primary: '#1F2329',
          regular: '#646A73',
          secondary: '#8F959E',
          placeholder: '#C0C4CC',
        },
        border: {
          base: '#DEE0E3',
          light: '#E8EAEC',
          lighter: '#F0F1F3',
        }
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'PingFang SC', 'Microsoft YaHei', 'sans-serif'],
      },
      borderRadius: {
        'sm': '4px',
        'md': '6px',
        'lg': '8px',
      },
    },
  },
  plugins: [],
  corePlugins: {
    preflight: false,  // 避免与Element Plus冲突
  },
}
