import type { Metadata, Viewport } from "next";
import "./globals.css";
import { SessionProvider } from "@/lib/session";

export const metadata: Metadata = {
  title: "ФСП Скаут — работодатели находят вас сами",
  description: "Подбор ИТ-специалистов по подтверждённому уровню: тестирование, категории и достижения Федерации спортивного программирования.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#2D1451" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body>
        <SessionProvider>{children}</SessionProvider>
      </body>
    </html>
  );
}
