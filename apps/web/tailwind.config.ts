import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: "#1d4ed8",
      },
    },
  },
  plugins: [],
} satisfies Config;
