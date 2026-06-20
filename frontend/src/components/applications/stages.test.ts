import assert from "node:assert/strict";
import { test } from "node:test";

import type { Application, ApplicationStatus } from "@/lib/api";
import {
  APPLICATION_STAGES,
  STAGE_BADGE_VARIANT,
  candidateDisplayName,
  groupByStage,
  shortId,
  stageLabelKey,
} from "./stages";

/**
 * Pure-logic tests for the recruiter applications pipeline helpers.
 *
 * No component test runner / React Testing Library is configured in this
 * frontend (see package.json — only ESLint + `tsc --noEmit`). Rather than pull
 * in a heavy test framework, these tests exercise the shared pure logic that
 * both the list and kanban presentations build on, which is where the
 * list/kanban PARITY (R17.2) is actually guaranteed:
 *
 *   - The list presentation renders the `applications` array directly.
 *   - The kanban presentation renders `groupByStage(applications)` as columns.
 *
 * If the union of the kanban columns always equals the list's input set (no
 * application dropped, none duplicated), the two views present the same set of
 * applications from the same data — i.e. they are in parity.
 *
 * They run on the existing toolchain via Node's built-in test runner over the
 * TypeScript compiled by the project's own `typescript` dependency.
 */

function makeApplication(id: string, status: ApplicationStatus): Application {
  return {
    id,
    job_id: `job-${id}`,
    company_id: "company-1",
    candidate_user_id: null,
    candidate_snapshot: null,
    status,
    resume_version_id: null,
    cover_note: null,
    source: "platform",
  };
}

// A representative dataset covering every stage plus repeats and empties.
const sampleApplications: Application[] = [
  makeApplication("a", "applied"),
  makeApplication("b", "applied"),
  makeApplication("c", "reviewed"),
  makeApplication("d", "shortlisted"),
  makeApplication("e", "rejected"),
  makeApplication("f", "hired"),
  makeApplication("g", "hired"),
];

test("list/kanban parity: grouped columns cover the same set the list renders", () => {
  const grouped = groupByStage(sampleApplications);

  // The list renders this exact set; collect the kanban's set from its columns.
  const listIds = new Set(sampleApplications.map((a) => a.id));
  const kanbanIds = new Set<string>();
  let kanbanCount = 0;
  for (const stage of APPLICATION_STAGES) {
    for (const application of grouped.get(stage) ?? []) {
      kanbanIds.add(application.id);
      kanbanCount += 1;
    }
  }

  // Same cardinality => nothing dropped and nothing duplicated across columns.
  assert.equal(kanbanCount, sampleApplications.length);
  // Same membership => list and kanban present identical application sets.
  assert.deepEqual([...kanbanIds].sort(), [...listIds].sort());
});

test("list/kanban parity holds for the empty dataset", () => {
  const grouped = groupByStage([]);
  let total = 0;
  for (const stage of APPLICATION_STAGES) {
    total += (grouped.get(stage) ?? []).length;
  }
  assert.equal(total, 0);
});

test("groupByStage places each application in the bucket matching its status", () => {
  const grouped = groupByStage(sampleApplications);
  for (const stage of APPLICATION_STAGES) {
    for (const application of grouped.get(stage) ?? []) {
      assert.equal(application.status, stage);
    }
  }
});

test("groupByStage exposes a column for every pipeline stage", () => {
  const grouped = groupByStage([]);
  for (const stage of APPLICATION_STAGES) {
    assert.ok(grouped.has(stage), `missing column for stage ${stage}`);
  }
  assert.equal(grouped.size, APPLICATION_STAGES.length);
});

test("APPLICATION_STAGES is the fixed, ordered pipeline (R16.3)", () => {
  assert.deepEqual([...APPLICATION_STAGES], ["applied", "reviewed", "shortlisted", "rejected", "hired"]);
});

test("every stage has a badge variant", () => {
  for (const stage of APPLICATION_STAGES) {
    assert.ok(STAGE_BADGE_VARIANT[stage], `missing badge variant for ${stage}`);
  }
});

test("stageLabelKey builds the pipeline namespace key", () => {
  assert.equal(stageLabelKey("applied"), "stage.applied");
  assert.equal(stageLabelKey("hired"), "stage.hired");
});

test("candidateDisplayName prefers JSON Resume basics.name", () => {
  const result = candidateDisplayName({ basics: { name: "Ada Lovelace" } }, "user-1", "app-1");
  assert.deepEqual(result, { kind: "snapshot", value: "Ada Lovelace" });
});

test("candidateDisplayName falls back to a top-level name", () => {
  const result = candidateDisplayName({ name: "Grace Hopper" }, null, "app-1");
  assert.deepEqual(result, { kind: "snapshot", value: "Grace Hopper" });
});

test("candidateDisplayName falls back to the candidate user id", () => {
  const result = candidateDisplayName(null, "11112222-3333-4444", "app-1");
  assert.deepEqual(result, { kind: "user", value: "11112222" });
});

test("candidateDisplayName falls back to the application id when nothing else is known", () => {
  const result = candidateDisplayName(null, null, "aaaabbbb-cccc-dddd");
  assert.deepEqual(result, { kind: "unknown", value: "aaaabbbb" });
});

test("shortId returns the first UUID segment", () => {
  assert.equal(shortId("12345678-90ab-cdef"), "12345678");
  assert.equal(shortId("nodashes"), "nodashes");
});
