"use client";

export default function ErrorPage({ reset }: { reset: () => void }) {
  return <main className="container state" role="alert">
    <h1>Не удалось открыть каталог</h1>
    <p>Попробуйте ещё раз.</p>
    <button onClick={reset}>Повторить</button>
  </main>;
}
