"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";

import { changeApplicationStatus, listApplications, type Application, type ApplicationStatus } from "@/lib/api";
import { useTenant } from "@/contexts/TenantContext";
import { classNames } from "@/lib/utils";
import { ApplicationsKanban } from "./ApplicationsKanban";
import { ApplicationsList } from "./ApplicationsList";

type Presentation = "list" | "kanban";

/**
 * Recruiter applications surface (R17.2/R17.3). Owns the single source of
 * application data and feeds it to either the list or the kanban presentation,
 * so the two views are always in parity. Advancing a stage (drag in kanban or
 * the per-card control in either view) calls PATCH /applications/{id}/status and
 * reconciles the returned application back into the shared state.
 */
export function ApplicationsClient() {
  const t = useTranslations("applications");
  const { activeCompany } = useTenant();

  const [applications, setApplications] = useState<Application[]>([]);
  const [presentation, setPresentation] = useState<Presentation>("list");
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [advanceError, setAdvanceError] = useState<string | null>(null);
  const [updatingIds, setUpdatingIds] = useState<ReadonlySet<string>>(new Set());

  const companyId = activeCompany?.id ?? null;

  const loadApplications = useCallback(async () => {
    if (!companyId) {
      setApplications([]);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setLoadError(null);
    try {
      const items = await listApplications(companyId);
      setApplications(items);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : t("loadError"));
    } finally {
      setIsLoading(false);
    }
  }, [companyId, t]);

  useEffect(() => {
    void loadApplications();
  }, [loadApplications]);

  const handleAdvance = useCallback(
    async (application: Application, next: ApplicationStatus) => {
      if (application.status === next) {
        return;
      }
      setAdvanceError(null);
      setUpdatingIds((current) => new Set(current).add(application.id));
      try {
        const updated = await changeApplicationStatus(application.id, next);
        // Reconcile from the server response so list and kanban share one truth.
        setApplications((current) =>
          current.map((item) => (item.id === updated.id ? { ...item, ...updated } : item)),
        );
      } catch (error) {
        setAdvanceError(error instanceof Error ? error.message : t("advanceError"));
      } finally {
        setUpdatingIds((current) => {
          const nextSet = new Set(current);
          nextSet.delete(application.id);
          return nextSet;
        });
      }
    },
    [t],
  );

  const presentations: Presentation[] = useMemo(() => ["list", "kanban"], []);

  return (
    <main className="min-h-screen bg-[#1a1a2e] px-4 py-12">
      <div className="mx-auto max-w-7xl space-y-6">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h1 className="text-3xl font-semibold text-[#e4e4e7]">{t("title")}</h1>
            <p className="mt-2 text-sm text-[#a1a1aa]">{t("subtitle")}</p>
          </div>

          <div
            role="group"
            aria-label={t("view.toggleLabel")}
            className="inline-flex rounded-xl border border-white/10 bg-[#16213e] p-1"
          >
            {presentations.map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={presentation === value}
                onClick={() => setPresentation(value)}
                className={classNames(
                  "rounded-lg px-4 py-2 text-sm font-medium transition",
                  presentation === value ? "bg-indigo-600 text-white" : "text-[#a1a1aa] hover:text-[#e4e4e7]",
                )}
              >
                {value === "list" ? t("view.list") : t("view.kanban")}
              </button>
            ))}
          </div>
        </div>

        {!companyId ? (
          <p className="rounded-2xl border border-white/10 bg-[#16213e] px-4 py-3 text-sm text-[#a1a1aa]">
            {t("noCompany")}
          </p>
        ) : (
          <>
            <p className="text-sm text-[#a1a1aa]">{t("countLabel", { count: applications.length })}</p>

            {loadError ? (
              <p className="rounded-2xl bg-red-500/10 px-4 py-3 text-sm text-red-300">{loadError}</p>
            ) : null}
            {advanceError ? (
              <p className="rounded-2xl bg-red-500/10 px-4 py-3 text-sm text-red-300">{advanceError}</p>
            ) : null}

            {isLoading ? (
              <p className="text-sm text-[#a1a1aa]">{t("loading")}</p>
            ) : presentation === "list" ? (
              <ApplicationsList applications={applications} onAdvance={handleAdvance} updatingIds={updatingIds} />
            ) : (
              <ApplicationsKanban applications={applications} onAdvance={handleAdvance} updatingIds={updatingIds} />
            )}
          </>
        )}
      </div>
    </main>
  );
}
