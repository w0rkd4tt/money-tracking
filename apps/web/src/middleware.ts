import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Routes that do NOT require a session cookie.
// Everything else redirects to /unlock if no cookie is present.
const PUBLIC_PATH_PREFIXES = ["/setup", "/unlock", "/recover", "/api", "/_next", "/favicon"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  for (const p of PUBLIC_PATH_PREFIXES) {
    if (pathname === p || pathname.startsWith(p + "/") || pathname.startsWith(p + ".")) {
      return NextResponse.next();
    }
  }

  const cookie = request.cookies.get("mt_session");
  if (!cookie) {
    // Not even a cookie → send to /unlock. /unlock page itself handles
    // "not configured → /setup" via its server-side status check.
    const url = request.nextUrl.clone();
    url.pathname = "/unlock";
    url.search = "";
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  // Match everything except static/image optimizations and obviously static asset paths.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)"],
};
