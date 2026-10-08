"use client";

import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { whenExact, type Note } from "@/lib/pipeline";

type Props = {
  comments: Note[];
  heading: string;
  hint: string;
  empty: string;
  onCreate: (body: string) => Promise<void>;
  onEdit: (id: string, body: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
};

export function CommentThread({ comments, heading, hint, empty, onCreate, onEdit, onDelete }: Props) {
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!draft.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      await onCreate(draft.trim());
      setDraft("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The comment was not saved.");
    } finally {
      setBusy(false);
    }
  }

  async function saveEdit(id: string) {
    if (!editText.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      await onEdit(id, editText.trim());
      setEditing(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The comment was not saved.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    setBusy(true);
    setError("");
    try {
      await onDelete(id);
      if (editing === id) setEditing(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The comment was not removed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel p-4">
      <h2 className="font-serif text-xl">{heading}</h2>
      <p className="page-lead">{hint}</p>
      <form onSubmit={create} className="mt-3 flex flex-col gap-2">
        <label className="text-sm">
          New comment
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            rows={3}
            className="field mt-1"
            placeholder="What should the next recruiter know?"
          />
        </label>
        <div className="flex items-center gap-3">
          <Button type="submit" size="sm" disabled={busy || !draft.trim()}>
            {busy ? "Saving…" : "Add comment"}
          </Button>
          {error && <p className="text-sm text-red-700">{error}</p>}
        </div>
      </form>
      <ul className="mt-4 flex flex-col gap-3">
        {comments.length === 0 && <li className="text-sm text-ink/60">{empty}</li>}
        {comments.map((comment) => (
          <li key={comment.id} className="rounded-xl border border-line bg-desk/60 px-3 py-3">
            {editing === comment.id ? (
              <div className="flex flex-col gap-2">
                <textarea value={editText} onChange={(event) => setEditText(event.target.value)} rows={3} className="field" aria-label="Edit comment" />
                <div className="flex gap-2">
                  <Button type="button" size="sm" disabled={busy || !editText.trim()} onClick={() => saveEdit(comment.id)}>
                    Save
                  </Button>
                  <Button type="button" size="sm" variant="outline" onClick={() => setEditing(null)}>
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <>
                <p className="whitespace-pre-wrap text-sm leading-6">{comment.body}</p>
                <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-ink/55">
                  <span>
                    {whenExact(comment.created_at)}
                    {comment.edited ? " · edited" : ""}
                  </span>
                  <button
                    type="button"
                    className="text-pine hover:underline"
                    onClick={() => {
                      setEditing(comment.id);
                      setEditText(comment.body);
                    }}
                  >
                    Edit
                  </button>
                  <button type="button" className="text-red-700 hover:underline" onClick={() => remove(comment.id)}>
                    Delete
                  </button>
                </div>
              </>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
