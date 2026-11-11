export type PostingBlock = { kind: "heading" | "item" | "text"; text: string };

const LIST_SECTION = /skill|qualification|requirement|responsibilit|desired|duties|experience|education/i;
const HEADING_WORDS = /skill|qualification|requirement|responsibilit|duties|overview|description|education|about|benefit|summary/i;

function isHeading(text: string, listing: boolean): boolean {
  if (text.length > 60 || /[.:;!?]$/.test(text) || text.includes(": ")) return false;
  return !listing || HEADING_WORDS.test(text);
}

/** Same heading and bullet split the public Full description uses. */
export function postingBlocks(paragraphs: string[]): PostingBlock[] {
  let listing = false;
  return paragraphs.map((text) => {
    if (isHeading(text, listing)) {
      listing = LIST_SECTION.test(text);
      return { kind: "heading", text };
    }
    return { kind: listing ? "item" : "text", text };
  });
}

/** Candidates on the internet use the public Spark address. An office or tailnet address stays on this machine. */
const PUBLIC_CAREERS = "https://spark-42c4.tail55e197.ts.net";

function isPrivateHost(host: string): boolean {
  if (host === "localhost" || host === "127.0.0.1" || host === "::1" || host === "[::1]") return true;
  if (host.startsWith("10.") || host.startsWith("192.168.")) return true;
  const second = /^172\.(\d+)\./.exec(host);
  if (second && Number(second[1]) >= 16 && Number(second[1]) <= 31) return true;
  return /^100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\./.test(host);
}

function candidateBase(): string {
  if (typeof window === "undefined") return PUBLIC_CAREERS;
  return isPrivateHost(window.location.hostname) ? PUBLIC_CAREERS : window.location.origin;
}

/** Profiles must say TS/SCI and a full-scope polygraph. Secret and CI poly are left out. */
export const LINKEDIN_CLEARANCE =
  '("TS/SCI" OR "TS SCI" OR "Top Secret/SCI" OR "Top Secret SCI") AND ("Full Scope Polygraph" OR "Full Scope Poly" OR FSP)';

function quoteTerm(term: string): string {
  const cleaned = term.replace(/"/g, "").replace(/\s+/g, " ").trim();
  return /^[A-Za-z0-9+#.-]+$/.test(cleaned) ? cleaned : `"${cleaned}"`;
}

/** The boolean string LinkedIn's keyword box runs. Clearance is always included. */
export function formLinkedInQuery(terms: string[], location: string, match: "all" | "any"): string {
  const quoted: string[] = [];
  const seen = new Set<string>();
  for (const raw of terms) {
    const term = raw.replace(/\s+/g, " ").trim().replace(/^"|"$/g, "");
    const key = term.toLowerCase();
    if (!term || seen.has(key)) continue;
    seen.add(key);
    quoted.push(quoteTerm(term));
    if (quoted.length === 6) break;
  }
  const parts = [LINKEDIN_CLEARANCE];
  if (match === "any" && quoted.length > 1) parts.push(`(${quoted.join(" OR ")})`);
  else parts.push(...quoted);
  const city = location.split(/,|\s+[-–—]\s+/)[0]?.trim() || "";
  if (city) parts.push(quoteTerm(city));
  return parts.join(" AND ");
}

export function linkedInUrls(query: string): { people: string; recruiter: string } {
  const encoded = encodeURIComponent(query);
  return {
    people: `https://www.linkedin.com/search/results/people/?keywords=${encoded}&origin=FACETED_SEARCH`,
    recruiter: `https://www.linkedin.com/talent/search?searchKeyword=${encoded}`,
  };
}

export function candidateJobUrl(code: string): string {
  return `${candidateBase()}/jobs?job=${encodeURIComponent(code)}`;
}

export function escapeHtml(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

export function postingEmail(input: {
  title: string | null;
  location: string | null;
  code: string;
  paragraphs: string[];
  applyUrl: string;
}): { plain: string; html: string } {
  const paragraphs = input.paragraphs.map((line) => line.trim()).filter(Boolean);
  const heading = [input.title || "Open role", [input.location, input.code].filter(Boolean).join(" · ")]
    .filter(Boolean)
    .join("\n");
  const body = paragraphs.join("\n\n") || "The full description is on the apply page.";
  const plain = `${heading}\n\n${body}\n\nApply: ${input.applyUrl}`;
  const htmlParts = [
    `<p><strong>${escapeHtml(input.title || "Open role")}</strong><br>${escapeHtml(
      [input.location, input.code].filter(Boolean).join(" · ")
    )}</p>`,
    ...paragraphs.map((line) => `<p>${escapeHtml(line)}</p>`),
    `<p><a href="${escapeHtml(input.applyUrl)}">Apply</a></p>`,
  ];
  return { plain, html: htmlParts.join("") };
}

export async function copyRich(plain: string, html: string): Promise<void> {
  try {
    if (typeof navigator !== "undefined" && navigator.clipboard?.write && typeof ClipboardItem !== "undefined") {
      await navigator.clipboard.write([
        new ClipboardItem({
          "text/html": new Blob([html], { type: "text/html" }),
          "text/plain": new Blob([plain], { type: "text/plain" }),
        }),
      ]);
      return;
    }
  } catch {
    // The plain-text copy below still puts the posting on the clipboard.
  }
  const area = document.createElement("textarea");
  area.value = plain;
  document.body.appendChild(area);
  area.select();
  document.execCommand("copy");
  area.remove();
}
