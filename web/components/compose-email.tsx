"use client";

import { useState } from "react";

import { copyText } from "@/components/candidate-mail";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { copyRich } from "@/lib/posting";
import { outreachHtml } from "@/lib/outreach";

export function ComposeEmail({
  subject,
  body,
  onSubject,
  onBody,
  onRestore,
  onClose,
}: {
  subject: string;
  body: string;
  onSubject: (value: string) => void;
  onBody: (value: string) => void;
  onRestore: () => void;
  onClose: () => void;
}) {
  const [copied, setCopied] = useState<"subject" | "email" | "">("");

  async function copyEmail() {
    const plain = `Subject: ${subject}\n\n${body}`;
    await copyRich(plain, outreachHtml(subject, body));
    setCopied("email");
  }

  return (
    <div className="mt-3 rounded-lg border border-line bg-desk/40 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-serif text-lg">Email to this candidate</h3>
        <button type="button" className="text-xs text-pine underline" onClick={onClose}>
          Close
        </button>
      </div>
      <p className="mt-1 text-xs text-ink/60">Edit the note, then copy it into your mail program. Nothing is sent from the desk.</p>
      <label className="mt-3 block text-sm">
        Subject
        <Input className="mt-1" value={subject} onChange={(event) => onSubject(event.target.value)} />
      </label>
      <label className="mt-3 block text-sm">
        Message
        <Textarea className="mt-1 font-serif leading-6" rows={16} value={body} onChange={(event) => onBody(event.target.value)} />
      </label>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button type="button" size="sm" onClick={() => void copyEmail()}>
          {copied === "email" ? "Copied" : "Copy email"}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => {
            copyText(subject);
            setCopied("subject");
          }}
        >
          {copied === "subject" ? "Subject copied" : "Copy subject"}
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={onRestore}>
          Restore template
        </Button>
      </div>
    </div>
  );
}
