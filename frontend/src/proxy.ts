import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const REFRESH_COOKIE_NAMES = ["wf_refresh", "__Host-wf_refresh"] as const;

export function proxy(request: NextRequest) {
  const hasRefreshCookie = REFRESH_COOKIE_NAMES.some((name) => request.cookies.has(name));
  if (!hasRefreshCookie) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*", "/users/:path*"],
};
