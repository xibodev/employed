import type { MarketConfig, MarketKey } from "@/lib/types";

/**
 * EMP-013/EMP-024: the deployment domain is never hardcoded
 * in source. All market hostnames derive from the single NEXT_PUBLIC_APP_URL
 * env var (the UAT/production apex). Local dev falls back to lvh.me-style
 * market subdomains.
 */
const DEFAULT_APP_URL = "http://localhost:3000";

export function appBaseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_APP_URL ?? DEFAULT_APP_URL;
  return raw.replace(/\/+$/, "");
}

function parseAppUrl(): { scheme: string; host: string } {
  try {
    const url = new URL(appBaseUrl());
    return { scheme: url.protocol.replace(":", ""), host: url.host };
  } catch {
    const stripped = appBaseUrl().replace(/^https?:\/\//, "").split("/")[0];
    return { scheme: "https", host: stripped || "localhost:3000" };
  }
}

/** Base host with any leading market label removed (mx.foo.tld -> foo.tld). */
function baseDomain(): string {
  const { host } = parseAppUrl();
  return host.replace(/^(mx|mz)\./, "");
}

function marketHost(key: MarketKey): string {
  const domain = baseDomain();
  if (domain.startsWith("localhost") || domain.includes("lvh.me")) {
    return `${key}.lvh.me`;
  }
  return `${key}.${domain}`;
}

/** Absolute base URL for a market (scheme from NEXT_PUBLIC_APP_URL). */
export function marketBaseUrl(key: MarketKey): string {
  const { scheme } = parseAppUrl();
  return `${scheme}://${marketHost(key)}`;
}

export const MARKETS = {
  mx: {
    key: "mx",
    country: "Mexico",
    locale: "es",
    siteName: "Employed MX",
    tagline: "Local jobs. Local hiring.",
    host: marketHost("mx"),
    featuredJob: { amount: 99900, currency: "mxn", label: "MX$999" },
    paymentProviders: ["stripe"]
  },
  mz: {
    key: "mz",
    country: "Mozambique",
    locale: "pt",
    siteName: "Employed MZ",
    tagline: "Local jobs. Local hiring.",
    host: marketHost("mz"),
    featuredJob: { amount: 250000, currency: "mzn", label: "MZN 2,500" },
    paymentProviders: ["mpesa", "emola", "stripe"]
  }
} satisfies Record<MarketKey, MarketConfig>;

export const DEFAULT_MARKET_KEY: MarketKey = "mz";

export function resolveMarketFromHostname(hostname?: string | null): MarketConfig {
  const host = (hostname ?? "").toLowerCase();
  const label = host.split(".")[0] as MarketKey;
  return MARKETS[label] ?? MARKETS[DEFAULT_MARKET_KEY];
}

export function resolveMarketFromHeaders(headersLike: Headers | { get(name: string): string | null }): MarketConfig {
  const host =
    headersLike.get("x-forwarded-host") ??
    headersLike.get("host") ??
    headersLike.get("x-original-host") ??
    undefined;

  return resolveMarketFromHostname(host);
}

export function buildMarketHostname(target: MarketKey, currentHostname: string): string {
  const lower = currentHostname.toLowerCase();

  if (lower.includes("lvh.me") || lower === "localhost") {
    return `${target}.lvh.me`;
  }

  const parts = lower.split(".");
  if (parts[0] in MARKETS) {
    parts[0] = target;
    return parts.join(".");
  }

  // Non-market host (e.g. the apex): derive from the env-configured domain.
  return MARKETS[target].host;
}
