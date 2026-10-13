import { NextRequest, NextResponse } from "next/server";

const api = process.env.API_INTERNAL_URL || "http://api:8000";

/** The careers page beacons here. Pass the address this server actually saw, not one the browser invented. */
export async function POST(request: NextRequest) {
  const ip = request.headers.get("x-visitor-address") || "";
  const body = await request.text();
  await fetch(`${api}/public/visit`, {
    method: "POST",
    headers: {
      "content-type": request.headers.get("content-type") || "application/json",
      "user-agent": request.headers.get("user-agent") || "",
      "x-visitor-address": ip,
    },
    body,
  }).catch(() => undefined);
  return new NextResponse(null, { status: 204 });
}
