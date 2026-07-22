/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef4ff",
          100: "#d9e6ff",
          500: "#3b6ef6",
          600: "#2f5ae0",
          700: "#2547b8",
        },
      },
    },
  },
  plugins: [],
};
