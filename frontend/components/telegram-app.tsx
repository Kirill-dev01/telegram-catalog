"use client";

import Script from "next/script";

declare global {
  interface Window {
    Telegram?: { WebApp?: { ready: () => void; expand: () => void } };
  }
}

export function TelegramApp() {
  return (
    <Script
      src="https://telegram.org/js/telegram-web-app.js"
      strategy="afterInteractive"
      onReady={() => {
        window.Telegram?.WebApp?.ready();
        window.Telegram?.WebApp?.expand();
      }}
    />
  );
}
