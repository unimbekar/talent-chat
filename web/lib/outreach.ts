import { candidateJobUrl, escapeHtml } from "@/lib/posting";

export type OutreachPerson = {
  full_name: string | null;
  mandatory_pct: number | null;
  meets_bar: boolean;
  matched_lines?: string[];
};

export type OutreachJob = {
  requisition_code: string;
  title: string | null;
  location: string | null;
};

function firstName(fullName: string | null): string {
  const name = (fullName || "").trim();
  if (!name) return "";
  return name.split(/\s+/)[0];
}

function skillPhrase(line: string): string {
  const label = line.split(":")[0].trim();
  if (label.length >= 3 && label.length <= 70) return label;
  return line.length > 90 ? `${line.slice(0, 87).trim()}…` : line;
}

function skillSentence(lines: string[]): string {
  const phrases = lines.map(skillPhrase).filter(Boolean).slice(0, 4);
  if (phrases.length === 0) return "";
  if (phrases.length === 1) return phrases[0];
  return `${phrases.slice(0, -1).join(", ")} and ${phrases[phrases.length - 1]}`;
}

export function outreachSubject(job: OutreachJob): string {
  const title = job.title || "an open role";
  const place = (job.location || "").trim();
  return place ? `${title} in ${place} — Janus Soft` : `${title} — Janus Soft`;
}

export function outreachBody(person: OutreachPerson, job: OutreachJob): string {
  const name = firstName(person.full_name);
  const title = job.title || "this role";
  const place = (job.location || "").trim();
  const where = place ? ` in ${place}` : "";
  const percent = person.mandatory_pct == null ? null : Math.round(person.mandatory_pct * 100);
  const fit = person.meets_bar || (percent != null && percent >= 90) ? "strong" : "solid";
  const skills = skillSentence(person.matched_lines || []);
  const coverage =
    percent == null
      ? `Your experience is a ${fit} fit for this position.`
      : skills
        ? `Your résumé covers ${percent}% of the mandatory requirements, including ${skills}.`
        : `Your résumé covers ${percent}% of the mandatory requirements for this position.`;
  const based = place ? `The role is based in ${place}. ` : "";
  const apply = candidateJobUrl(job.requisition_code);

  return [
    name ? `Hello ${name},` : "Hello,",
    "",
    `I am writing from Janus Soft about our ${title} opening${where} (${job.requisition_code}).`,
    "",
    `${coverage} That experience is the kind of work this team is looking for, and I wanted you to see the role.`,
    "",
    `${based}This position requires an active TS/SCI clearance with a Full Scope Polygraph (FSP).`,
    "",
    "Janus Soft offers some of the strongest pay and benefits in our field:",
    "",
    "💰 Competitive high salaries",
    "📈 10% Company 401(k) Match",
    "🌴 Unlimited PTO",
    "🏥 100% Employer-Paid Employee Medical Insurance",
    "",
    "You can read the posting and apply here:",
    apply,
    "",
    "I would welcome a conversation about the position and how your skills fit it.",
    "",
    "Kind regards,",
    "Janus Soft Recruiting",
  ].join("\n");
}

export function outreachHtml(subject: string, body: string): string {
  const blocks = body
    .split(/\n{2,}/)
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => {
      const linked = escapeHtml(part).replace(
        /https?:\/\/[^\s<]+/g,
        (url) => `<a href="${url}">${url}</a>`,
      );
      return `<p>${linked.replace(/\n/g, "<br>")}</p>`;
    });
  return `<p><strong>${escapeHtml(subject)}</strong></p>${blocks.join("")}`;
}
