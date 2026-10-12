"use client";

/** Anonymous careers-site visit counting. A random id in local storage stands for one browser. */

const VISITOR_KEY = "janus-visitor";
const CAMPAIGN_KEY = "janus-campaign";
export const DESK_BROWSER_KEY = "janus-desk-browser";

type Kind = "page" | "posting" | "apply";

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function visitorId(store: Storage): string {
  let id = store.getItem(VISITOR_KEY);
  if (!id || !/^[0-9a-f-]{36}$/i.test(id)) {
    id = crypto.randomUUID();
    store.setItem(VISITOR_KEY, id);
  }
  return id;
}

function optedOut(): boolean {
  const nav = navigator as Navigator & { globalPrivacyControl?: boolean };
  return nav.globalPrivacyControl === true || nav.doNotTrack === "1";
}

/** utm_source from the landing link, kept for the rest of the tab so later pages credit the same source. */
function campaign(): string | null {
  try {
    const tag = new URLSearchParams(window.location.search).get("utm_source");
    if (tag) sessionStorage.setItem(CAMPAIGN_KEY, tag.slice(0, 40));
    return sessionStorage.getItem(CAMPAIGN_KEY);
  } catch {
    return null;
  }
}

function referrer(): string | null {
  try {
    const value = document.referrer;
    if (!value || new URL(value).host === window.location.host) return null;
    return value.slice(0, 1000);
  } catch {
    return null;
  }
}

export function trackVisit(kind: Kind, path: string): void {
  if (typeof window === "undefined" || typeof crypto?.randomUUID !== "function") return;
  const store = storage();
  // Desk staff checking the careers page should not inflate the numbers.
  if (!store || store.getItem(DESK_BROWSER_KEY) === "1" || optedOut()) return;
  const body = JSON.stringify({ visitor: visitorId(store), kind, path, referrer: referrer(), campaign: campaign() });
  fetch("/api/public/visit", { method: "POST", headers: { "Content-Type": "application/json" }, body, keepalive: true }).catch(
    () => undefined,
  );
}

export function markDeskBrowser(): void {
  storage()?.setItem(DESK_BROWSER_KEY, "1");
}
