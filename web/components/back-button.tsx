"use client";

import { useRouter } from "next/navigation";

export function BackButton({ fallback, label = "Back" }: { fallback: string; label?: string }) {
  const router = useRouter();
  return (
    <button
      type="button"
      onClick={() => {
        if (window.history.length > 1) router.back();
        else router.push(fallback);
      }}
      className="inline-flex items-center gap-1 text-sm text-pine hover:underline"
    >
      <span aria-hidden="true">←</span> {label}
    </button>
  );
}
