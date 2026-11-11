"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";

import { CandidateActions } from "@/components/candidate-actions";
import { copyText } from "@/components/candidate-mail";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { formLinkedInQuery, LINKEDIN_CLEARANCE, linkedInUrls } from "@/lib/posting";
import { SkillSearch, SkillYears, type SkillNeed, type SkillYear } from "@/components/skill-search";

type DeskPerson = {
  id: string;
  full_name: string | null;
  email: string | null;
  location: string | null;
  skill_years?: SkillYear[];
};

type Lead = {
  id: string;
  full_name: string;
  profile_url: string;
  headline: string;
  note: string;
};

type LinkedInSearch = {
  clearance: string;
  terms: string[];
  location: string;
  query: string;
  people_url: string;
  recruiter_url: string;
  leads: Lead[];
};

export function LinkedInSource({ code }: { code: string }) {
  const [search, setSearch] = useState<LinkedInSearch | null>(null);
  const [name, setName] = useState("");
  const [profileUrl, setProfileUrl] = useState("");
  const [headline, setHeadline] = useState("");
  const [note, setNote] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [terms, setTerms] = useState("");
  const [city, setCity] = useState("");
  const [match, setMatch] = useState<"all" | "any">("all");
  const [copiedQuery, setCopiedQuery] = useState(false);
  const [queryText, setQueryText] = useState("");
  const [queryEdited, setQueryEdited] = useState(false);
  const [people, setPeople] = useState<DeskPerson[] | null>(null);
  const [finding, setFinding] = useState(false);
  const [findError, setFindError] = useState("");
  const [copiedEmails, setCopiedEmails] = useState(false);

  async function load(shape: boolean) {
    const response = await fetch(`/api/admin/jobs/${encodeURIComponent(code)}/linkedin`);
    if (!response.ok) return;
    const body = (await response.json()) as LinkedInSearch;
    setSearch(body);
    if (shape) {
      setTerms((body.terms || []).join("\n"));
      setCity(body.location || "");
      setMatch("all");
      setQueryEdited(false);
    }
  }

  useEffect(() => {
    void load(true);
  }, [code]);

  const formed = formLinkedInQuery(terms.split("\n"), city, match);
  const drafted = queryEdited ? queryText : formed;
  const query = drafted.trim() ? drafted : formed;
  const urls = linkedInUrls(query.trim());

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    const response = await fetch(`/api/admin/jobs/${encodeURIComponent(code)}/linkedin`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ full_name: name, profile_url: profileUrl, headline, note }),
    });
    const body = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setError(typeof body.detail === "string" ? body.detail : "That profile could not be saved.");
      return;
    }
    setName("");
    setProfileUrl("");
    setHeadline("");
    setNote("");
    setMessage(`${body.full_name} is saved on this job.`);
    await load(false);
  }

  async function findBySkills(skills: SkillNeed[]) {
    setFinding(true);
    setFindError("");
    setCopiedEmails(false);
    const response = await fetch("/api/admin/candidates/skills", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ skills: skills.map((skill) => ({ name: skill.name, min_years: skill.minYears })) }),
    });
    const body = await response.json().catch(() => ({}));
    setFinding(false);
    if (!response.ok || !Array.isArray(body.candidates)) {
      setFindError(typeof body.detail === "string" ? body.detail : "The desk search did not complete.");
      return;
    }
    setPeople(body.candidates as DeskPerson[]);
  }

  async function remove(lead: Lead) {
    setError("");
    const response = await fetch(`/api/admin/jobs/${encodeURIComponent(code)}/linkedin/${lead.id}`, { method: "DELETE" });
    if (!response.ok) {
      setError("That profile could not be removed.");
      return;
    }
    await load(false);
  }

  return (
    <section className="panel p-4">
      <h2 className="font-serif text-xl">Source on LinkedIn</h2>
      <p className="page-lead">
        Every search requires TS/SCI and a full-scope polygraph. Add the role words, then open it in the browser where
        your LinkedIn Recruiter seat is signed in. People who never wrote the clearance on their profile will not appear.
        Paste a profile link here after you find someone.
      </p>
      <label className="mt-3 block text-sm">
        Clearance, always included
        <textarea className="field mt-1 font-mono text-xs" readOnly rows={3} value={search?.clearance || LINKEDIN_CLEARANCE} />
      </label>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="text-sm">
          Role words, one per line
          <Textarea className="mt-1" rows={5} value={terms} onChange={(event) => setTerms(event.target.value)} />
        </label>
        <div className="flex flex-col gap-3">
          <label className="text-sm">
            City
            <Input className="mt-1" value={city} onChange={(event) => setCity(event.target.value)} />
          </label>
          <label className="text-sm">
            Role match
            <select className="field mt-1" value={match} onChange={(event) => setMatch(event.target.value === "any" ? "any" : "all")}>
              <option value="all">Every role word</option>
              <option value="any">Any role word</option>
            </select>
          </label>
        </div>
      </div>
      <label className="mt-3 block text-sm">
        Query LinkedIn will run. Edit it before you open the search.
        <textarea
          className="field mt-1 font-mono text-xs"
          rows={5}
          value={query}
          aria-label="LinkedIn query"
          onChange={(event) => {
            setQueryText(event.target.value);
            setQueryEdited(true);
            setCopiedQuery(false);
          }}
        />
      </label>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button asChild size="sm" variant="outline">
          <a href={urls.recruiter} target="_blank" rel="noopener noreferrer">
            Open in Recruiter
          </a>
        </Button>
        <Button asChild size="sm" variant="outline">
          <a href={urls.people} target="_blank" rel="noopener noreferrer">
            Open people search
          </a>
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => {
            copyText(query);
            setCopiedQuery(true);
          }}
        >
          {copiedQuery ? "Copied" : "Copy query"}
        </Button>
        {queryEdited && (
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => {
              setQueryEdited(false);
              setQueryText(formed);
            }}
          >
            Rebuild from role words
          </Button>
        )}
      </div>
      <div className="mt-4 border-t border-line pt-4">
        <h3 className="font-serif text-lg">Find on the desk</h3>
        <p className="page-lead">Add each skill, and a minimum number of years when you need one.</p>
        <div className="mt-3">
          <SkillSearch
            busy={finding}
            suggestions={terms.split("\n").map((line) => line.trim()).filter((line) => line && line.length <= 48)}
            onSearch={findBySkills}
          />
        </div>
      </div>
      {findError && <p className="mt-2 text-sm text-red-700">{findError}</p>}
      {people && (
        <div className="mt-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-serif text-lg">On the desk</h3>
            {people.some((person) => (person.email || "").includes("@")) && (
              <button
                type="button"
                className="text-sm font-medium text-pine underline"
                onClick={() => {
                  const emails = [
                    ...new Set(
                      people.map((person) => (person.email || "").trim().toLowerCase()).filter((email) => email.includes("@")),
                    ),
                  ];
                  copyText(emails.join(", "));
                  setCopiedEmails(true);
                }}
              >
                {copiedEmails ? "Copied" : "Copy emails"}
              </button>
            )}
          </div>
          {people.length === 0 ? (
            <p className="mt-2 text-sm text-ink/70">No one on file matches those words.</p>
          ) : (
            <ul className="mt-2 divide-y divide-line">
              {people.map((person) => (
                <li key={person.id} className="py-2 text-sm">
                  <Link href={`/admin/candidates/${person.id}`} className="font-medium text-pine underline">
                    {person.full_name || "Unnamed résumé"}
                  </Link>
                  <p className="text-xs text-ink/70">
                    {(person.email || "").trim() || "No email"} · {(person.location || "").trim() || "No location"}
                  </p>
                  {person.skill_years && <SkillYears rows={person.skill_years} />}
                  <CandidateActions id={person.id} job={code} />
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      <form onSubmit={save} className="mt-4 grid gap-3 sm:grid-cols-2">
        <label className="text-sm">
          Name
          <Input className="mt-1" value={name} onChange={(event) => setName(event.target.value)} required minLength={2} />
        </label>
        <label className="text-sm">
          LinkedIn profile link
          <Input
            className="mt-1"
            value={profileUrl}
            onChange={(event) => setProfileUrl(event.target.value)}
            placeholder="https://www.linkedin.com/in/…"
            required
          />
        </label>
        <label className="text-sm sm:col-span-2">
          Headline
          <Input className="mt-1" value={headline} onChange={(event) => setHeadline(event.target.value)} />
        </label>
        <label className="text-sm sm:col-span-2">
          Note
          <Textarea className="mt-1" value={note} onChange={(event) => setNote(event.target.value)} rows={3} />
        </label>
        <div>
          <Button type="submit" size="sm" disabled={busy}>
            Save on this job
          </Button>
        </div>
      </form>
      {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
      {message && <p className="mt-2 text-sm">{message}</p>}
      {(search?.leads.length || 0) > 0 && (
        <ul className="mt-4 flex flex-col gap-3">
          {search?.leads.map((lead) => (
            <li key={lead.id} className="border-t border-line pt-3 text-sm">
              <a className="font-medium text-pine underline" href={lead.profile_url} target="_blank" rel="noopener noreferrer">
                {lead.full_name}
              </a>
              {lead.headline && <p className="text-ink/70">{lead.headline}</p>}
              {lead.note && <p className="mt-1">{lead.note}</p>}
              <button type="button" className="mt-1 text-pine underline" onClick={() => void remove(lead)}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
