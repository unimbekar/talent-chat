"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { KeyRound } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useDesk } from "@/lib/desk";

export default function PasswordPage() {
  const router = useRouter();
  const desk = useDesk();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch("/api/admin/overview").then((response) => {
      if (response.status === 401) router.push("/admin/login");
    });
  }, [router]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setSaved(false);
    if (next.length < 12) {
      setError("Use at least 12 characters.");
      return;
    }
    if (next !== confirm) {
      setError("The new password and the confirmation do not match.");
      return;
    }
    setBusy(true);
    try {
      const response = await fetch("/api/admin/password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_password: current, new_password: next }),
      });
      if (response.status === 401) {
        router.push("/admin/login");
        return;
      }
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        const detail = data.detail;
        setError(typeof detail === "string" ? detail : "The password was not changed.");
        return;
      }
      setCurrent("");
      setNext("");
      setConfirm("");
      setSaved(true);
    } catch {
      setError("The server did not answer. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-lg">
      <p className="text-xs uppercase tracking-[0.18em] text-pine-deep">Desk</p>
      <h1 className="mt-1 font-serif text-3xl">Change password</h1>
      <p className="mt-2 text-sm leading-6 text-ink/65">
        {desk.email ? `This password belongs to ${desk.email}.` : "This password belongs to your desk account."} The careers site does not use it. Sign in again with the new password on any other browser.
      </p>
      <form onSubmit={onSubmit} className="mt-6 flex flex-col gap-4 rounded-2xl border border-line bg-white p-5 shadow-sm">
        <span className="inline-flex size-10 items-center justify-center rounded-xl bg-pine/10 text-pine-deep">
          <KeyRound className="size-5" />
        </span>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="current">Current password</Label>
          <Input id="current" type="password" autoComplete="current-password" value={current} onChange={(event) => setCurrent(event.target.value)} required />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="next">New password</Label>
          <Input id="next" type="password" autoComplete="new-password" value={next} onChange={(event) => setNext(event.target.value)} required minLength={12} />
          <p className="text-xs text-ink/50">At least 12 characters.</p>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="confirm">Confirm new password</Label>
          <Input id="confirm" type="password" autoComplete="new-password" value={confirm} onChange={(event) => setConfirm(event.target.value)} required />
        </div>
        {error && (
          <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800" role="alert">
            {error}
          </p>
        )}
        {saved && (
          <p className="rounded-lg border border-pine/20 bg-pine/10 px-3 py-2 text-sm text-pine-deep" role="status">
            Password changed. Use it the next time you sign in.
          </p>
        )}
        <Button type="submit" disabled={busy || !current || !next || !confirm}>
          {busy ? "Saving…" : "Change password"}
        </Button>
      </form>
    </div>
  );
}
