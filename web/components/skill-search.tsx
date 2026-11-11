"use client";

import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export type SkillNeed = { name: string; minYears: number | null };

export type SkillYear = { name: string; years: number | null; min_years: number | null; label: string };

export function SkillYears({ rows }: { rows: SkillYear[] }) {
  if (!rows.length) return null;
  return (
    <ul className="mt-1 flex flex-col gap-0.5 text-xs text-ink/80">
      {rows.map((row) => (
        <li key={row.name}>
          <span className="font-medium">{row.name}:</span> {row.label}
          {row.min_years != null ? <span className="text-ink/50"> · minimum {row.min_years}</span> : null}
        </li>
      ))}
    </ul>
  );
}

export function SkillSearch({
  onSearch,
  busy,
  suggestions,
}: {
  onSearch: (skills: SkillNeed[]) => void;
  busy?: boolean;
  suggestions?: string[];
}) {
  const [name, setName] = useState("");
  const [years, setYears] = useState("");
  const [rows, setRows] = useState<SkillNeed[]>([]);
  const [error, setError] = useState("");

  function add(event?: FormEvent) {
    event?.preventDefault();
    const skill = name.trim();
    if (!skill) {
      setError("Enter a skill.");
      return;
    }
    if (rows.some((row) => row.name.toLowerCase() === skill.toLowerCase())) {
      setError(`${skill} is already in the list.`);
      return;
    }
    let minYears: number | null = null;
    if (years.trim()) {
      const value = Number(years);
      if (!Number.isFinite(value) || value < 0 || value > 40) {
        setError("Minimum years is a number from 0 to 40.");
        return;
      }
      minYears = value;
    }
    setRows((current) => [...current, { name: skill, minYears }]);
    setName("");
    setYears("");
    setError("");
  }

  function addSuggestion(skill: string) {
    if (rows.some((row) => row.name.toLowerCase() === skill.toLowerCase())) return;
    setRows((current) => [...current, { name: skill, minYears: null }]);
    setError("");
  }

  return (
    <div className="flex flex-col gap-3">
      <form onSubmit={add} className="grid gap-2 sm:grid-cols-[1fr_9rem_auto] sm:items-end">
        <label className="text-sm">
          Skill
          <Input className="mt-1" value={name} onChange={(event) => setName(event.target.value)} placeholder="Java" />
        </label>
        <label className="text-sm">
          Minimum years
          <Input
            className="mt-1"
            type="number"
            min={0}
            max={40}
            step={1}
            value={years}
            onChange={(event) => setYears(event.target.value)}
            placeholder="Optional"
            aria-label="Minimum years"
          />
        </label>
        <Button type="submit" variant="outline" className="sm:mb-0">
          Add skill
        </Button>
      </form>
      {error && <p className="text-sm text-red-700">{error}</p>}
      {suggestions && suggestions.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-ink/60">From this role:</span>
          {suggestions.map((skill) => (
            <button key={skill} type="button" className="rounded-full border border-line px-2 py-0.5 text-xs text-pine" onClick={() => addSuggestion(skill)}>
              {skill}
            </button>
          ))}
        </div>
      )}
      {rows.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm">
          {rows.map((row) => (
            <li key={row.name} className="flex items-center justify-between gap-3 rounded-md border border-line px-3 py-1.5">
              <span>
                {row.name}
                {row.minYears == null ? <span className="text-ink/50"> · any years</span> : <span> · at least {row.minYears} years</span>}
              </span>
              <button
                type="button"
                className="text-xs text-pine underline"
                onClick={() => setRows((current) => current.filter((item) => item.name !== row.name))}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      <Button
        type="button"
        disabled={busy || rows.length === 0}
        className="w-full sm:w-auto sm:self-end"
        onClick={() => onSearch(rows)}
      >
        {busy ? "Searching…" : "Find by skills"}
      </Button>
    </div>
  );
}
