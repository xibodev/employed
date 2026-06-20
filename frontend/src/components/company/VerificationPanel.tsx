"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useTranslations } from "next-intl";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { verificationVariant } from "@/components/company/utils";
import { ApiError, getCompany, verifyCompanyDomain } from "@/lib/api";
import type { CompanyMembership } from "@/lib/tenant";
import type { Company } from "@/lib/types";

type VerifyMethod = "dns" | "member_email";

/** Verification status overview plus a domain-verify action (R9.1, R10.1). */
export function VerificationPanel({ activeCompany }: { activeCompany: CompanyMembership }) {
  const t = useTranslations("verification");
  const companyId = activeCompany.id;

  const [company, setCompany] = useState<Company | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [domain, setDomain] = useState("");
  const [method, setMethod] = useState<VerifyMethod>("dns");
  const [expectedToken, setExpectedToken] = useState("");
  const [isVerifying, setIsVerifying] = useState(false);

  const loadCompany = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      setCompany(await getCompany(companyId));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : t("loadError"));
    } finally {
      setIsLoading(false);
    }
  }, [companyId, t]);

  useEffect(() => {
    void loadCompany();
  }, [loadCompany]);

  const handleVerify = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!domain.trim()) {
      return;
    }
    if (method === "dns" && !expectedToken.trim()) {
      setError(t("tokenRequired"));
      return;
    }
    setIsVerifying(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await verifyCompanyDomain(companyId, {
        domain: domain.trim(),
        method,
        expected_token: method === "dns" ? expectedToken.trim() : undefined,
      });
      setCompany(updated);
      setDomain("");
      setExpectedToken("");
      setNotice(t("verifySuccess"));
    } catch (verifyError) {
      if (verifyError instanceof ApiError && verifyError.status === 422) {
        setError(t("verifyFailed"));
      } else if (verifyError instanceof ApiError && verifyError.status === 403) {
        setError(t("forbidden"));
      } else {
        setError(verifyError instanceof Error ? verifyError.message : t("verifyError"));
      }
    } finally {
      setIsVerifying(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-white/10 bg-[#16213e] p-6">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-[#e4e4e7]">{t("statusTitle")}</h2>
          {company ? (
            <Badge variant={verificationVariant(company.verification_status)}>
              {t(`status.${company.verification_status}`)}
            </Badge>
          ) : null}
        </div>

        {isLoading ? (
          <p className="mt-4 text-sm text-[#a1a1aa]">{t("loading")}</p>
        ) : company ? (
          <div className="mt-4">
            <h3 className="text-xs uppercase tracking-[0.2em] text-[#71717a]">{t("verifiedDomainsTitle")}</h3>
            {company.verified_email_domains.length > 0 ? (
              <div className="mt-2 flex flex-wrap gap-2">
                {company.verified_email_domains.map((verifiedDomain) => (
                  <Badge key={verifiedDomain} variant="success">
                    {verifiedDomain}
                  </Badge>
                ))}
              </div>
            ) : (
              <p className="mt-2 text-sm text-[#71717a]">{t("noVerifiedDomains")}</p>
            )}
          </div>
        ) : null}
      </div>

      <form onSubmit={handleVerify} className="space-y-4 rounded-2xl border border-white/10 bg-[#16213e] p-6">
        <div>
          <h2 className="text-lg font-semibold text-[#e4e4e7]">{t("verifyTitle")}</h2>
          <p className="mt-1 text-sm text-[#a1a1aa]">{t("verifySubtitle")}</p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Input
            label={t("domainLabel")}
            name="domain"
            value={domain}
            onChange={(event) => setDomain(event.target.value)}
            placeholder="example.com"
            required
          />
          <Select
            label={t("methodLabel")}
            name="method"
            value={method}
            onChange={(event) => setMethod(event.target.value as VerifyMethod)}
            options={[
              { value: "dns", label: t("methodDns") },
              { value: "member_email", label: t("methodMemberEmail") },
            ]}
          />
        </div>

        {method === "dns" ? (
          <Input
            label={t("tokenLabel")}
            name="expectedToken"
            value={expectedToken}
            onChange={(event) => setExpectedToken(event.target.value)}
            hint={t("tokenHint")}
            required
          />
        ) : (
          <p className="text-xs text-[#a1a1aa]">{t("memberEmailHint")}</p>
        )}

        {notice ? <p className="rounded-xl bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">{notice}</p> : null}
        {error ? <p className="rounded-xl bg-rose-500/10 px-3 py-2 text-xs text-rose-300">{error}</p> : null}

        <Button type="submit" disabled={isVerifying || !domain.trim()}>
          {isVerifying ? t("verifying") : t("verifyAction")}
        </Button>
      </form>
    </div>
  );
}
