"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";

type JobCard = {
  requisition_code: string;
  title: string | null;
  location: string | null;
  matched_skills: string[];
  confidence: string;
  description_on_file: boolean;
  description_note: string | null;
  quote: string;
  source_url: string | null;
};

type ChatResponse = {
  refusal?: boolean;
  notice?: string | null;
  answer?: string;
  message?: string;
  error?: string;
  jobs?: JobCard[];
  prior_codes?: string[];
  limited?: boolean;
};

export default function ChatPage() {
  const [company, setCompany] = useState("Open roles");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [prior, setPrior] = useState<string[]>([]);
  const [turns, setTurns] = useState<{ question: string; response: ChatResponse }[]>([]);

  useEffect(() => {
    fetch("/api/public/config")
      .then((response) => response.json())
      .then((data) => setCompany(data.company_name || "Open roles"))
      .catch(() => setCompany("Open roles"));
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const message = draft.trim();
    if (!message || busy) return;
    setBusy(true);
    setDraft("");
    try {
      const response = await fetch("/api/public/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, prior_codes: prior }),
      });
      const data = (await response.json()) as ChatResponse;
      if (!response.ok && !data.message && !data.error) {
        data.error = "database";
        data.message = "The job database is unavailable right now.";
      }
      setPrior(data.prior_codes || []);
      setTurns((current) => [...current, { question: message, response: data }]);
    } catch {
      setTurns((current) => [
        ...current,
        {
          question: message,
          response: { error: "database", message: "The job database is unavailable right now.", jobs: [] },
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col px-4 py-6 sm:py-10">
      <header className="mb-6 border-b border-line pb-4">
        <p className="text-xs uppercase tracking-[0.18em] text-pine">Published openings</p>
        <h1 className="mt-1 font-serif text-3xl text-ink">{company}</h1>
        <p className="mt-2 max-w-xl text-sm leading-6 text-ink/80">
          Ask about skills, a city, or a requisition code. Answers use the job descriptions on file.
        </p>
      </header>

      <div className="flex flex-1 flex-col gap-4">
        {turns.length === 0 && (
          <p className="text-sm text-ink/70">Try “jobs with Java, Python, and AWS” or “jobs in Chantilly.”</p>
        )}
        {turns.map((turn, index) => (
          <section key={index} className="flex flex-col gap-3">
            <p className="text-sm text-ink/70">{turn.question}</p>
            <Answer response={turn.response} />
          </section>
        ))}
      </div>

      <form onSubmit={onSubmit} className="sticky bottom-0 mt-6 flex flex-col gap-2 bg-desk pb-2 pt-3">
        <label className="sr-only" htmlFor="question">
          Question
        </label>
        <Textarea
          id="question"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Jobs in Chantilly"
          rows={3}
        />
        <Button type="submit" disabled={busy} className="w-full sm:w-auto sm:self-end">
          {busy ? "Searching…" : "Search open jobs"}
        </Button>
      </form>
      <footer className="mt-6 text-xs text-ink/60">
        <Link href="/admin/login" className="underline">
          Recruiter sign in
        </Link>
      </footer>
    </main>
  );
}

function Answer({ response }: { response: ChatResponse }) {
  if (response.limited) {
    return <p className="text-sm">{response.message}</p>;
  }
  if (response.error === "database") {
    return (
      <p className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm" role="alert">
        {response.message || "The job database is unavailable right now."}
      </p>
    );
  }
  if (response.refusal) {
    return <p className="text-sm">{response.answer}</p>;
  }
  return (
    <div className="flex flex-col gap-3">
      {response.notice && (
        <p className="rounded-md border border-line bg-card px-3 py-2 text-sm">{response.notice}</p>
      )}
      {response.answer && <p className="text-sm leading-6">{response.answer}</p>}
      {(response.jobs || []).map((job) => (
        <Card key={job.requisition_code}>
          <CardHeader>
            <p className="font-mono text-sm text-pine">{job.requisition_code}</p>
            <CardTitle>{job.title}</CardTitle>
            <p className="text-sm text-ink/70">{job.location}</p>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <div className="flex flex-wrap gap-2">
              {(job.matched_skills || []).map((skill) => (
                <Badge key={skill}>{skill}</Badge>
              ))}
              <Badge>{job.confidence === "low" ? "Low confidence" : "Standard confidence"}</Badge>
            </div>
            {job.description_note && <p className="text-sm">{job.description_note}</p>}
            {job.quote && <p className="text-sm leading-6">{job.quote}</p>}
            {job.source_url && (
              <a className="text-sm text-pine underline" href={job.source_url}>
                Source posting
              </a>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
