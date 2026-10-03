"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Lock } from "lucide-react";

import { BrandMark, useBrand } from "@/components/brand";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function LoginPage() {
  const router = useRouter();
  const brand = useBrand();
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [google, setGoogle] = useState(false);
  const [domain, setDomain] = useState("janus-soft.com");

  useEffect(() => {
    const code = new URLSearchParams(window.location.search).get("error");
    const messages: Record<string, string> = {
      domain: "Use a janus-soft.com Google account. Personal Gmail cannot sign in.",
      denied: "Google sign-in was cancelled.",
      locked: "Too many sign-in attempts. Try again in 15 minutes.",
      state: "That sign-in link expired. Start again.",
      google: "Google did not complete sign-in. Try again.",
    };
    if (code && messages[code]) setError(messages[code]);
    fetch("/api/admin/login/options")
      .then(async (response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (!data) return;
        setGoogle(Boolean(data.google));
        if (data.hosted_domain) setDomain(data.hosted_domain);
      })
      .catch(() => undefined);
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const response = await fetch("/api/admin/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        setError(data.detail || "Sign-in failed.");
        return;
      }
      router.push("/admin/dashboard");
    } catch {
      setError("The server did not answer. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <section
        className="relative hidden overflow-hidden bg-night text-white lg:block"
        style={{ backgroundImage: `url("${brand.hero_url}")`, backgroundSize: "cover", backgroundPosition: "75% center" }}
      >
        <div className="absolute inset-0 bg-gradient-to-r from-night via-night/80 to-transparent" aria-hidden="true" />
        <div className="relative flex h-full flex-col justify-between p-10">
          <div className="flex items-center gap-3">
            <BrandMark className="size-10" />
            <p className="font-serif text-xl">{brand.company_name}</p>
          </div>
          <div className="max-w-md">
            <p className="text-xs uppercase tracking-[0.22em] text-pine-soft">Recruiter desk</p>
            <h1 className="mt-3 font-serif text-4xl leading-tight">Match the right people to every opening.</h1>
            <p className="mt-4 text-sm leading-6 text-white/70">
              Import résumés, ask for candidates in plain words, and see exactly which posting lines each person covers.
            </p>
          </div>
          <p className="text-xs text-white/40">© {new Date().getFullYear()} {brand.company_name}</p>
        </div>
      </section>
      <section className="flex flex-col justify-center px-6 py-12">
        <div className="mx-auto w-full max-w-sm">
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <BrandMark className="size-10" />
            <p className="font-serif text-xl">{brand.company_name}</p>
          </div>
          <span className="inline-flex size-11 items-center justify-center rounded-xl bg-pine/10 text-pine-deep">
            <Lock className="size-5" />
          </span>
          <h2 className="mt-4 font-serif text-3xl">Sign in</h2>
          <p className="mt-1 text-sm text-ink/60">Recruiters only. Your session lasts until you log out or it expires.</p>
          {google && (
            <a
              href="/api/admin/login/google"
              className="mt-8 inline-flex h-11 items-center justify-center rounded-md bg-ink px-4 text-sm font-medium text-white hover:bg-ink/90"
            >
              Sign in with Google
            </a>
          )}
          {google && <p className="mt-2 text-xs text-ink/55">Use your @{domain} Workspace account. That sign-in can also read the Drive folders you already have access to.</p>}
          <form onSubmit={onSubmit} className={`flex flex-col gap-3 ${google ? "mt-6" : "mt-8"}`}>
            {google && <p className="text-xs uppercase tracking-wide text-ink/45">Or use the break-glass password</p>}
            <Label htmlFor="password">Password</Label>
            <Input id="password" type="password" autoFocus autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} />
            {error && (
              <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800" role="alert">
                {error}
              </p>
            )}
            <Button type="submit" size="lg" disabled={busy || !password} className="mt-2">
              {busy ? "Signing in…" : "Sign in"}
            </Button>
          </form>
          <Link href="/chat" className="mt-8 inline-flex items-center gap-1.5 text-sm text-ink/60 hover:text-pine-deep">
            <ArrowLeft className="size-4" /> Back to the careers page
          </Link>
        </div>
      </section>
    </main>
  );
}
