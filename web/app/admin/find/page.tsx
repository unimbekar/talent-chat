"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

type Person = {
  id: string;
  full_name: string | null;
  email: string | null;
  location: string | null;
  titles: string[];
  skills: string[];
};

type Answer = {
  answer: string;
  categories: string[];
  candidates: Person[];
};

const STORAGE_KEY = "talent-find-results";

export default function FindPage() {
  const router = useRouter();
  const [draft, setDraft] = useState("Show me all Software Testers.");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Answer | null>(null);
  const [copied, setCopied] = useState("");
  const [restored, setRestored] = useState(false);

  useEffect(() => {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (raw) {
      try {
        const saved = JSON.parse(raw) as { draft?: string; result?: Answer | null };
        if (saved.draft) setDraft(saved.draft);
        if (saved.result) setResult(saved.result);
      } catch {
        sessionStorage.removeItem(STORAGE_KEY);
      }
    }
    setRestored(true);
  }, []);

  useEffect(() => {
    if (!restored) return;
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ draft, result }));
  }, [draft, result, restored]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const message = draft.trim();
    if (!message || busy) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/admin/candidates/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      if (response.status === 401) {
        router.push("/admin/login");
        return;
      }
      const data = await response.json().catch(() => null);
      if (!response.ok || !data || !Array.isArray(data.candidates)) {
        setError(data?.detail || "The search did not complete. The previous list is still here.");
        return;
      }
      setResult(data);
    } catch {
      setError("The search did not complete. The previous list is still here.");
    } finally {
      setBusy(false);
    }
  }

  function copyText(value: string, label: string) {
    const area = document.createElement("textarea");
    area.value = value;
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    area.remove();
    if (navigator.clipboard?.writeText) {
      void navigator.clipboard.writeText(value).catch(() => undefined);
    }
    setCopied(label);
  }

  const emails = (result?.candidates || []).map((person) => person.email).filter((email): email is string => Boolean(email));

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="font-serif text-3xl">Find candidates</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink/70">
          Ask for a profession, such as Software Testers, Cybersecurity Engineers, or people with machine learning experience.
          Emails stay on this desk so you can copy them. Nothing is sent.
        </p>
      </div>
      <form onSubmit={onSubmit} className="flex flex-col gap-2">
        <label className="text-sm" htmlFor="ask">
          Question
        </label>
        <Textarea id="ask" value={draft} onChange={(event) => setDraft(event.target.value)} rows={3} />
        <Button type="submit" disabled={busy} className="w-full sm:w-auto sm:self-end">
          {busy ? "Searching…" : "Find candidates"}
        </Button>
      </form>
      {error && <p className="text-sm text-red-700">{error}</p>}
      {result && (
        <section className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm">{result.answer}</p>
            {emails.length > 0 && (
              <Button type="button" variant="outline" onClick={() => copyText(emails.join("\n"), "all")}>
                {copied === "all" ? "Copied" : "Copy all emails"}
              </Button>
            )}
          </div>
          <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-card">
            {result.candidates.length === 0 && <li className="px-4 py-8 text-sm text-ink/70">No one is filed in that category yet.</li>}
            {result.candidates.map((person) => (
              <li key={person.id} className="flex flex-col gap-2 px-4 py-3">
                <div>
                  <Link href={`/admin/match?id=${person.id}`} className="font-medium hover:text-pine">
                    {person.full_name || "Unnamed résumé"}
                  </Link>
                  <p className="text-xs text-ink/60">{[person.titles.join(", "), person.location].filter(Boolean).join(" · ")}</p>
                  {person.skills.length > 0 && <p className="mt-1 text-xs text-ink/50">{person.skills.join(" · ")}</p>}
                </div>
                {person.email ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <Input readOnly value={person.email} aria-label={`Email for ${person.full_name || "candidate"}`} className="max-w-md" />
                    <Button type="button" variant="outline" size="sm" onClick={() => copyText(person.email || "", person.id)}>
                      {copied === person.id ? "Copied" : "Copy email"}
                    </Button>
                  </div>
                ) : (
                  <p className="text-xs text-ink/50">No email address on this résumé.</p>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
