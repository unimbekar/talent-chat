"use client";

import { useEffect } from "react";
import { RefreshCw, WifiOff } from "lucide-react";

import { applyUpdate, startPwa, usePwa } from "@/lib/pwa";

export function AppShell() {
  const { updateReady, online } = usePwa();

  useEffect(() => {
    startPwa();
  }, []);

  return (
    <div className="pointer-events-none fixed inset-x-0 top-[calc(env(safe-area-inset-top)+4.25rem)] z-[60] lg:top-[calc(env(safe-area-inset-top)+6rem)] flex flex-col items-center gap-2 px-3">
      {!online && (
        <p role="status" className="pointer-events-auto inline-flex animate-fade-up items-center gap-2 rounded-full bg-amber-100 px-4 py-2 text-xs font-medium text-amber-900 shadow-lift ring-1 ring-amber-300">
          <WifiOff className="size-3.5" /> Offline. Changes and searches wait for a connection.
        </p>
      )}
      {updateReady && (
        <div role="status" className="pointer-events-auto inline-flex animate-fade-up items-center gap-3 rounded-full bg-night py-2 pl-4 pr-2 text-xs text-white shadow-lift ring-1 ring-white/10">
          A new version of the desk is ready.
          <button type="button" onClick={applyUpdate} className="inline-flex items-center gap-1.5 rounded-full bg-pine px-3 py-1.5 font-medium text-white">
            <RefreshCw className="size-3.5" /> Update
          </button>
        </div>
      )}
    </div>
  );
}
