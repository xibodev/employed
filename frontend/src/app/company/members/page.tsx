"use client";

import { useTranslations } from "next-intl";

import { CompanyGate } from "@/components/company/CompanyGate";
import { MembersPanel } from "@/components/company/MembersPanel";

function CompanyMembersContent() {
  const t = useTranslations("members");

  return (
    <CompanyGate title={t("title")} subtitle={t("subtitle")} redirectTo="/company/members">
      {(activeCompany) => <MembersPanel activeCompany={activeCompany} />}
    </CompanyGate>
  );
}

export default function CompanyMembersPage() {
  return <CompanyMembersContent />;
}
