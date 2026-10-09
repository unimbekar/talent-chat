"use client";

import { Suspense, useEffect, useRef } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { MessageSquareText, Sparkles, Users } from "lucide-react";

import { askAssistant, openAssistant } from "@/lib/assistant";

export default function ShareRoute() {
  return (
    <Suspense fallback={null}>
      <SharePage />
    </Suspense>
  );
}

function SharePage() {
  const params = useSearchParams();
  const shared = [params.get("title"), params.get("text"), params.get("url")]
    .map((part) => (part || "").trim())
    .filter(Boolean)
    .filter((part, index, all) => all.indexOf(part) === index)
    .join("\n")
    .slice(0, 1500);
  const opened = useRef(false);

  useEffect(() => {
    if (opened.current || shared) return;
    opened.current = true;
    // Wait a tick so the panel's listener is attached after a cold start.
    const timer = window.setTimeout(openAssistant, 150);
    return () => window.clearTimeout(timer);
  }, [shared]);

  if (!shared) {
    return (
      <div className="flex flex-col items-start gap-3">
        <h1 className="page-title">Ask the desk</h1>
        <button type="button" onClick={openAssistant} className="inline-flex items-center gap-2 rounded-full bg-night px-4 py-2.5 text-sm font-medium text-white">
          <Sparkles className="size-4 text-pine-soft" /> Open the assistant
        </button>
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-xl flex-col gap-4">
      <div>
        <h1 className="page-title">Shared to the desk</h1>
        <p className="page-lead">Choose what to do with it. The assistant only reads; nothing is saved.</p>
      </div>
      <pre className="panel max-h-64 overflow-y-auto whitespace-pre-wrap break-words p-4 font-sans text-sm text-ink/80">{shared}</pre>
      <div className="grid gap-2 sm:grid-cols-2">
        <button
          type="button"
          onClick={() => askAssistant(`Find candidates in our bench who fit this:\n${shared}`)}
          className="flex items-center gap-3 rounded-2xl bg-night px-4 py-3.5 text-left text-sm font-medium text-white active:scale-[0.99]"
        >
          <Users className="size-5 text-pine-soft" /> Find matching candidates
        </button>
        <button
          type="button"
          onClick={() => askAssistant(shared)}
          className="flex items-center gap-3 rounded-2xl border border-line bg-card px-4 py-3.5 text-left text-sm font-medium active:scale-[0.99]"
        >
          <MessageSquareText className="size-5 text-pine" /> Ask the desk about it
        </button>
      </div>
      <Link href="/admin/dashboard" className="text-sm text-pine underline">
        Go to the dashboard
      </Link>
    </div>
  );
}
