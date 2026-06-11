import { headers } from "next/headers";
import { getTranslations } from "next-intl/server";

import Container from "@/components/layout/Container";
import FeaturedStrip from "@/components/jobs/FeaturedStrip";
import JobFilters from "@/components/jobs/JobFilters";
import JobGrid from "@/components/jobs/JobGrid";
import Pagination from "@/components/jobs/Pagination";
import { getJobs } from "@/lib/api";
import { resolveMarketFromHeaders } from "@/lib/market";
import { buildMetadata } from "@/lib/seo";
import { PER_PAGE_OPTIONS } from "@/lib/constants";
import type { Job, JobsQuery } from "@/lib/types";
import { countryLabel, pickRandomItems } from "@/lib/utils";

function toPositiveInt(value: string | undefined, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

async function loadBrowseData(host: string, query: JobsQuery & { country: string }) {
  try {
    const [featuredResponse, jobsResponse] = await Promise.all([
      getJobs({ country: query.country, featured: true, status: "active", per_page: 6, page: 1 }, { host }),
      getJobs(query, { host })
    ]);

    return {
      featured: pickRandomItems(featuredResponse.items, 3),
      jobs: jobsResponse.items,
      total: jobsResponse.total,
      totalPages: jobsResponse.total_pages,
      page: jobsResponse.page,
      perPage: jobsResponse.per_page
    };
  } catch {
    return {
      featured: [] as Job[],
      jobs: [] as Job[],
      total: 0,
      totalPages: 0,
      page: query.page ?? 1,
      perPage: query.per_page ?? 12
    };
  }
}

export async function generateMetadata() {
  const requestHeaders = await headers();
  const market = resolveMarketFromHeaders(requestHeaders);
  return buildMetadata({
    title: "Browse jobs",
    description: `Search public job listings in ${market.country} by title, company, location, remote status, and employment type.`,
    market,
    pathname: "/jobs"
  });
}

export default async function JobsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const requestHeaders = await headers();
  const market = resolveMarketFromHeaders(requestHeaders);
  const host = requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host") ?? market.host;
  const t = await getTranslations("jobsList");
  const tCountries = await getTranslations("countries");

  const page = toPositiveInt(typeof params.page === "string" ? params.page : undefined, 1);
  const perPage = toPositiveInt(typeof params.per_page === "string" ? params.per_page : undefined, PER_PAGE_OPTIONS[0]);
  const search = typeof params.search === "string" ? params.search : "";
  const jobType = typeof params.job_type === "string" ? params.job_type : "";
  const remote = params.remote === "true";

  const data = await loadBrowseData(host, {
    country: market.country,
    status: "active",
    search,
    job_type: jobType || undefined,
    remote: remote || undefined,
    page,
    per_page: perPage
  });

  return (
    <Container className="space-y-8">
      <section className="space-y-3">
        <p className="text-sm font-semibold uppercase tracking-[0.22em] text-indigo-300">{t("kicker")}</p>
        <h1 className="text-4xl font-bold tracking-tight text-zinc-100">{t("title", { country: countryLabel(tCountries, market.country) })}</h1>
        <p className="max-w-3xl text-lg text-zinc-400">{t("subtitle")}</p>
      </section>

      <JobFilters initialSearch={search} initialJobType={jobType} initialRemote={remote} />
      <FeaturedStrip jobs={data.featured} />

      <section className="space-y-4">
        {data.total > 0 ? (
          <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-zinc-400">
            <p className="font-medium text-zinc-100">{t("jobsFound", { count: data.total })}</p>
            <p>{t("featuredSeparate")}</p>
          </div>
        ) : null}
        <JobGrid jobs={data.jobs} locale={market.locale} />
      </section>

      {data.total > 0 ? (
        <Pagination
          page={data.page}
          perPage={data.perPage}
          total={data.total}
          totalPages={data.totalPages}
          pathname="/jobs"
          params={{ search, job_type: jobType, remote: remote || undefined }}
        />
      ) : null}
    </Container>
  );
}
