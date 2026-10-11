"use client";

import { useEffect, useSyncExternalStore } from "react";

import { standalone } from "@/lib/pwa";

export type PushStatus = "loading" | "unsupported" | "needs-install" | "denied" | "off" | "on";

type PushState = { status: PushStatus; busy: boolean; error: string };

let state: PushState = { status: "loading", busy: false, error: "" };
const listeners = new Set<() => void>();
const SERVER_STATE = state;

function set(next: Partial<PushState>) {
  state = { ...state, ...next };
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function supported(): boolean {
  return typeof window !== "undefined" && window.isSecureContext && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

function ios(): boolean {
  return /iphone|ipad|ipod/i.test(navigator.userAgent);
}

function keyBytes(base64: string): Uint8Array<ArrayBuffer> {
  const padded = (base64 + "=".repeat((4 - (base64.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(padded);
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let index = 0; index < raw.length; index += 1) bytes[index] = raw.charCodeAt(index);
  return bytes;
}

async function post(path: string, body?: unknown): Promise<Response> {
  return fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

let checked = false;

export async function refreshPush() {
  if (typeof window === "undefined") return;
  if (!supported()) {
    // iPhone Safari offers push only to an app added to the Home Screen.
    set({ status: ios() && !standalone() ? "needs-install" : "unsupported" });
    return;
  }
  if (Notification.permission === "denied") {
    set({ status: "denied" });
    return;
  }
  const registration = await navigator.serviceWorker.ready;
  const existing = await registration.pushManager.getSubscription();
  set({ status: existing && Notification.permission === "granted" ? "on" : "off" });
}

export function usePush(): PushState {
  useEffect(() => {
    if (checked) return;
    checked = true;
    refreshPush().catch(() => set({ status: "unsupported" }));
  }, []);
  return useSyncExternalStore(subscribe, () => state, () => SERVER_STATE);
}

export async function enablePush(): Promise<boolean> {
  if (state.busy) return false;
  set({ busy: true, error: "" });
  try {
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      set({ status: permission === "denied" ? "denied" : "off" });
      return false;
    }
    const keyResponse = await fetch("/api/admin/push/key");
    if (!keyResponse.ok) throw new Error("The desk did not return a push key.");
    const { public_key } = (await keyResponse.json()) as { public_key: string };
    const registration = await navigator.serviceWorker.ready;
    let subscription = await registration.pushManager.getSubscription();
    if (subscription) {
      const current = subscription.options.applicationServerKey;
      const wanted = keyBytes(public_key);
      const same = current && new Uint8Array(current).every((value, index) => value === wanted[index]);
      if (!same) {
        await subscription.unsubscribe();
        subscription = null;
      }
    }
    subscription ??= await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(public_key) });
    const saved = await post("/api/admin/push/subscribe", subscription.toJSON());
    if (!saved.ok) throw new Error("The desk did not save this device.");
    set({ status: "on" });
    await post("/api/admin/push/test");
    return true;
  } catch (error) {
    set({ error: error instanceof Error ? error.message : "Alerts could not be turned on." });
    return false;
  } finally {
    set({ busy: false });
  }
}

export async function disablePush(): Promise<void> {
  if (state.busy) return;
  set({ busy: true, error: "" });
  try {
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    if (subscription) {
      await post("/api/admin/push/unsubscribe", { endpoint: subscription.endpoint }).catch(() => undefined);
      await subscription.unsubscribe();
    }
    set({ status: "off" });
  } finally {
    set({ busy: false });
  }
}
