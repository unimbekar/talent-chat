"use client";

import { useSyncExternalStore } from "react";

type InstallPrompt = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: "accepted" | "dismissed" }> };

type PwaState = {
  installPrompt: InstallPrompt | null;
  installed: boolean;
  ios: boolean;
  updateReady: ServiceWorker | null;
  online: boolean;
};

let state: PwaState = { installPrompt: null, installed: false, ios: false, updateReady: null, online: true };
const listeners = new Set<() => void>();

function set(next: Partial<PwaState>) {
  state = { ...state, ...next };
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

const SERVER_STATE = state;

export function usePwa(): PwaState {
  return useSyncExternalStore(subscribe, () => state, () => SERVER_STATE);
}

export function standalone(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(display-mode: standalone)").matches || (navigator as { standalone?: boolean }).standalone === true;
}

let started = false;

export function startPwa() {
  if (started || typeof window === "undefined") return;
  started = true;
  set({
    installed: standalone(),
    ios: /iphone|ipad|ipod/i.test(navigator.userAgent) && !/crios|fxios/i.test(navigator.userAgent),
    online: navigator.onLine,
  });
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    set({ installPrompt: event as InstallPrompt });
  });
  window.addEventListener("appinstalled", () => set({ installPrompt: null, installed: true }));
  window.addEventListener("online", () => set({ online: true }));
  window.addEventListener("offline", () => set({ online: false }));

  if (!("serviceWorker" in navigator) || !window.isSecureContext) return;
  let reloading = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (reloading) return;
    reloading = true;
    window.location.reload();
  });
  navigator.serviceWorker
    .register("/sw.js", { scope: "/" })
    .then((registration) => {
      const offer = (worker: ServiceWorker | null) => {
        if (worker && navigator.serviceWorker.controller) set({ updateReady: worker });
      };
      offer(registration.waiting);
      registration.addEventListener("updatefound", () => {
        const worker = registration.installing;
        worker?.addEventListener("statechange", () => {
          if (worker.state === "installed") offer(worker);
        });
      });
      // A phone app can stay open for days; look for a new version when it comes back to the front.
      document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") registration.update().catch(() => {});
      });
    })
    .catch(() => {});
}

export async function install(): Promise<boolean> {
  const prompt = state.installPrompt;
  if (!prompt) return false;
  await prompt.prompt();
  const choice = await prompt.userChoice;
  set({ installPrompt: null, installed: choice.outcome === "accepted" || state.installed });
  return choice.outcome === "accepted";
}

export function applyUpdate() {
  state.updateReady?.postMessage("SKIP_WAITING");
}
