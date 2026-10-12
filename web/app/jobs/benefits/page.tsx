import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { BrandMark } from "@/components/brand";

export const metadata: Metadata = { title: "Benefits" };

type Glance = { value: string; label: string };
type BenefitTable = { columns: string[]; rows: string[][] };
type Section = {
  id: string;
  kicker?: string;
  image: string;
  title: string;
  lead: string;
  points: string[];
  table?: BenefitTable;
};
type Guide = {
  title: string;
  season: string;
  company: string;
  address: string;
  phone_office: string;
  email: string;
  intro: string;
  glance: Glance[];
  sections: Section[];
};

async function loadGuide(): Promise<Guide | null> {
  const api = process.env.API_INTERNAL_URL || "http://127.0.0.1:8000";
  try {
    const response = await fetch(`${api}/public/benefits`, { cache: "no-store" });
    if (!response.ok) return null;
    return (await response.json()) as Guide;
  } catch {
    return null;
  }
}

export default async function BenefitsGuidePage() {
  const guide = await loadGuide();

  return (
    <main className="min-h-screen bg-[#FBF8F4] text-[#1C2430]">
      <header className="border-b border-[#E4D9C8] bg-[#FBF8F4]/95 backdrop-blur">
        <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center justify-between gap-4 px-5 py-4 sm:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <BrandMark className="size-11 rounded-xl ring-1 ring-[#E4D9C8]" />
            <div className="min-w-0">
              <p className="truncate text-sm font-medium tracking-tight">{guide?.company || "Janus Soft Inc."}</p>
              <p className="text-[11px] uppercase tracking-[0.16em] text-[#8A7354]">Benefits {guide?.season || "2026–27"}</p>
            </div>
          </div>
          <Link href="/jobs" className="inline-flex items-center gap-1.5 text-sm text-[#1C2430]/70 underline-offset-4 hover:text-[#1C2430] hover:underline">
            <ArrowLeft className="size-3.5" /> Open roles
          </Link>
        </div>
      </header>

      {!guide ? (
        <p className="mx-auto max-w-5xl px-5 py-16 text-sm text-[#1C2430]/70 sm:px-8">The benefits guide could not be loaded.</p>
      ) : (
        <div className="mx-auto w-full max-w-5xl px-5 py-10 sm:px-8 sm:py-14">
          <p className="text-[11px] uppercase tracking-[0.18em] text-[#8A7354]">For candidates</p>
          <h1 className="mt-3 max-w-2xl font-serif text-4xl tracking-tight sm:text-5xl">Your benefits</h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-[#1C2430]/75">{guide.intro}</p>
          <p className="mt-4 text-sm leading-6 text-[#1C2430]/60">
            {guide.address}
            <span className="px-2 text-[#E4D9C8]">/</span>
            {guide.phone_office} office
            <span className="px-2 text-[#E4D9C8]">/</span>
            <a className="underline-offset-4 hover:underline" href={`mailto:${guide.email}`}>
              {guide.email}
            </a>
          </p>

          <dl className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {guide.glance.map((item) => (
              <div key={item.label} className="rounded-2xl border border-[#E4D9C8] bg-[#F4EFE6] px-4 py-5 shadow-[inset_0_3px_0_#8A7354]">
                <dt className="font-serif text-3xl tracking-tight">{item.value}</dt>
                <dd className="mt-1 text-sm text-[#1C2430]/65">{item.label}</dd>
              </div>
            ))}
          </dl>

          <nav className="mt-8 flex flex-wrap gap-2" aria-label="Benefits sections">
            {guide.sections.map((section) => (
              <a
                key={section.id}
                href={`#${section.id}`}
                className="rounded-full border border-[#E4D9C8] bg-white px-3 py-1.5 text-xs tracking-wide text-[#1C2430]/75 hover:border-[#8A7354] hover:text-[#1C2430]"
              >
                {section.title}
              </a>
            ))}
          </nav>

          <div className="mt-10 flex flex-col gap-5">
            {guide.sections.map((section) => (
              <article key={section.id} id={section.id} className="scroll-mt-6 rounded-3xl border border-[#E4D9C8] bg-white px-5 py-6 sm:px-7 sm:py-7">
                <div className="flex items-start gap-4">
                  <img
                    src={`/api/public/benefits/media/${section.image}`}
                    alt=""
                    className="size-16 shrink-0 rounded-2xl bg-[#F4EFE6] object-cover ring-1 ring-[#E4D9C8] sm:size-20"
                  />
                  <div className="min-w-0">
                    {section.kicker && <p className="text-[11px] uppercase tracking-[0.16em] text-[#8A7354]">{section.kicker}</p>}
                    <h2 className="mt-1 font-serif text-2xl tracking-tight">{section.title}</h2>
                    <p className="mt-2 text-sm leading-6 text-[#1C2430]/70">{section.lead}</p>
                  </div>
                </div>
                <ul className="mt-5 space-y-2.5">
                  {section.points.map((point) => (
                    <li key={point} className="flex gap-3 text-sm leading-6 text-[#1C2430]/85">
                      <span className="mt-2 h-px w-4 shrink-0 bg-[#8A7354]" aria-hidden="true" />
                      <span>{point}</span>
                    </li>
                  ))}
                </ul>
                {section.table && (
                  <div className="mt-5 overflow-x-auto rounded-2xl border border-[#E4D9C8]">
                    <table className="w-full min-w-[40rem] border-collapse text-left text-sm">
                      <thead>
                        <tr className="bg-[#F4EFE6] text-[11px] uppercase tracking-wide text-[#1C2430]/55">
                          {section.table.columns.map((column) => (
                            <th key={column} className="border-b border-[#8A7354] px-3 py-2.5 font-medium">
                              {column}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {section.table.rows.map((row) => (
                          <tr key={row.join("|")} className="border-b border-[#E4D9C8] last:border-0">
                            {row.map((cell, index) => (
                              <td key={`${index}-${cell}`} className="px-3 py-3 align-top">
                                {cell}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </article>
            ))}
          </div>

          <p className="mt-10 text-sm leading-6 text-[#1C2430]/55">
            These terms are the {guide.season} benefits summary of {guide.company} · {guide.address} · {guide.phone_office} office · {guide.email}
          </p>
        </div>
      )}
    </main>
  );
}
