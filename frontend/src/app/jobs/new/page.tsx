import { headers } from "next/headers";
import { getTranslations } from "next-intl/server";

import Container from "@/components/layout/Container";
import JobForm from "@/components/jobs/JobForm";
import { resolveMarketFromHeaders } from "@/lib/market";
import { buildMetadata } from "@/lib/seo";
import { countryLabel } from "@/lib/utils";

export async function generateMetadata() {
  const requestHeaders = await headers();
  const market = resolveMarketFromHeaders(requestHeaders);
  return buildMetadata({
    title: "Post a job",
    description: `Publish a new public job listing for ${market.country}. Featured upgrades are priced per market and anonymous posters use reCAPTCHA verification.`,
    market,
    pathname: "/jobs/new"
  });
}

export default async function NewJobPage() {
  const requestHeaders = await headers();
  const market = resolveMarketFromHeaders(requestHeaders);
  const t = await getTranslations("postJob");
  const tCountries = await getTranslations("countries");

  return (
    <Container className="space-y-8">
      <section className="space-y-3">
        <p className="text-sm font-semibold uppercase tracking-[0.22em] text-indigo-300">{t("kicker")}</p>
        <h1 className="text-4xl font-bold tracking-tight text-zinc-100">{t("title", { country: countryLabel(tCountries, market.country) })}</h1>
        <p className="max-w-3xl text-lg text-zinc-400">{t("subtitle")}</p>
      </section>
      <JobForm mode="create" />
    </Container>
  );
}
