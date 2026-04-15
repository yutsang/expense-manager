import { type NextRequest, NextResponse } from "next/server";

const PUBLIC_PATHS = ["/login", "/signup", "/forgot-password", "/reset-password", "/pricing", "/docs"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Skip auth in development — JWT auth is wired in a later phase
  if (process.env.NODE_ENV === "development") {
    return NextResponse.next();
  }

  const isPublic = pathname === "/" || PUBLIC_PATHS.some((p) => pathname.startsWith(p));
  const hasToken = request.cookies.has("aegis_access") || request.cookies.has("aegis_refresh");

  if (!isPublic && !hasToken) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }
  if (isPublic && hasToken) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|v1|_next/static|_next/image|favicon.ico).*)"],
};
