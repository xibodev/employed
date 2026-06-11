import type { MetadataRoute } from "next";

import { marketBaseUrl } from "@/lib/market";
import type { MarketKey } from "@/lib/types";

// EMP-024: market hosts derive from NEXT_PUBLIC_APP_URL (Rule 2).
const MARKET_KEYS: MarketKey[] = ["mz", "mx"];

const STATIC_PATHS = ["/", "/jobs", "/sign-in", "/sign-up"];

export default function sitemap(): MetadataRoute.Sitemap {
  const entries: MetadataRoute.Sitemap = [];

  for (const key of MARKET_KEYS) {
    const base = marketBaseUrl(key);
    for (const path of STATIC_PATHS) {
      entries.push({
        url: path === "/" ? base : `${base}${path}`,
        lastModified: new Date(),
        changeFrequency: path === "/" ? "daily" : "weekly",
        priority: path === "/" ? 1 : 0.8,
      });
    }
  }

  return entries;
}
