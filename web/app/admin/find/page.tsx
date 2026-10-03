"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { CandidateMailBar, copyText, selectedEmails, shown } from "@/components/candidate-mail";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ClipboardCheck, Download } from "lucide-react";

import { downloadCsv } from "@/lib/csv";
import { writeCache } from "@/lib/page-cache";

type Person = {
  id: string;
  full_name: string | null;
  email: string | null;
  location: string | null;
  titles: string[];
  skills: string[];
};

type StateRef = { code: string; name: string };

type Filters = {
  skills: string[];
  states: StateRef[];
  exclude_states: StateRef[];
  categories: string[];
  keywords: string[];
  parser: "llm" | "rules";
};

type Answer = {
  answer: string;
  categories: string[];
  filters?: Filters | null;
  unknown_location?: number;
  candidates: Person[];
};

function filterChips(filters: Filters): string[] {
  return [
    ...filters.categories.map((label) => `Role: ${label}`),
    ...filters.skills.map((skill) => `Skill: ${skill}`),
    ...filters.keywords.map((word) => `Mentions: ${word}`),
    ...filters.states.map((state) => `Lives in: ${state.name}`),
    ...(filters.exclude_states || []).map((state) => `Not in: ${state.name}`),
  ];
}

const STORAGE_KEY = "talent-find-results";

export default function FindPage() {
  const router = useRouter();
  const [draft, setDraft] = useState("Find me all candidates with ServiceNow experience who live in Maryland.");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Answer | null>(null);
  const [copied, setCopied] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [copyNote, setCopyNote] = useState("");
  const [restored, setRestored] = useState(false);

  useEffect(() => {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (raw) {
      try {
        const saved = JSON.parse(raw) as { draft?: string; result?: Answer | null; selected?: string[] };
        if (saved.draft) setDraft(saved.draft);
        if (saved.result) setResult(saved.result);
        if (saved.selected) setSelected(new Set(saved.selected));
      } catch {
        sessionStorage.removeItem(STORAGE_KEY);
      }
    }
    setRestored(true);
  }, []);

  useEffect(() => {
    if (!restored) return;
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ draft, result, selected: [...selected] }));
  }, [draft, result, selected, restored]);

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

  function reviewSelected() {
    const people = (result?.candidates || []).filter((person) => selected.has(person.id));
    writeCache(
      "talent-review-picked",
      people.map((person) => ({ id: person.id, full_name: person.full_name, original_filename: null, email: person.email, location: person.location })),
    );
    router.push(`/admin/review?candidates=${people.map((person) => person.id).join(",")}`);
  }

  function copyLabeled(value: string, label: string) {
    copyText(value);
    setCopied(label);
  }

  const emails = (result?.candidates || []).map((person) => person.email).filter((email): email is string => Boolean(email));

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="page-title">Find candidates</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink/70">
          Ask in plain words for a role, a skill, and where people live, such as ServiceNow people in Maryland, Software
          Testers, or Java developers outside Virginia. The filters used are shown above the list. Emails stay on this
          desk so you can copy them. Nothing is sent.
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
              <Button type="button" variant="outline" onClick={() => copyLabeled(emails.join("\n"), "all")}>
                {copied === "all" ? "Copied" : "Copy all emails"}
              </Button>
            )}
          </div>
          <CandidateMailBar
            total={result.candidates.length}
            selectedCount={result.candidates.filter((person) => selected.has(person.id)).length}
            allSelected={result.candidates.length > 0 && result.candidates.every((person) => selected.has(person.id))}
            onToggleAll={() => {
              setCopied("");
              setSelected(
                result.candidates.every((person) => selected.has(person.id))
                  ? new Set()
                  : new Set(result.candidates.map((person) => person.id)),
              );
            }}
            onCopy={() => {
              const list = selectedEmails(result.candidates, selected);
              const missing = result.candidates.filter((person) => selected.has(person.id) && !(person.email || "").includes("@")).length;
              setCopyNote(missing ? `${missing} selected ${missing === 1 ? "candidate has" : "candidates have"} no email, so ${missing === 1 ? "that address was" : "those addresses were"} left out.` : "");
              if (!list) return;
              copyLabeled(list, "selected");
            }}
            copied={copied === "selected"}
            note={copyNote}
          />
          <div className="flex flex-wrap gap-2">
            {result.candidates.some((person) => selected.has(person.id)) && (
              <Button type="button" onClick={reviewSelected}>
                <ClipboardCheck /> Review selected against a job
              </Button>
            )}
            {result.candidates.length > 0 && (
              <Button
                type="button"
                variant="outline"
                onClick={() =>
                  downloadCsv(
                    "find-results.csv",
                    ["Name", "Email", "Location", "Titles", "Skills"],
                    result.candidates.map((person) => [person.full_name, person.email, person.location, person.titles.join("; "), person.skills.join("; ")]),
                  )
                }
              >
                <Download /> Export CSV
              </Button>
            )}
          </div>
          {result.filters && (
            <div className="flex flex-col gap-1.5">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-xs text-ink/60">Filters used:</span>
                {filterChips(result.filters).map((chip) => (
                  <Badge key={chip}>{chip}</Badge>
                ))}
              </div>
              {result.filters.parser === "rules" && (
                <p className="text-xs text-ink/60">
                  The language model did not answer, so these filters were read by keyword. Negation such as “outside
                  Virginia” is not understood in this mode.
                </p>
              )}
            </div>
          )}
          {(result.unknown_location || 0) > 0 && (
            <p className="text-xs text-ink/60">
              {result.unknown_location} more {result.unknown_location === 1 ? "résumé matches" : "résumés match"} the
              other filters but {result.unknown_location === 1 ? "has" : "have"} no known home state, so{" "}
              {result.unknown_location === 1 ? "it is" : "they are"} not listed. Add a location on the résumé’s profile
              to include {result.unknown_location === 1 ? "it" : "them"}.
            </p>
          )}
          <ul className="divide-y divide-line overflow-hidden panel">
            {result.candidates.length === 0 && <li className="px-4 py-8 text-sm text-ink/70">No one on file matches all of those filters.</li>}
            {result.candidates.map((person) => (
              <li key={person.id} className="flex flex-col gap-2 px-4 py-3">
                <div className="flex items-start gap-3">
                  <input
                    type="checkbox"
                    className="mt-1"
                    aria-label={`Select ${person.full_name || "candidate"}`}
                    checked={selected.has(person.id)}
                    onChange={() => {
                      setCopied("");
                      setSelected((current) => {
                        const next = new Set(current);
                        if (next.has(person.id)) next.delete(person.id);
                        else next.add(person.id);
                        return next;
                      });
                    }}
                  />
                  <div>
                    <Link href={`/admin/match?id=${person.id}`} className="font-medium hover:text-pine">
                      {person.full_name || "Unnamed résumé"}
                    </Link>
                    <p className="text-xs text-ink/60">{person.titles.join(", ")}</p>
                    <p className="text-xs text-ink/80">Email: {shown(person.email)}</p>
                    <p className="text-xs text-ink/80">Location: {shown(person.location)}</p>
                    {person.skills.length > 0 && <p className="mt-1 text-xs text-ink/50">{person.skills.join(" · ")}</p>}
                  </div>
                </div>
                {person.email ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <Input readOnly value={person.email} aria-label={`Email for ${person.full_name || "candidate"}`} className="max-w-md" />
                    <Button type="button" variant="outline" size="sm" onClick={() => copyLabeled(person.email || "", person.id)}>
                      {copied === person.id ? "Copied" : "Copy email"}
                    </Button>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
