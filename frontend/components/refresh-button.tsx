"use client";

import { useTransition } from "react";
import { useRouter } from "next/navigation";

export function RefreshButton() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  return (
    <button className="secondary" disabled={pending} onClick={() => startTransition(() => router.refresh())}>
      {pending ? "Обновление…" : "Обновить"}
    </button>
  );
}
