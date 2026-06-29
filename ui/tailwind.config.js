export default {
  content: [
    "./index.html",
    "./src/**/*.{js,jsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: '#3b82f6',
        secondary: '#1e293b',
      },
      animation: {
        fadeIn: 'fadeIn 0.3s ease-in',
        bounce: 'bounce 1.4s infinite ease-in-out',
      }
    },
  },
  plugins: [],
}