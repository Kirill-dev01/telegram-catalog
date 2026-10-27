import type { Metadata, Viewport } from "next";
import { TelegramApp } from "@/components/telegram-app";
import "./globals.css";

export const metadata: Metadata = {
  title: "Каталог товаров",
  description: "Каталог товаров в браузере и Telegram",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body>
        <TelegramApp />
        <a className="skip-link" href="#catalog">К каталогу</a>
        {children}
      </body>
    </html>
  );
}
