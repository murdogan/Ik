import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const TENANT_REFRESH_COOKIE_NAMES = ["wf_refresh", "__Host-wf_refresh"] as const;
const PLATFORM_REFRESH_COOKIE_NAMES = [
  "wf_platform_refresh",
  "__Host-wf_platform_refresh",
] as const;

export function proxy(request: NextRequest) {
  const pathname = request.nextUrl.pathname;
  if (pathname === "/platform/login") {
    return NextResponse.next();
  }

  const isPlatformRoute =
    pathname === "/platform" || pathname.startsWith("/platform/");
  const refreshCookieNames = isPlatformRoute
    ? PLATFORM_REFRESH_COOKIE_NAMES
    : TENANT_REFRESH_COOKIE_NAMES;
  const hasRefreshCookie = refreshCookieNames.some((name) =>
    request.cookies.has(name),
  );
  if (!hasRefreshCookie) {
    return NextResponse.redirect(
      new URL(isPlatformRoute ? "/platform/login" : "/login", request.url),
    );
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/users/:path*",
    "/audit/:path*",
    "/platform/:path*",
  ],
};
