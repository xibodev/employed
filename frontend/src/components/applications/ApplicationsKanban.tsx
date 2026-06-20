"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";

import type { Application, ApplicationStatus } from "@/lib/api";
import { classNames } from "@/lib/utils";
import { ApplicationCard } from "./ApplicationCard";
import { APPLICATION_STAGES, groupByStage, stageLabelKey } from "./stages";

interface ApplicationsKanbanProps {
  applications: Application[];
  onAdvance: (application: Application, next: ApplicationStatus) => void;
  /** Ids with an in-flight status change. */
  updatingIds: ReadonlySet<string>;
}

/**
 * Kanban presentation of the recruiter pipeline (R17.2): one column per stage.
 * Recruiters advance an application either by dragging its card into another
 * column or via the per-card status control (R17.3). Both presentations read
 * from the same `applications` array, so the data stays in parity.
 */
export function ApplicationsKanban({ applications, onAdvance, updatingIds }: ApplicationsKanbanProps) {
  const tStage = useTranslations("pipeline");
  const [dragging, setDragging] = useState<Application | null>(null);
  const [dragOverStage, setDragOverStage] = useState<ApplicationStatus | null>(null);

  const grouped = useMemo(() => groupByStage(applications), [applications]);

  const handleDrop = (stage: ApplicationStatus) => {
    setDragOverStage(null);
    const dropped = dragging;
    setDragging(null);
    if (dropped && dropped.status !== stage) {
      onAdvance(dropped, stage);
    }
  };

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
      {APPLICATION_STAGES.map((stage) => {
        const items = grouped.get(stage) ?? [];
        return (
          <section
            key={stage}
            aria-label={tStage(stageLabelKey(stage))}
            onDragOver={(event) => {
              event.preventDefault();
              event.dataTransfer.dropEffect = "move";
              if (dragOverStage !== stage) {
                setDragOverStage(stage);
              }
            }}
            onDragLeave={(event) => {
              // Only clear when leaving the column, not when moving between its children.
              if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
                setDragOverStage((current) => (current === stage ? null : current));
              }
            }}
            onDrop={() => handleDrop(stage)}
            className={classNames(
              "flex flex-col gap-3 rounded-2xl border p-3 transition",
              dragOverStage === stage ? "border-indigo-500/60 bg-indigo-500/5" : "border-white/10 bg-[#13182b]",
            )}
          >
            <header className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-[#e4e4e7]">{tStage(stageLabelKey(stage))}</h2>
              <span className="rounded-full bg-white/5 px-2 py-0.5 text-xs text-[#a1a1aa]">
                {tStage("columnCount", { count: items.length })}
              </span>
            </header>

            <div className="flex flex-1 flex-col gap-3">
              {items.length === 0 ? (
                <p className="rounded-xl border border-dashed border-white/10 px-3 py-6 text-center text-xs text-[#71717a]">
                  {tStage("emptyColumn")}
                </p>
              ) : (
                items.map((application) => (
                  <ApplicationCard
                    key={application.id}
                    application={application}
                    onAdvance={onAdvance}
                    isUpdating={updatingIds.has(application.id)}
                    hideStatusBadge
                    draggable
                    onDragStart={setDragging}
                    onDragEnd={() => {
                      setDragging(null);
                      setDragOverStage(null);
                    }}
                  />
                ))
              )}
            </div>
          </section>
        );
      })}

      <p className="sr-only">{tStage("dragHint")}</p>
    </div>
  );
}
