"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Download } from "lucide-react";

import { Button } from "@/components/ui/button";

type Glance = { value: string; label: string };
type BenefitTable = { columns: string[]; rows: string[][] };
type Section = {
  id: string;
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
  source: string;
  filename: string;
  intro: string;
  glance: Glance[];
  sections: Section[];
};

export default function BenefitsPage() {
  const router = useRouter();
  const [guide, setGuide] = useState<Guide | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let gone = false;
    fetch("/api/admin/benefits")
      .then(async (response) => {
        if (response.status === 401) {
          router.push("/admin/login");
          return null;
        }
        if (!response.ok) throw new Error("unavailable");
        return response.json() as Promise<Guide>;
      })
      .then((data) => {
        if (!gone && data) setGuide(data);
      })
      .catch(() => {
        if (!gone) setError("The benefits guide could not be loaded.");
      });
    return () => {
      gone = true;
    };
  }, [router]);

  return (
    <main className="mx-auto w-full max-w-4xl px-4 py-8 sm:px-6">
      <p className="careers-kicker">Candidates</p>
      <div className="mt-2 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="page-title">Benefits</h1>
          <p className="page-lead">{guide ? `${guide.company} · ${guide.season}` : "The benefits summary candidates can be shown."}</p>
        </div>
        <Button asChild>
          <a href="/api/admin/benefits/download">
            <Download />
            Download
          </a>
        </Button>
      </div>

      {error && (
        <p className="mt-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800" role="alert">
          {error}
        </p>
      )}

      {guide && (
        <>
          <p className="mt-6 max-w-2xl text-sm leading-6 text-ink/70">{guide.intro}</p>
          <dl className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {guide.glance.map((item) => (
              <div key={item.value} className="rounded-2xl border border-line bg-card px-4 py-4">
                <dt className="font-mono text-2xl tracking-tight">{item.value}</dt>
                <dd className="mt-1 text-xs leading-5 text-ink/60">{item.label}</dd>
              </div>
            ))}
          </dl>

          <div className="mt-8 flex flex-col gap-4">
            {guide.sections.map((section) => (
              <article key={section.id} className="panel p-5 sm:p-6">
                <div className="flex items-start gap-4">
                  <img
                    src={`/api/admin/benefits/media/${section.image}`}
                    alt=""
                    className="size-16 shrink-0 rounded-2xl bg-night object-cover"
                  />
                  <div className="min-w-0">
                    <h2 className="text-lg font-medium tracking-tight">{section.title}</h2>
                    <p className="mt-1 text-sm leading-6 text-ink/65">{section.lead}</p>
                  </div>
                </div>
                <ul className="mt-4 list-disc space-y-2 pl-5 text-sm leading-6 text-ink/80">
                  {section.points.map((point) => (
                    <li key={point}>{point}</li>
                  ))}
                </ul>
                {section.table && (
                  <div className="mt-4 overflow-x-auto">
                    <table className="w-full min-w-[36rem] border-collapse text-left text-sm">
                      <thead>
                        <tr className="border-b border-line text-xs uppercase tracking-wide text-ink/45">
                          {section.table.columns.map((column) => (
                            <th key={column} className="px-3 py-2 font-medium">
                              {column}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {section.table.rows.map((row) => (
                          <tr key={row.join("|")} className="border-b border-line/70">
                            {row.map((cell) => (
                              <td key={cell} className="px-3 py-2.5">
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

          <p className="mt-6 text-sm leading-6 text-ink/55">
            {guide.address}. {guide.phone_office} office · {guide.email}. Source: {guide.source}.
          </p>
        </>
      )}
    </main>
  );
}
