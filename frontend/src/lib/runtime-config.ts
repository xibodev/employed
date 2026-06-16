/**
 * EMP-012 (runtime config): mutable config resolves at runtime, never baked.
 *
 * Next.js inlines NEXT_PUBLIC_* values into the client bundle at build time,
 * which made the API URL and reCAPTCHA site key rebuild-only config. The
 * server layout injects window.__ENV from process.env on every request and
 * client code prefers it over the inlined values — so changing these values
 * is a container restart, not an image rebuild.
 */

export interface RuntimeEnv {
  NEXT_PUBLIC_API_URL?: string;
  NEXT_PUBLIC_RECAPTCHA_SITE_KEY?: string;
}

declare global {
  interface Window {
    __ENV?: RuntimeEnv;
  }
}

export function runtimeEnv(): RuntimeEnv {
  if (typeof window !== "undefined") {
    return window.__ENV ?? {};
  }
  // Server side: process.env is read at request time (runtime), not bundled.
  return {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
    NEXT_PUBLIC_RECAPTCHA_SITE_KEY: process.env.NEXT_PUBLIC_RECAPTCHA_SITE_KEY,
  };
}

export function getApiUrl(): string {
  // Build-time inlined value remains the fallback for environments where the
  // runtime script has not loaded (e.g. static error pages).
  return runtimeEnv().NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
}

export function getRecaptchaSiteKey(): string | undefined {
  return runtimeEnv().NEXT_PUBLIC_RECAPTCHA_SITE_KEY || process.env.NEXT_PUBLIC_RECAPTCHA_SITE_KEY || undefined;
}
