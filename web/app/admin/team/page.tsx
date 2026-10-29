"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Eye, EyeOff, ShieldCheck, UserPlus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useDesk, type Role } from "@/lib/desk";
import { errorMessage, when } from "@/lib/pipeline";

type Account = {
  id: string;
  email: string;
  display_name: string | null;
  role: Role;
  active: boolean;
  builtin: boolean;
  created_at: string | null;
  last_login_at: string | null;
  signed_in: boolean | null;
};

const RECRUITER_LIMITS = [
  "Cannot delete anything: jobs, submissions, résumés, comments, or documents",
  "No burden calculator, and no margins or bill rates on the pipeline",
  "Cannot edit, close, reopen, or recrawl jobs",
  "Cannot run folder or cloud imports, or export reports",
  "Cannot change settings, company documents, or team accounts",
];

export default function TeamPage() {
  const router = useRouter();
  const desk = useDesk();
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [minimum, setMinimum] = useState(12);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    const response = await fetch("/api/admin/team");
    if (response.status === 401) {
      router.push("/admin/login");
      return;
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      setError(errorMessage(data, "The team list did not load."));
      return;
    }
    setAccounts(data.accounts || []);
    if (data.password_min) setMinimum(data.password_min);
  }, [router]);

  useEffect(() => {
    void load();
  }, [load]);

  async function call(method: "POST" | "PATCH" | "DELETE", path: string, body?: object): Promise<boolean> {
    setError("");
    setNotice("");
    const response = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (response.status === 401) {
      router.push("/admin/login");
      return false;
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      setError(errorMessage(data, "That change was not saved."));
      return false;
    }
    await load();
    return true;
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <div>
        <p className="text-xs uppercase tracking-[0.18em] text-pine-deep">Desk</p>
        <h1 className="mt-1 font-serif text-3xl">Team</h1>
        <p className="mt-2 text-sm leading-6 text-ink/65">
          Who can sign in to the desk. Admins can do everything. Recruiters work jobs, candidates, the pipeline, and reports. Changing a role, turning an
          account off, or resetting a password signs that person out everywhere.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <AddAccount minimum={minimum} onAdd={(body) => call("POST", "/api/admin/team", body)} onAdded={setNotice} />
        <aside className="rounded-2xl border border-line bg-white p-5 shadow-sm">
          <p className="flex items-center gap-2 text-sm font-medium">
            <ShieldCheck className="size-4 text-pine" /> What a recruiter cannot do
          </p>
          <ul className="mt-3 flex flex-col gap-2 text-sm text-ink/70">
            {RECRUITER_LIMITS.map((line) => (
              <li key={line} className="flex gap-2">
                <span aria-hidden="true" className="mt-2 size-1.5 shrink-0 rounded-full bg-ink/30" />
                {line}
              </li>
            ))}
          </ul>
        </aside>
      </div>

      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="rounded-lg border border-pine/30 bg-pine/10 px-3 py-2 text-sm text-ink" role="status">
          {notice}
        </p>
      )}

      <section className="flex flex-col gap-3">
        <h2 className="font-serif text-2xl">Accounts</h2>
        {accounts === null && !error && <p className="text-sm text-ink/60">Loading accounts…</p>}
        {accounts?.map((account) => (
          <AccountRow
            key={account.id}
            account={account}
            minimum={minimum}
            isYou={account.email === desk.email}
            onPatch={(body) => call("PATCH", `/api/admin/team/${account.id}`, body)}
            onDelete={() => call("DELETE", `/api/admin/team/${account.id}`)}
            onNotice={setNotice}
          />
        ))}
      </section>
    </div>
  );
}

function AddAccount({
  minimum,
  onAdd,
  onAdded,
}: {
  minimum: number;
  onAdd: (body: object) => Promise<boolean>;
  onAdded: (text: string) => void;
}) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<Role>("recruiter");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    const ok = await onAdd({ email, password, role, display_name: name || null });
    setBusy(false);
    if (!ok) return;
    onAdded(`${email.trim().toLowerCase()} can sign in now as ${role === "admin" ? "an admin" : "a recruiter"}. Share the password privately.`);
    setEmail("");
    setName("");
    setPassword("");
    setRole("recruiter");
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4 rounded-2xl border border-line bg-white p-5 shadow-sm">
      <p className="flex items-center gap-2 font-serif text-xl">
        <UserPlus className="size-5 text-pine" /> Add someone
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="team-email">Work email</Label>
          <Input id="team-email" type="email" autoComplete="off" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="name@janus-soft.com" required />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="team-name">Name</Label>
          <Input id="team-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="Optional" maxLength={120} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="team-role">Role</Label>
          <select id="team-role" className="field h-10" value={role} onChange={(event) => setRole(event.target.value as Role)}>
            <option value="recruiter">Recruiter</option>
            <option value="admin">Admin</option>
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="team-password">Starting password</Label>
          <PasswordInput id="team-password" value={password} onChange={setPassword} show={show} onToggle={() => setShow(!show)} minimum={minimum} />
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={busy || !email.trim() || password.length < minimum}>
          {busy ? "Adding…" : "Add account"}
        </Button>
        <p className="text-xs text-ink/55">At least {minimum} characters. They can change it from Password after signing in.</p>
      </div>
    </form>
  );
}

