"use client";

import { createContext, type ReactNode, useContext } from "react";

export type Capability = "delete" | "burden" | "settings" | "edit_jobs" | "bulk_ingest" | "knowledge_edit" | "export" | "team";
export type Role = "admin" | "recruiter";

export type DeskAccount = {
  ready: boolean;
  role: Role;
  name: string;
  email: string;
  can: Partial<Record<Capability, boolean>>;
};

export const ROLE_LABEL: Record<Role, string> = { admin: "Admin", recruiter: "Recruiter" };

/** Completes "Only admins can …". */
export const CAPABILITY_LABEL: Record<Capability, string> = {
  delete: "delete records",
  burden: "use the burden calculator",
  settings: "change desk settings",
  edit_jobs: "edit jobs",
  bulk_ingest: "run folder and cloud imports",
  knowledge_edit: "edit company documents",
  export: "export reports",
  team: "manage team accounts",
};

const LOADING: DeskAccount = { ready: false, role: "recruiter", name: "", email: "", can: {} };

const DeskContext = createContext<DeskAccount>(LOADING);

export function DeskProvider({ account, children }: { account: DeskAccount | null; children: ReactNode }) {
  return <DeskContext.Provider value={account ?? LOADING}>{children}</DeskContext.Provider>;
}

export function useDesk(): DeskAccount {
  return useContext(DeskContext);
}

/** True only once the session has loaded and grants the capability, so admin-only controls never flash for recruiters. */
export function useCan(capability: Capability): boolean {
  const desk = useDesk();
  return desk.ready && Boolean(desk.can[capability]);
}

/** The name to show beside the role badge; falls back to the email when the name only repeats the role. */
export function shownName(account: DeskAccount): string {
  const name = account.name.trim();
  if (!name || name.toLowerCase() === ROLE_LABEL[account.role].toLowerCase()) return account.email;
  return name;
}

export function readAccount(data: unknown): DeskAccount | null {
  if (!data || typeof data !== "object") return null;
  const value = data as Record<string, unknown>;
  const role: Role = value.role === "admin" ? "admin" : "recruiter";
  return {
    ready: true,
    role,
    name: typeof value.name === "string" ? value.name : "",
    email: typeof value.email === "string" ? value.email : "",
    can: (value.can && typeof value.can === "object" ? value.can : {}) as DeskAccount["can"],
  };
}
