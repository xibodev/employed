/**
 * Server component that exposes runtime-mutable config to the browser
 * (EMP-012, Rule 11). Rendered per request, so the values reflect the
 * container's current environment — not the build.
 */
export function RuntimeEnvScript() {
  const env = {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "",
    NEXT_PUBLIC_RECAPTCHA_SITE_KEY: process.env.NEXT_PUBLIC_RECAPTCHA_SITE_KEY ?? "",
  };

  const payload = JSON.stringify(env).replace(/</g, "\\u003c");

  return (
    <script
      id="runtime-env"
      dangerouslySetInnerHTML={{ __html: `window.__ENV=${payload};` }}
    />
  );
}
