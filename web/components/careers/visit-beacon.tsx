"use client";

import { useEffect } from "react";

import { trackVisit } from "@/lib/visit";

export function VisitBeacon({ path }: { path: string }) {
  useEffect(() => {
    trackVisit("page", path);
  }, [path]);
  return null;
}
