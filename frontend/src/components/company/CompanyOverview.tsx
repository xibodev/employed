"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { Badge } from "@/components/ui/Badge";
import { buttonStyles } from "@/components/ui/Button";
import { verificationVariant } from "@/components/company/utils";
import { getCompany } from "@/lib/api";
import type { CompanyMembership } from "@/lib/tenant";
import type { Company } from "@/lib/types";

/** Company management overview for the active company (R2.6 dashboard surface). */
export function CompanyOverview({ activeCompany }: { activeCompany: CompanyMembership }) {
  const t = useTranslations("company");
  const [company, setCompany] = useState<Company | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const loadCompany = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      setCompany(await getCompany(activeCompany.id));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : t("loadError"));
    } finally {
      setIsLoading(false);
    }
  }, [activeCompany.id, t]);

  useEffect(() => {
    void loadCompany();
  }, [loadCompany]);

  if (isLoading) {
    return <p className="text-sm text-[#a1a1aa]">{t("loading")}</p>;
  }

  if (error) {
    return <p className="rounded-2xl bg-rose-500/10 px-4 py-3 text-sm text-rose-300">{error}</p>;
  }

  if (!company) {
    return null;
  }

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-white/10 bg-[#16213e] p-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="text-2xl font-semibold text-[#e4e4e7]">{company.name}</h2>
            <p className="mt-1 text-sm text-[#a1a1aa]">{t("slugLabel", { slug: company.slug })}</p>
            {company.website ? (
              <a
                href={company.website}
                target="_blank"
                rel="noreferrer"
                className="mt-2 inline-block text-sm text-indigo-300 hover:text-indigo-200"
              >
                {company.website}
              </a>
            ) : null}
          </div>
          <Badge variant={verificationVariant(company.verification_status)}>
            {t(`verificationStatus.${company.verification_status}`)}
          </Badge>
        </div>

        {company.description ? (
          <p className="mt-4 text-sm text-[#d4d4d8]">{company.description}</p>
        ) : (
          <p className="mt-4 text-sm text-[#71717a]">{t("noDescription")}</p>
        )}

        <dl className="mt-6 grid gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase tracking-[0.2em] text-[#71717a]">{t("marketLabel")}</dt>
            <dd className="mt-1 text-sm text-[#e4e4e7]">{company.market.toUpperCase()}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-[0.2em] text-[#71717a]">{t("roleLabel")}</dt>
            <dd className="mt-1 text-sm text-[#e4e4e7]">{t(`role.${activeCompany.role}`)}</dd>
          </div>
        </dl>
      </div>

      <div className="rounded-2xl border border-white/10 bg-[#16213e] p-6">
        <h3 className="text-sm font-semibold text-[#e4e4e7]">{t("trustBadgesTitle")}</h3>
        {company.trust_badges.length > 0 ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {company.trust_badges.map((badge) => (
              <Badge key={badge} variant="info">
                {badge}
              </Badge>
            ))}
          </div>
        ) : (
          <p className="mt-2 text-sm text-[#71717a]">{t("noTrustBadges")}</p>
        )}
      </div>

      <div className="flex flex-wrap gap-3">
        <Link href="/company/members" className={buttonStyles({ variant: "secondary", size: "sm" })}>
          {t("manageMembersAction")}
        </Link>
        <Link href="/company/verification" className={buttonStyles({ variant: "secondary", size: "sm" })}>
          {t("manageVerificationAction")}
        </Link>
      </div>
    </div>
  );
}
