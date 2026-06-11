import type { MetadataRoute } from "next";

import { appBaseUrl } from "@/lib/market";

export default function robots(): MetadataRoute.Robots {
  // EMP-024: base URL comes from NEXT_PUBLIC_APP_URL (Rule 2), never source.
  return {
    rules: { userAgent: "*", allow: "/" },
    sitemap: `${appBaseUrl()}/sitemap.xml`,
  };
}
