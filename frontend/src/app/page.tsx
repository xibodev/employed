import Link from "next/link";
import { headers } from "next/headers";
import { getTranslations } from "next-intl/server";

import Container from "@/components/layout/Container";
import FeaturedStrip from "@/components/jobs/FeaturedStrip";
import JobGrid from "@/components/jobs/JobGrid";
import { Button, buttonStyles } from "@/components/ui/Button";
import { getJobs } from "@/lib/api";
import { resolveMarketFromHeaders } from "@/lib/market";
import { buildMetadata } from "@/lib/seo";
import type { Job } from "@/lib/types";
import { countryLabel, pickRandomItems } from "@/lib/utils";

async function loadHomeData(host: string, country: string) {
  try {
    const [featuredResponse, recentResponse] = await Promise.all([
      getJobs({ country, featured: true, status: "active", per_page: 6, page: 1 }, { host }),
      getJobs({ country, status: "active", per_page: 10, page: 1 }, { host })
    ]);

    const featured = pickRandomItems(featuredResponse.items, 3);
    const featuredIds = new Set(featured.map((job) => job.id));
    const recent = recentResponse.items.filter((job) => !featuredIds.has(job.id)).slice(0, 10);

    return { featured, recent };
  } catch {
    return { featured: [] as Job[], recent: [] as Job[] };
  }
}

export async function generateMetadata() {
  const requestHeaders = await headers();
  const market = resolveMarketFromHeaders(requestHeaders);
  return buildMetadata({
    title: "Home",
    description: `${market.tagline} Browse featured jobs and the latest active listings in ${market.country}.`,
    market,
    pathname: "/"
  });
}

export default async function HomePage() {
  const requestHeaders = await headers();
  const market = resolveMarketFromHeaders(requestHeaders);
  const host = requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host") ?? market.host;
  const { featured, recent } = await loadHomeData(host, market.country);
  const t = await getTranslations("home");
  const tCountries = await getTranslations("countries");

  return (
    <Container className="space-y-10">
      <section className="hero-surface overflow-hidden px-6 py-10 sm:px-10 sm:py-14">
        <div className="grid gap-8 lg:grid-cols-[minmax(0,1.3fr)_minmax(280px,0.7fr)] lg:items-center">
          <div className="space-y-5">
            <p className="text-sm font-semibold uppercase tracking-[0.28em] text-indigo-200">{market.siteName}</p>
            <h1 className="max-w-3xl text-4xl font-black tracking-tight text-white sm:text-5xl">{t("heroTagline")}</h1>
            <p className="max-w-2xl text-lg leading-8 text-zinc-200">
              {t("heroBody", { country: countryLabel(tCountries, market.country) })}
            </p>
            <div className="flex flex-wrap gap-3">
              <Link href="/jobs" className={buttonStyles({ variant: "primary", size: "lg" })}>
                {t("browseJobsCta")}
              </Link>
              <Link href="/jobs/new" className={buttonStyles({ variant: "secondary", size: "lg" })}>
                {t("postJobCta")}
              </Link>
            </div>
          </div>
          <div className="card-surface grid gap-4 p-6 text-sm text-zinc-300">
            <div>
              <p className="text-zinc-500">{t("featuredListingLabel")}</p>
              <p className="mt-2 text-2xl font-semibold text-zinc-100">{market.featuredJob.label}</p>
            </div>
            <p>{t("featuredListingHelper")}</p>
            <Button variant="secondary">{t("supportedPayments", { providers: market.paymentProviders.join(", ") })}</Button>
          </div>
        </div>
      </section>

      <FeaturedStrip jobs={featured} />

      <section className="space-y-5">
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.22em] text-indigo-300">{t("recentJobsKicker")}</p>
            <h2 className="text-2xl font-semibold text-zinc-100">{t("latestActiveRoles")}</h2>
          </div>
          <Link href="/jobs" className="text-sm font-medium text-indigo-300 hover:text-indigo-200">
            {t("viewAllJobs")} →
          </Link>
        </div>
        <JobGrid jobs={recent} locale={market.locale} emptyMessage={t("noJobs")} />
      </section>
    </Container>
  );
}
