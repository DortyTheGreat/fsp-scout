import type { Config } from "tailwindcss";

// Палитра — из официального шаблона презентаций ФСП (тема pptx)
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#1C1D22",
        plum: { DEFAULT: "#2D1451", 700: "#3B1D66", 600: "#520977", 100: "#EDE9F6", 50: "#F6F4FA" },
        signal: { DEFAULT: "#FF0053", 600: "#E0004A", 100: "#FFD6E3", 50: "#FFF0F5" },
        lavender: { DEFAULT: "#8A83D1", 200: "#D3D0EE" },
        mist: { DEFAULT: "#E4EAE9", 50: "#F3F6F5", 300: "#C9D2D0" },
        ok: "#13795B",
        warn: "#A15C00",
      },
      fontFamily: {
        sans: ["Montserrat", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      fontSize: {
        "2xs": ["0.75rem", { lineHeight: "1rem" }],
      },
    },
  },
  plugins: [],
};
export default config;
