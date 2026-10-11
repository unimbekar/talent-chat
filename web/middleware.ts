import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  if (request.nextUrl.pathname === "/chat" || request.nextUrl.pathname === "/finetuning") {
    const url = request.nextUrl.clone();
    url.pathname = "/jobs";
    return NextResponse.redirect(url);
  }
  const response = NextResponse.next();
  const extra = process.env.PUBLIC_FRAME_ANCESTOR || "";
  const ancestors = ["'self'", extra].filter(Boolean).join(" ");
  response.headers.set("Content-Security-Policy", `frame-ancestors ${ancestors}`);
  return response;
}

export const config = { matcher: ["/chat", "/finetuning", "/jobs"] };
