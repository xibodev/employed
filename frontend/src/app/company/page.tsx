"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { CompanyOverview } from "@/components/company/CompanyOverview";
import { CompanySectionNav } from "@/components/company/CompanySectionNav";
import { CompanySwitcher } from "@/components/company/CompanySwitcher";
import { CreateCompanyForm } from "@/components/company/CreateCompanyForm";
import { useAuth } from "@/contexts/AuthContext";
import { useTenant } from "@/contexts/TenantContext";

function CompanyDashboardContent() {
  const t = useTranslations("company");
  const router = useRouter();
  const { user, isLoading } = useAuth();
  const { activeCompany } = useTenant();

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace("/sign-in?redirect=/company");
    }
  }, [isLoading, router, user]);

  return (
    <div className="min-h-screen bg-[#1a1a2e] px-4 py-12">
      <div className="mx-auto max-w-5xl space-y-8">
        <header className="space-y-4">
          <div>
            <h1 className="text-3xl font-semibold text-[#e4e4e7]">{t("dashboardTitle")}</h1>
            <p className="mt-2 text-sm text-[#a1a1aa]">{t("dashboardSubtitle")}</p>
          </div>
          <CompanySectionNav />
        </header>

        {isLoading || !user ? (
          <p className="text-sm text-[#a1a1aa]">{t("loading")}</p>
        ) : activeCompany ? (
          <div className="grid gap-8 lg:grid-cols-[2fr_1fr]">
            <CompanyOverview activeCompany={activeCompany} />
            <CompanySwitcher />
          </div>
        ) : (
          <div className="grid gap-8 lg:grid-cols-2">
            <CreateCompanyForm />
            <CompanySwitcher />
          </div>
        )}
      </div>
    </div>
  );
}

export default function CompanyDashboardPage() {
  return <CompanyDashboardContent />;
}
