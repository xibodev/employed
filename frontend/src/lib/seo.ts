import type { Metadata } from "next";

import { marketBaseUrl } from "@/lib/market";
import type { Job, MarketConfig } from "@/lib/types";
import { stripHtml, truncateHtml } from "@/lib/utils";

export function marketUrl(market: MarketConfig, pathname = "/"): string {
  const normalisedPath = pathname.startsWith("/") ? pathname : `/${pathname}`;
  return `${marketBaseUrl(market.key)}${normalisedPath}`;
}

export function pageTitle(title: string, market: MarketConfig): string {
  return `${title} | ${market.siteName}`;
}

export function buildMetadata({
  title,
  description,
  market,
  pathname = "/"
}: {
  title: string;
  description: string;
  market: MarketConfig;
  pathname?: string;
}): Metadata {
  const url = marketUrl(market, pathname);

  return {
    metadataBase: new URL(marketBaseUrl(market.key)),
    title: pageTitle(title, market),
    description,
    alternates: {
      canonical: url
    },
    openGraph: {
      type: "website",
      url,
      title: pageTitle(title, market),
      description,
      siteName: market.siteName,
      locale: market.locale
    },
    twitter: {
      card: "summary_large_image",
      title: pageTitle(title, market),
      description
    }
  };
}

export function buildJobMetadata(job: Job, market: MarketConfig): Metadata {
  const description = truncateHtml(job.html_description ?? job.description ?? "", 180) || market.tagline;
  const heading = job.company ? `${job.title} at ${job.company}` : job.title;

  return buildMetadata({
    title: heading,
    description,
    market,
    pathname: `/jobs/${job.id}`
  });
}

export function buildJobPostingJsonLd(job: Job, market: MarketConfig) {
  const payload = {
    "@context": "https://schema.org",
    "@type": "JobPosting",
    title: job.title,
    description: stripHtml(job.html_description ?? job.description ?? ""),
    datePosted: job.published_at ?? job.created_at,
    employmentType: job.jobtype,
    hiringOrganization: {
      "@type": "Organization",
      name: job.company ?? market.siteName
    },
    jobLocation: job.remote
      ? undefined
      : {
          "@type": "Place",
          address: {
            "@type": "PostalAddress",
            addressCountry: job.country,
            addressLocality: job.location ?? undefined
          }
        },
    applicantLocationRequirements: job.remote
      ? {
          "@type": "Country",
          name: job.country
        }
      : undefined,
    baseSalary:
      job.salary_currency && (job.salary_min != null || job.salary_max != null)
        ? {
            "@type": "MonetaryAmount",
            currency: job.salary_currency,
            value: {
              "@type": "QuantitativeValue",
              minValue: job.salary_min ?? undefined,
              maxValue: job.salary_max ?? undefined,
              unitText: job.salary_period ?? undefined
            }
          }
        : undefined,
    directApply: Boolean(job.url || job.apply_whatsapp),
    url: marketUrl(market, `/jobs/${job.id}`)
  };

  return payload;
}
