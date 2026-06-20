"use client";

import { useTranslations } from "next-intl";

import type { Application, ApplicationStatus } from "@/lib/api";
import { ApplicationCard } from "./ApplicationCard";

interface ApplicationsListProps {
  applications: Application[];
  onAdvance: (application: Application, next: ApplicationStatus) => void;
  /** Ids with an in-flight status change. */
  updatingIds: ReadonlySet<string>;
}

/**
 * List presentation of the recruiter applications view (R17.2). Renders the
 * same applications as the kanban, one per row, each carrying the status-advance
 * control (R17.3).
 */
export function ApplicationsList({ applications, onAdvance, updatingIds }: ApplicationsListProps) {
  const t = useTranslations("applications");

  if (applications.length === 0) {
    return <p className="text-sm text-[#71717a]">{t("empty")}</p>;
  }

  return (
    <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {applications.map((application) => (
        <li key={application.id}>
          <ApplicationCard
            application={application}
            onAdvance={onAdvance}
            isUpdating={updatingIds.has(application.id)}
          />
        </li>
      ))}
    </ul>
  );
}
