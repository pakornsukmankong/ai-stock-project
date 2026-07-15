import { NextResponse } from "next/server";
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

/**
 * OAuth (and email-confirmation) callback. Supabase redirects here with a
 * one-time `code`; we exchange it for a session cookie, then send the user on to
 * `next` (defaults to the dashboard).
 *
 * This route must stay outside the middleware's auth gate — at this point the
 * session cookie does not exist yet, so gating it would bounce the user back to
 * /login and the login could never complete.
 */
export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  // Only allow relative paths, so `next` can't be used as an open redirect.
  const nextParam = searchParams.get("next") ?? "/dashboard";
  const next = nextParam.startsWith("/") ? nextParam : "/dashboard";

  if (code) {
    const cookieStore = await cookies();
    const supabase = createServerClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
      {
        cookies: {
          getAll() {
            return cookieStore.getAll();
          },
          setAll(cookiesToSet) {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options)
            );
          },
        },
      }
    );

    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      // Behind a proxy (Vercel), request.url's origin is the internal host, so
      // prefer the forwarded host to build the user-facing redirect URL.
      const forwardedHost = request.headers.get("x-forwarded-host");
      const isLocalEnv = process.env.NODE_ENV === "development";
      if (isLocalEnv) {
        return NextResponse.redirect(`${origin}${next}`);
      }
      if (forwardedHost) {
        return NextResponse.redirect(`https://${forwardedHost}${next}`);
      }
      return NextResponse.redirect(`${origin}${next}`);
    }
  }

  // No code, or the exchange failed — send back to login with a flag to surface.
  return NextResponse.redirect(`${origin}/login?error=oauth`);
}
