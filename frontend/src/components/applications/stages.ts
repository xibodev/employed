import type { Application, ApplicationStatus } from "@/lib/api";

/**
 * The fixed application pipeline, in display order (R16.3). The kanban renders
 * one column per stage and the list status control offers exactly these values,
 * so list and kanban stay in parity over the same set of stages.
 */
export const APPLICATION_STAGES: readonly ApplicationStatus[] = [
  "applied",
  "reviewed",
  "shortlisted",
  "rejected",
  "hired",
] as const;

/** Badge tone per stage, shared by the list and kanban presentations. */
export const STAGE_BADGE_VARIANT: Record<ApplicationStatus, "default" | "info" | "warning" | "success" | "danger"> = {
  applied: "info",
  reviewed: "default",
  shortlisted: "warning",
  rejected: "danger",
  hired: "success",
};

/** next-intl key (within the `pipeline` namespace) for a stage's display label. */
export function stageLabelKey(stage: ApplicationStatus): string {
  return `stage.${stage}`;
}

/**
 * Group applications into one bucket per pipeline stage, in {@link APPLICATION_STAGES}
 * order. The kanban presentation renders these buckets as columns; because every
 * application is placed in exactly the bucket matching its status (and statuses are
 * drawn from {@link APPLICATION_STAGES}), the union of all buckets equals the input
 * set the list presentation renders — keeping list and kanban in parity (R17.2).
 */
export function groupByStage(
  applications: readonly Application[],
): Map<ApplicationStatus, Application[]> {
  const byStage = new Map<ApplicationStatus, Application[]>();
  for (const stage of APPLICATION_STAGES) {
    byStage.set(stage, []);
  }
  for (const application of applications) {
    byStage.get(application.status)?.push(application);
  }
  return byStage;
}

/**
 * A short, human-scannable handle for an application. Resume snapshots follow
 * the JSON Resume shape, so prefer `basics.name`; otherwise fall back through a
 * top-level `name`, the candidate user id, and finally the application id.
 */
export function candidateDisplayName(
  snapshot: Record<string, unknown> | null,
  candidateUserId: string | null,
  fallbackId: string,
): { kind: "snapshot" | "user" | "unknown"; value: string } {
  if (snapshot) {
    const basics = snapshot.basics;
    if (basics && typeof basics === "object" && "name" in basics) {
      const name = (basics as { name?: unknown }).name;
      if (typeof name === "string" && name.trim()) {
        return { kind: "snapshot", value: name.trim() };
      }
    }
    if (typeof snapshot.name === "string" && snapshot.name.trim()) {
      return { kind: "snapshot", value: snapshot.name.trim() };
    }
    return { kind: "snapshot", value: shortId(fallbackId) };
  }
  if (candidateUserId) {
    return { kind: "user", value: shortId(candidateUserId) };
  }
  return { kind: "unknown", value: shortId(fallbackId) };
}

/** First segment of a UUID — enough to disambiguate in the UI without noise. */
export function shortId(id: string): string {
  return id.split("-")[0] ?? id;
}
