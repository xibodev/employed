"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import type { Job, MarketConfig } from "@/lib/types";
import { deleteJob, getJob, updateJob, apiFetch } from "@/lib/api";
import { formatDate, formatSalary, toWhatsAppUrl } from "@/lib/utils";
import { countryLabel } from "@/lib/utils";
import { useAuth } from "@/hooks/useAuth";

export default function JobDetail({ job, market }: { job: Job; market: MarketConfig }) {
  const router = useRouter();
  const { user } = useAuth();
  const t = useTranslations("jobs");
  const tCountries = useTranslations("countries");
  const [reportOpen, setReportOpen] = useState(false);
  const [reportReason, setReportReason] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // EMP-028: contact is auth-gated server-side, so the SSR payload carries
  // null for anonymous renders; signed-in users reveal it explicitly.
  const [contact, setContact] = useState<string | null>(job.contact ?? null);
  const [revealState, setRevealState] = useState<"idle" | "busy" | "empty">("idle");

  const isOwner = Boolean(user?.id && user.id === job.owner_id);
  const salary = formatSalary(job);
  const applyHref = useMemo(() => toWhatsAppUrl(job.apply_whatsapp) ?? job.url ?? (contact ? `mailto:${contact}` : null), [job.apply_whatsapp, contact, job.url]);

  async function revealContact() {
    setRevealState("busy");
    setMessage(null);
    try {
      const fresh = await getJob(job.id);
      if (fresh.contact) {
        setContact(fresh.contact);
        setRevealState("idle");
      } else {
        setRevealState("empty");
      }
    } catch (error) {
      setRevealState("idle");
      setMessage(error instanceof Error ? error.message : t("revealError"));
    }
  }

  async function handleDeactivate() {
    if (!isOwner) return;
    setBusy(true);
    setMessage(null);
    try {
      await updateJob(job.id, { status: "inactive" });
      setMessage(t("deactivated"));
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t("deactivateError"));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!isOwner || !window.confirm(t("deleteConfirm"))) return;
    setBusy(true);
    setMessage(null);
    try {
      await deleteJob(job.id);
      router.push("/jobs");
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t("deleteError"));
      setBusy(false);
    }
  }

  async function submitReport() {
    setBusy(true);
    setMessage(null);
    try {
      await apiFetch(`/api/jobs/${job.id}/report`, {
        method: "POST",
        body: { reason: reportReason }
      });
      setMessage(t("reportThanks"));
      setReportOpen(false);
      setReportReason("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t("reportError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,2.2fr)_minmax(300px,1fr)]">
      <section className="space-y-6">
        <div className="card-surface space-y-4 p-6">
          <div className="flex flex-wrap items-center gap-2">
            {job.featured ? <Badge variant="warning">{t("featuredBadge")}</Badge> : null}
            {job.remote ? <Badge variant="success">{t("remoteBadge")}</Badge> : null}
            <Badge>{job.jobtype}</Badge>
          </div>
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-zinc-100">{job.title}</h1>
            <p className="mt-2 text-lg text-zinc-300">{job.company ?? market.siteName}</p>
          </div>
          <div className="grid gap-2 text-sm text-zinc-400 sm:grid-cols-2">
            <p>{job.location ?? t("flexibleLocation")}</p>
            <p>{countryLabel(tCountries, job.country)}</p>
            <p>{t("postedOn", { date: formatDate(job.published_at ?? job.created_at, market.locale) })}</p>
            {salary ? <p>{salary}</p> : null}
          </div>
        </div>

        <article className="card-surface p-6">
          <div className="job-copy" dangerouslySetInnerHTML={{ __html: job.html_description ?? job.description ?? `<p>${t("noDescription")}</p>` }} />
        </article>
      </section>

      <aside className="space-y-4">
        <div className="card-surface space-y-4 p-5">
          <h2 className="text-lg font-semibold text-zinc-100">{t("applyTitle")}</h2>
          {applyHref ? (
            <a
              href={applyHref}
              target={applyHref.startsWith("http") ? "_blank" : undefined}
              rel={applyHref.startsWith("http") ? "noopener noreferrer" : undefined}
              className="inline-flex w-full items-center justify-center rounded-xl bg-indigo-600 px-4 py-3 text-sm font-medium text-white transition hover:bg-indigo-500"
            >
              {job.apply_whatsapp ? t("applyWhatsApp") : job.url ? t("applyButton") : t("contactEmployer")}
            </a>
          ) : contact === null && revealState !== "empty" ? (
            user ? (
              <Button className="w-full" disabled={revealState === "busy"} onClick={revealContact}>
                {revealState === "busy" ? t("revealingContact") : t("revealContact")}
              </Button>
            ) : (
              <Link
                href="/sign-in"
                className="inline-flex w-full items-center justify-center rounded-xl bg-indigo-600 px-4 py-3 text-sm font-medium text-white transition hover:bg-indigo-500"
              >
                {t("signInToContact")}
              </Link>
            )
          ) : (
            <p className="rounded-xl border border-zinc-800 bg-[#111827] px-4 py-3 text-sm text-zinc-400">{t("noApplication")}</p>
          )}
          {contact ? (
            <p className="text-sm text-zinc-400">{t("contactLine", { contact })}</p>
          ) : applyHref && revealState !== "empty" ? (
            user ? (
              <button
                type="button"
                disabled={revealState === "busy"}
                onClick={revealContact}
                className="text-sm font-medium text-indigo-300 underline underline-offset-2 transition hover:text-indigo-200 disabled:opacity-60"
              >
                {revealState === "busy" ? t("revealingContact") : t("revealContact")}
              </button>
            ) : (
              <Link href="/sign-in" className="text-sm font-medium text-indigo-300 underline underline-offset-2 transition hover:text-indigo-200">
                {t("signInToContact")}
              </Link>
            )
          ) : null}
        </div>

        <div className="card-surface space-y-3 p-5 text-sm text-zinc-300">
          <h2 className="text-lg font-semibold text-zinc-100">{t("listingDetails")}</h2>
          <p><span className="text-zinc-500">{t("company")}:</span> {job.company ?? t("independentEmployer")}</p>
          <p><span className="text-zinc-500">{t("location")}:</span> {job.location ?? t("flexible")}</p>
          <p><span className="text-zinc-500">{t("type")}:</span> {job.jobtype}</p>
          <p><span className="text-zinc-500">{t("remote")}:</span> {job.remote ? t("yes") : t("no")}</p>
          {salary ? <p><span className="text-zinc-500">{t("salary")}:</span> {salary}</p> : null}
          <p><span className="text-zinc-500">{t("published")}:</span> {formatDate(job.published_at ?? job.created_at, market.locale)}</p>
        </div>

        {isOwner ? (
          <div className="card-surface space-y-3 p-5">
            <h2 className="text-lg font-semibold text-zinc-100">{t("manageTitle")}</h2>
            <div className="flex flex-wrap gap-2">
              <Link href={`/jobs/${job.id}/edit`} className="inline-flex items-center justify-center rounded-xl border border-zinc-700 bg-[#16213e] px-4 py-2 text-sm font-medium text-zinc-100 hover:border-zinc-600">
                {t("edit")}
              </Link>
              <Button variant="secondary" disabled={busy} onClick={handleDeactivate}>
                {t("deactivate")}
              </Button>
              <Button variant="danger" disabled={busy} onClick={handleDelete}>
                {t("delete")}
              </Button>
            </div>
          </div>
        ) : (
          <div className="card-surface space-y-3 p-5">
            <h2 className="text-lg font-semibold text-zinc-100">{t("flagTitle")}</h2>
            <Button variant="secondary" onClick={() => setReportOpen(true)}>
              {t("reportJob")}
            </Button>
          </div>
        )}

        {message ? <div className="rounded-2xl border border-zinc-700 bg-[#111827] px-4 py-3 text-sm text-zinc-300">{message}</div> : null}
      </aside>

      {reportOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4">
          <div className="w-full max-w-lg rounded-3xl border border-zinc-800 bg-[#16213e] p-6 shadow-2xl shadow-black/50">
            <h2 className="text-xl font-semibold text-zinc-100">{t("reportTitle")}</h2>
            <p className="mt-2 text-sm text-zinc-400">{t("reportSubtitle")}</p>
            <textarea
              value={reportReason}
              onChange={(event) => setReportReason(event.target.value)}
              className="mt-4 min-h-32 w-full rounded-2xl border border-zinc-800 bg-[#111827] px-4 py-3 text-sm text-zinc-100 outline-none focus:border-indigo-500"
              placeholder={t("reportPlaceholder")}
            />
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setReportOpen(false)}>
                {t("cancel")}
              </Button>
              <Button onClick={submitReport} disabled={busy || !reportReason.trim()}>
                {t("reportSubmit")}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
