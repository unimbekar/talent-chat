"use client";

import { Bell, BellOff, BellRing } from "lucide-react";

import { disablePush, enablePush, usePush } from "@/lib/push";

const HINTS: Partial<Record<string, string>> = {
  "needs-install": "On iPhone, add the desk to the Home Screen first, then turn alerts on from the app.",
  denied: "Notifications are blocked for this site. Allow them in the browser or phone settings, then come back.",
  unsupported: "This browser cannot show alerts. Use Chrome on Android or the Home Screen app on iPhone.",
};

export function AlertsRow() {
  const { status, busy, error } = usePush();
  if (status === "loading") return null;
  const hint = HINTS[status];
  if (hint) {
    return (
      <p className="flex items-center gap-3 rounded-2xl border border-line bg-card px-4 py-3 text-sm text-ink/70">
        <BellOff className="size-5 shrink-0 text-ink/55" />
        {hint}
      </p>
    );
  }
  const on = status === "on";
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      disabled={busy}
      onClick={() => (on ? disablePush() : enablePush())}
      className="flex items-center gap-3 rounded-2xl border border-line bg-card px-4 py-3 text-left text-sm text-ink/80 active:scale-[0.99] disabled:opacity-60"
    >
      {on ? <BellRing className="size-5 text-pine" /> : <Bell className="size-5 text-ink/55" />}
      <span className="flex-1">
        Alerts for new applications
        {error && <span className="block text-xs text-red-700">{error}</span>}
      </span>
      <span className={`relative h-6 w-10 rounded-full transition ${on ? "bg-pine" : "bg-ink/20"}`}>
        <span className={`absolute top-0.5 size-5 rounded-full bg-white shadow transition-all ${on ? "left-[1.125rem]" : "left-0.5"}`} />
      </span>
    </button>
  );
}

export function AlertsButton() {
  const { status, busy } = usePush();
  if (status !== "on" && status !== "off") return null;
  const on = status === "on";
  return (
    <button
      type="button"
      disabled={busy}
      onClick={() => (on ? disablePush() : enablePush())}
      aria-pressed={on}
      title={on ? "Alerts for new applications are on. Click to turn them off." : "Get an alert for each new application"}
      className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition hover:bg-white/5 disabled:opacity-60 ${
        on ? "text-pine-soft" : "text-white/60 hover:text-white"
      }`}
    >
      {on ? <BellRing className="size-4" /> : <Bell className="size-4" />}
      Alerts
    </button>
  );
}