function AccountRow({
  account,
  minimum,
  isYou,
  onPatch,
  onDelete,
  onNotice,
}: {
  account: Account;
  minimum: number;
  isYou: boolean;
  onPatch: (body: object) => Promise<boolean>;
  onDelete: () => Promise<boolean>;
  onNotice: (text: string) => void;
}) {
  const [mode, setMode] = useState<"idle" | "reset" | "delete">("idle");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<boolean>, message: string) {
    setBusy(true);
    const ok = await action();
    setBusy(false);
    if (!ok) return;
    setMode("idle");
    setPassword("");
    onNotice(message);
  }

  const status = account.builtin
    ? "Built-in sign-in from the server settings"
    : !account.active
      ? "Turned off"
      : account.last_login_at
        ? `Last signed in ${when(account.last_login_at)}${account.signed_in ? " · signed in now" : ""}`
        : "Has not signed in yet";

  return (
    <article className={`rounded-2xl border bg-white px-4 py-4 shadow-sm ${account.active ? "border-line" : "border-dashed border-ink/20 opacity-75"}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{account.display_name || account.email}</span>
            <RoleBadgeLight role={account.role} />
            {isYou && <span className="text-xs text-ink/50">You</span>}
          </p>
          {account.display_name && <p className="truncate text-sm text-ink/60">{account.email}</p>}
          <p className="mt-1 text-xs text-ink/50">{status}</p>
        </div>
        {!account.builtin && mode === "idle" && (
          <div className="flex flex-wrap items-center gap-2">
            <select
              aria-label={`Role for ${account.email}`}
              className="field h-8 py-0 text-xs"
              value={account.role}
              disabled={busy}
              onChange={(event) =>
                void run(() => onPatch({ role: event.target.value }), `${account.email} is now ${event.target.value === "admin" ? "an admin" : "a recruiter"}. They were signed out to pick up the change.`)
              }
            >
              <option value="recruiter">Recruiter</option>
              <option value="admin">Admin</option>
            </select>
            <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => setMode("reset")}>
              Reset password
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() =>
                void run(
                  () => onPatch({ active: !account.active }),
                  account.active ? `${account.email} is turned off and signed out.` : `${account.email} can sign in again.`,
                )
              }
            >
              {account.active ? "Turn off" : "Turn on"}
            </Button>
            <Button type="button" size="sm" variant="danger" disabled={busy} onClick={() => setMode("delete")}>
              Remove
            </Button>
          </div>
        )}
      </div>

      {mode === "reset" && (
        <form
          className="mt-4 flex flex-wrap items-end gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            void run(() => onPatch({ password }), `New password saved for ${account.email}. They were signed out everywhere.`);
          }}
        >
          <div className="flex min-w-64 flex-1 flex-col gap-1.5">
            <Label htmlFor={`reset-${account.id}`}>New password</Label>
            <PasswordInput id={`reset-${account.id}`} value={password} onChange={setPassword} show={show} onToggle={() => setShow(!show)} minimum={minimum} />
          </div>
          <Button type="submit" size="sm" disabled={busy || password.length < minimum}>
            Save password
          </Button>
          <Button type="button" size="sm" variant="outline" onClick={() => { setMode("idle"); setPassword(""); }}>
            Cancel
          </Button>
        </form>
      )}

      {mode === "delete" && (
        <div className="mt-4 rounded-xl border border-red-200 bg-red-50/60 p-3">
          <p className="text-sm text-red-900">
            Remove {account.email}? They are signed out and cannot sign in again. Their submissions, comments, and history stay on file. Turning the
            account off is reversible; removing it is not.
          </p>
          <div className="mt-3 flex gap-2">
            <Button type="button" size="sm" variant="danger" disabled={busy} onClick={() => void run(onDelete, `${account.email} was removed.`)}>
              Remove permanently
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={() => setMode("idle")}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </article>
  );
}

function RoleBadgeLight({ role }: { role: Role }) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
        role === "admin" ? "bg-amber-100 text-amber-900 ring-1 ring-amber-300" : "bg-pine/10 text-pine-deep ring-1 ring-pine/30"
      }`}
    >
      {role === "admin" ? "Admin" : "Recruiter"}
    </span>
  );
}

function PasswordInput({
  id,
  value,
  onChange,
  show,
  onToggle,
  minimum,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  show: boolean;
  onToggle: () => void;
  minimum: number;
}) {
  return (
    <div className="relative">
      <Input
        id={id}
        type={show ? "text" : "password"}
        autoComplete="new-password"
        value={value}
        minLength={minimum}
        onChange={(event) => onChange(event.target.value)}
        className="pr-10"
        required
      />
      <button
        type="button"
        onClick={onToggle}
        aria-label={show ? "Hide password" : "Show password"}
        className="absolute inset-y-0 right-0 grid w-10 place-items-center text-ink/50 hover:text-ink"
      >
        {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
      </button>
    </div>
  );
}
