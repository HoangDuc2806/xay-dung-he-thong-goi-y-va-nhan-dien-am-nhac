import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { 950: "#101014", 900: "#17171d", 800: "#202027", 700: "#2b2b35", 600: "#3d3c49", 500: "#696776" },
        mist: { 100: "#f4f1fa", 200: "#d8d4e2", 300: "#b9b4c5", 400: "#a29bad" },
        lime: { 300: "#ded2ff", 400: "#c2adff", 500: "#a68af5", 600: "#8767d5", 700: "#654aa5" },
      },
      fontFamily: {
        sans: ['"Segoe UI"', "system-ui", "-apple-system", "Roboto", "sans-serif"],
      },
      boxShadow: {
        card: "0 12px 32px -20px rgba(0,0,0,.7)",
      },
    },
  },
  plugins: [],
};
export default config;
