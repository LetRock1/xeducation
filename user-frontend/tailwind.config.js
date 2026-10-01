/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html","./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        navy:  { DEFAULT:'#0B1426', light:'#1E3A5F', deep:'#060D1A' },
        ember: { DEFAULT:'#F97316' },
        gold:  { DEFAULT:'#FFB703' },
        sky:   { accent:'#38BDF8' },
      },
      fontFamily: {
        display: ['Sora','sans-serif'],
        body:    ['DM Sans','sans-serif'],
      },
    },
  },
  plugins: [],
}
