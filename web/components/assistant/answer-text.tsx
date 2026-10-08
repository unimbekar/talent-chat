"use client";

import { Fragment, type ReactNode } from "react";
import Link from "next/link";

import type { Block } from "@/lib/assistant";

// A small markdown subset: paragraphs, bullets, numbered lists, **bold**, `code`, and links.
// Job codes and the names of people in this answer's results link to their pages.

type Links = { codes: Set<string>; people: Map<string, string> };

export function linksFrom(blocks: Block[]): Links {
  const codes = new Set<string>();
  const people = new Map<string, string>();
  for (const block of blocks) {
    if (block.type === "jobs") block.rows.forEach((row) => codes.add(row.code));
    if (block.type === "ranked") {
      codes.add(block.code);
      block.rows.forEach((row) => row.name && people.set(row.name, row.id));
    }
    if (block.type === "candidates") block.rows.forEach((row) => row.name && people.set(row.name, row.id));
    if (block.type === "submissions") block.rows.forEach((row) => {
      codes.add(row.code);
      if (row.candidate) people.set(row.candidate, row.candidate_id);
    });
    if (block.type === "job") codes.add(block.job.code);
    if (block.type === "fit") {
      codes.add(block.fit.code);
      people.set(block.fit.candidate, block.fit.candidate_id);
    }
    if (block.type === "profile" && block.candidate.name) people.set(block.candidate.name, block.candidate.id);
    if (block.type === "submission") codes.add(block.submission.code);
  }
  return { codes, people };
}

function escapeRegex(text: string) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function inline(text: string, links: Links, key: string): ReactNode[] {
  const names = [...links.people.keys()].filter((name) => name.length > 3).sort((a, b) => b.length - a.length);
  const parts = [
    String.raw`\*\*([^*]+)\*\*`,
    String.raw`\x60([^\x60]+)\x60`,
    String.raw`\[([^\]]+)\]\(((?:https?:\/\/|\/)[^\s)]+)\)`,
    String.raw`\b([A-Z][0-9]{3,5})\b`,
  ];
  if (names.length) parts.push(`(${names.map(escapeRegex).join("|")})`);
  const pattern = new RegExp(parts.join("|"), "g");
  const out: ReactNode[] = [];
  let last = 0;
  let index = 0;
  for (const match of text.matchAll(pattern)) {
    const start = match.index ?? 0;
    if (start > last) out.push(text.slice(last, start));
    const id = `${key}-${index++}`;
    const [whole, bold, code, linkText, href, jobCode, person] = match;
    if (bold !== undefined) out.push(<strong key={id} className="font-semibold text-ink">{inline(bold, links, id)}</strong>);
    else if (code !== undefined && links.codes.has(code)) {
      out.push(<Link key={id} href={`/admin/jobs/${code}`} className="font-mono text-[0.92em] font-semibold text-pine hover:underline">{code}</Link>);
    } else if (code !== undefined) out.push(<code key={id} className="rounded bg-ink/5 px-1 font-mono text-[0.85em]">{code}</code>);
    else if (linkText !== undefined) {
      out.push(
        href.startsWith("/") ? (
          <Link key={id} href={href} className="text-pine underline">{linkText}</Link>
        ) : (
          <a key={id} href={href} target="_blank" rel="noopener noreferrer" className="text-pine underline">{linkText}</a>
        ),
      );
    } else if (jobCode !== undefined) {
      out.push(
        links.codes.has(jobCode) ? (
          <Link key={id} href={`/admin/jobs/${jobCode}`} className="font-mono text-[0.92em] font-semibold text-pine hover:underline">{jobCode}</Link>
        ) : (
          jobCode
        ),
      );
    } else if (person !== undefined) {
      out.push(
        <Link key={id} href={`/admin/candidates/${links.people.get(person)}`} className="decoration-pine/40 underline-offset-2 hover:text-pine hover:underline">
          {person}
        </Link>,
      );
    } else out.push(whole);
    last = start + whole.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function AnswerText({ text, blocks }: { text: string; blocks: Block[] }) {
  const links = linksFrom(blocks);
  const lines = text.replace(/\r/g, "").split("\n");
  const nodes: ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  let paragraph: string[] = [];

  const flushParagraph = () => {
    if (paragraph.length) {
      const key = `p${nodes.length}`;
      nodes.push(
        <p key={key}>
          {paragraph.map((line, i) => (
            <Fragment key={i}>
              {i > 0 && <br />}
              {inline(line, links, `${key}-${i}`)}
            </Fragment>
          ))}
        </p>,
      );
      paragraph = [];
    }
  };
  const flushList = () => {
    if (list) {
      const key = `l${nodes.length}`;
      const items = list.items.map((item, i) => <li key={i}>{inline(item, links, `${key}-${i}`)}</li>);
      nodes.push(
        list.ordered ? (
          <ol key={key} className="list-decimal space-y-0.5 pl-5">{items}</ol>
        ) : (
          <ul key={key} className="list-disc space-y-0.5 pl-5 marker:text-ink/30">{items}</ul>
        ),
      );
      list = null;
    }
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*[-*•]\s+(.*)$/);
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (bullet || numbered) {
      flushParagraph();
      const ordered = Boolean(numbered);
      if (!list || list.ordered !== ordered) {
        flushList();
        list = { ordered, items: [] };
      }
      list.items.push((bullet || numbered)![1]);
    } else if (!line.trim()) {
      flushParagraph();
      flushList();
    } else {
      flushList();
      paragraph.push(line.replace(/^#{1,6}\s+/, ""));
    }
  }
  flushParagraph();
  flushList();
  return <div className="space-y-2 text-sm leading-6 text-ink/85">{nodes}</div>;
}
