"use client";

import { Button } from "@/components/ui/button";

export type MailPerson = {
  id: string;
  email: string | null;
};

export function copyText(value: string) {
  const area = document.createElement("textarea");
  area.value = value;
  document.body.appendChild(area);
  area.select();
  document.execCommand("copy");
  area.remove();
  if (navigator.clipboard?.writeText) {
    void navigator.clipboard.writeText(value).catch(() => undefined);
  }
}

export function selectedEmails(people: MailPerson[], selected: Set<string>): string {
  const seen = new Set<string>();
  const emails: string[] = [];
  for (const person of people) {
    if (!selected.has(person.id)) continue;
    const email = (person.email || "").trim().toLowerCase();
    if (!email.includes("@") || seen.has(email)) continue;
    seen.add(email);
    emails.push(email);
  }
  return emails.join(", ");
}

export function shown(value: string | null | undefined): string {
  const text = (value || "").trim();
  return text || "unknown";
}

export function CandidateMailBar({
  total,
  selectedCount,
  allSelected,
  onToggleAll,
  onCopy,
  copied,
  note,
}: {
  total: number;
  selectedCount: number;
  allSelected: boolean;
  onToggleAll: () => void;
  onCopy: () => void;
  copied: boolean;
  note?: string;
}) {
  if (total === 0) return null;
  return (
    <div className="mt-3 flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" onClick={onToggleAll}>
          {allSelected ? "Select none" : "Select all"}
        </Button>
        <Button type="button" onClick={onCopy} disabled={selectedCount === 0}>
          {copied ? "Copied" : `Copy selected emails (${selectedCount})`}
        </Button>
      </div>
      {note && <p className="text-sm text-ink/70">{note}</p>}
    </div>
  );
}
