"use client";

import { useTranslations } from "next-intl";

import type { Application, ApplicationStatus } from "@/lib/api";
import { classNames } from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";
import { APPLICATION_STAGES, STAGE_BADGE_VARIANT, candidateDisplayName, shortId, stageLabelKey } from "./stages";

interface ApplicationCardProps {
  application: Application;
  /** Advance the application to a new stage (R17.3). Disabled while in flight. */
  onAdvance: (application: Application, next: ApplicationStatus) => void;
  /** True while a status change for this card is being persisted. */
  isUpdating?: boolean;
  /** When true the card omits the status badge (the kanban column already conveys it). */
  hideStatusBadge?: boolean;
  /** Makes the card a native drag source for the kanban presentation. */
  draggable?: boolean;
  onDragStart?: (application: Application) => void;
  onDragEnd?: () => void;
  className?: string;
}

export function ApplicationCard({
  application,
  onAdvance,
  isUpdating = false,
  hideStatusBadge = false,
  draggable = false,
  onDragStart,
  onDragEnd,
  className,
}: ApplicationCardProps) {
  const t = useTranslations("applications");
  const tStage = useTranslations("pipeline");

  const candidate = candidateDisplayName(
    application.candidate_snapshot,
    application.candidate_user_id,
    application.id,
  );
  const candidateLabel =
    candidate.kind === "user"
      ? t("candidateLabel", { id: candidate.value })
      : candidate.kind === "snapshot"
        ? candidate.value
        : t("unknownCandidate");

  return (
    <article
      draggable={draggable}
      onDragStart={
        draggable
          ? (event) => {
              event.dataTransfer.setData("text/plain", application.id);
              event.dataTransfer.effectAllowed = "move";
              onDragStart?.(application);
            }
          : undefined
      }
      onDragEnd={draggable ? () => onDragEnd?.() : undefined}
      className={classNames(
        "space-y-3 rounded-2xl border border-white/10 bg-[#16213e] p-4 text-sm",
        draggable && "cursor-grab active:cursor-grabbing",
        isUpdating && "opacity-60",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-medium text-[#e4e4e7]">{candidateLabel}</p>
          <p className="mt-1 text-xs text-[#71717a]">{t("jobLabel", { id: shortId(application.job_id) })}</p>
        </div>
        {hideStatusBadge ? null : (
          <Badge variant={STAGE_BADGE_VARIANT[application.status]}>{tStage(stageLabelKey(application.status))}</Badge>
        )}
      </div>

      <p className="text-xs text-[#a1a1aa]">{t("sourceLabel", { source: application.source })}</p>

      {application.cover_note ? (
        <p className="line-clamp-3 text-xs text-[#a1a1aa]">{application.cover_note}</p>
      ) : (
        <p className="text-xs italic text-[#71717a]">{t("noCoverNote")}</p>
      )}

      <label className="flex flex-col gap-1 text-xs text-[#a1a1aa]">
        <span className="font-medium text-[#e4e4e7]">{t("stageControlLabel")}</span>
        <select
          className="h-9 rounded-lg border border-zinc-800 bg-[#111827] px-2 text-[#e4e4e7] outline-none transition focus:border-indigo-500 disabled:opacity-60"
          value={application.status}
          disabled={isUpdating}
          aria-busy={isUpdating}
          onChange={(event) => {
            const next = event.target.value as ApplicationStatus;
            if (next !== application.status) {
              onAdvance(application, next);
            }
          }}
        >
          {APPLICATION_STAGES.map((stage) => (
            <option key={stage} value={stage}>
              {tStage(stageLabelKey(stage))}
            </option>
          ))}
        </select>
      </label>
    </article>
  );
}
