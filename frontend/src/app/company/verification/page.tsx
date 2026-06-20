"use client";

import { useTranslations } from "next-intl";

import { CompanyGate } from "@/components/company/CompanyGate";
import { VerificationPanel } from "@/components/company/VerificationPanel";

function CompanyVerificationContent() {
  const t = useTranslations("verification");

  return (
    <CompanyGate title={t("title")} subtitle={t("subtitle")} redirectTo="/company/verification">
      {(activeCompany) => <VerificationPanel activeCompany={activeCompany} />}
    </CompanyGate>
  );
}

export default function CompanyVerificationPage() {
  return <CompanyVerificationContent />;
}
