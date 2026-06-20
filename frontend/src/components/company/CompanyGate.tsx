"use client";

import { useEffect, type ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { buttonStyles } from "@/components/ui/Button";
import { CompanySectionNav } from "@/components/company/CompanySectionNav";
import { CompanySwitcher } from "@/components/company/CompanySwitcher";
import { useAuth } from "@/contexts/AuthContext";
import { useTenant } from "@/contexts/TenantContext";
import type { CompanyMembership } from "@/lib/tenant";

interface CompanyGateProps {
  /** Section heading shown above the content. */
  title: string;
  /** Optional supporting copy under the heading. */
  subtitle?: string;
  /** Where to send unauthenticated users after sign-in. */
  redirectTo: string;
  /** Rendered with the resolved active company once authenticated. */
  children: (activeCompany: CompanyMembership) => ReactNode;
}

/**
 * Shared shell for the company segments: gates on authentication, renders the
 * section nav, and resolves the active company from the tenant context. When no
 * active company is selected it surfaces the switcher and a link to create one.
 */
export function CompanyGate({ title, subtitle, redirectTo, children }: CompanyGateProps) {
  const t = useTranslations("company");
  const router = useRouter();
  const { user, isLoading } = useAuth();
  const { activeCompany } = useTenant();

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace(`/sign-in?redirect=${encodeURIComponent(redirectTo)}`);
    }
  }, [isLoading, redirectTo, router, user]);

  return (
    <div className="min-h-screen bg-[#1a1a2e] px-4 py-12">
      <div className="mx-auto max-w-5xl space-y-8">
        <header className="space-y-4">
          <div>
            <h1 className="text-3xl font-semibold text-[#e4e4e7]">{title}</h1>
            {subtitle ? <p className="mt-2 text-sm text-[#a1a1aa]">{subtitle}</p> : null}
          </div>
          <CompanySectionNav />
        </header>

        {isLoading ? (
          <p className="text-sm text-[#a1a1aa]">{t("loading")}</p>
        ) : !user ? (
          <p className="text-sm text-[#a1a1aa]">{t("loading")}</p>
        ) : activeCompany ? (
          children(activeCompany)
        ) : (
          <div className="space-y-6">
            <div className="rounded-2xl border border-white/10 bg-[#16213e] p-6">
              <h2 className="text-lg font-semibold text-[#e4e4e7]">{t("noActiveTitle")}</h2>
              <p className="mt-2 text-sm text-[#a1a1aa]">{t("noActiveSubtitle")}</p>
              <Link href="/company" className={buttonStyles({ variant: "primary", size: "sm", className: "mt-4" })}>
                {t("goToDashboard")}
              </Link>
            </div>
            <CompanySwitcher />
          </div>
        )}
      </div>
    </div>
  );
}
