"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/Button";
import { companyToMembership } from "@/components/company/utils";
import { useTenant } from "@/contexts/TenantContext";
import { ApiError, getCompany } from "@/lib/api";
import { upsertStoredMembership } from "@/lib/tenant-store";

/**
 * Lets a user pick which company they are acting on behalf of, and link an
 * existing company they belong to by id. The active company is the canonical
 * source for every company segment (R2.11).
 */
export function CompanySwitcher() {
  const t = useTranslations("company");
  const { activeCompany, memberships, setActiveCompany } = useTenant();
  const [companyId, setCompanyId] = useState("");
  const [isLinking, setIsLinking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLink = async () => {
    const trimmed = companyId.trim();
    if (!trimmed) {
      return;
    }
    setIsLinking(true);
    setError(null);
    try {
      const company = await getCompany(trimmed);
      upsertStoredMembership(companyToMembership(company));
      setActiveCompany(company.id);
      setCompanyId("");
    } catch (linkError) {
      if (linkError instanceof ApiError && linkError.status === 404) {
        setError(t("linkNotFound"));
      } else {
        setError(linkError instanceof Error ? linkError.message : t("linkError"));
      }
    } finally {
      setIsLinking(false);
    }
  };

  return (
    <div className="space-y-4 rounded-2xl border border-white/10 bg-[#16213e] p-5">
      <div>
        <h2 className="text-sm font-semibold text-[#e4e4e7]">{t("switcherTitle")}</h2>
        <p className="mt-1 text-xs text-[#71717a]">{t("switcherHint")}</p>
      </div>

      {memberships.length > 0 ? (
        <label className="flex flex-col gap-2 text-sm text-zinc-300">
          <span className="font-medium text-zinc-100">{t("activeCompanyLabel")}</span>
          <select
            value={activeCompany?.id ?? ""}
            onChange={(event) => setActiveCompany(event.target.value || null)}
            className="h-11 rounded-xl border border-zinc-800 bg-[#111827] px-3 text-zinc-100 outline-none transition focus:border-indigo-500"
          >
            {memberships.map((membership) => (
              <option key={membership.id} value={membership.id}>
                {membership.name} · {t(`status.${membership.status}`)}
              </option>
            ))}
          </select>
        </label>
      ) : (
        <p className="text-xs text-[#a1a1aa]">{t("noMemberships")}</p>
      )}

      <div className="flex flex-col gap-2">
        <label className="flex flex-col gap-2 text-sm text-zinc-300" htmlFor="link-company-id">
          <span className="font-medium text-zinc-100">{t("linkLabel")}</span>
          <input
            id="link-company-id"
            value={companyId}
            onChange={(event) => setCompanyId(event.target.value)}
            placeholder={t("linkPlaceholder")}
            className="h-11 rounded-xl border border-zinc-800 bg-[#111827] px-3 text-zinc-100 outline-none transition placeholder:text-zinc-500 focus:border-indigo-500"
          />
        </label>
        <div>
          <Button variant="secondary" size="sm" disabled={isLinking || !companyId.trim()} onClick={() => void handleLink()}>
            {isLinking ? t("linking") : t("linkAction")}
          </Button>
        </div>
        {error ? <p className="text-xs text-rose-400">{error}</p> : null}
      </div>
    </div>
  );
}
