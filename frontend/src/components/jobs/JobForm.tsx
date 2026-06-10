"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { RichTextEditor } from "@/components/ui/RichTextEditor";
import { RecaptchaWidget } from "@/components/ui/RecaptchaWidget";
import { JOB_TYPES, SALARY_CURRENCIES, SALARY_PERIODS } from "@/lib/constants";
import { createJob, updateJob } from "@/lib/api";
import type { Job, JobFormValues } from "@/lib/types";
import { useAuth } from "@/hooks/useAuth";
import { useMarket } from "@/hooks/useMarket";

type FormErrors = Partial<Record<keyof JobFormValues, string>> & { form?: string };

function coerceNumber(value: string): number | undefined {
  if (!value) return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

export default function JobForm({ mode, job }: { mode: "create" | "edit"; job?: Job }) {
  const router = useRouter();
  const { market } = useMarket();
  const { isAuthenticated } = useAuth();
  const [values, setValues] = useState<JobFormValues>({
    title: job?.title ?? "",
    company: job?.company ?? "",
    location: job?.location ?? "",
    url: job?.url ?? "",
    contact: job?.contact ?? "",
    apply_whatsapp: job?.apply_whatsapp ?? "",
    jobtype: job?.jobtype ?? "Full Time",
    remote: job?.remote ?? false,
    salary_min: job?.salary_min ?? undefined,
    salary_max: job?.salary_max ?? undefined,
    salary_currency: job?.salary_currency ?? undefined,
    salary_period: job?.salary_period ?? undefined,
    description: job?.html_description ?? job?.description ?? "",
    country: job?.country ?? market.country
  });
  const [errors, setErrors] = useState<FormErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);
  const [recaptchaRefresh, setRecaptchaRefresh] = useState(0);
  const pendingSubmit = useRef(false);

  useEffect(() => {
    setValues((current) => ({ ...current, country: job?.country ?? market.country }));
  }, [job?.country, market.country]);

  const salaryOptions = useMemo(() => SALARY_CURRENCIES.map((currency) => ({ label: currency, value: currency })), []);
  const periodOptions = useMemo(() => SALARY_PERIODS.map((period) => ({ label: period, value: period })), []);

  function update<K extends keyof JobFormValues>(key: K, value: JobFormValues[K]) {
    setValues((current) => ({ ...current, [key]: value }));
  }

  function validate() {
    const nextErrors: FormErrors = {};

    if (!values.title.trim()) nextErrors.title = "A job title is required.";
    if (!values.contact.trim()) nextErrors.contact = "Add a contact email or contact point.";
    if (!values.description.trim() || values.description === "<p></p>") nextErrors.description = "Describe the opportunity in detail.";
    if (values.salary_min && values.salary_max && values.salary_min > values.salary_max) {
      nextErrors.salary_max = "Maximum salary should be greater than the minimum.";
    }

    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  }

  async function performSubmit(recaptchaToken?: string) {
    try {
      const payload: JobFormValues = {
        ...values,
        title: values.title.trim(),
        company: values.company?.trim() || undefined,
        location: values.location?.trim() || undefined,
        url: values.url?.trim() || undefined,
        contact: values.contact.trim(),
        apply_whatsapp: values.apply_whatsapp?.trim() || undefined,
        description: values.description,
        country: market.country,
        salary_min: values.salary_min,
        salary_max: values.salary_max,
        salary_currency: values.salary_currency,
        salary_period: values.salary_period,
        recaptcha_token: !isAuthenticated ? recaptchaToken : undefined,
        remote: values.remote,
        jobtype: values.jobtype
      };

      if (mode === "edit" && job) {
        await updateJob(job.id, payload);
        setSuccess("Job listing updated successfully.");
        router.refresh();
      } else {
        const created = await createJob(payload);
        setSuccess("Job listing submitted. It will appear once approved.");
        router.push(`/jobs/${created.id}`);
        router.refresh();
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Something went wrong while saving your listing.";
      setErrors({ form: message });
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSuccess(null);
    setErrors({});

    if (!validate()) return;

    setSubmitting(true);

    if (!isAuthenticated && process.env.NEXT_PUBLIC_RECAPTCHA_SITE_KEY) {
      pendingSubmit.current = true;
      setRecaptchaRefresh((value) => value + 1);
      return;
    }

    await performSubmit();
  }

  async function handleRecaptcha(token: string) {
    if (!pendingSubmit.current) return;
    pendingSubmit.current = false;
    await performSubmit(token);
  }

  if (mode === "edit" && !isAuthenticated) {
    return (
      <div className="card-surface p-6 text-sm text-zinc-300">
        <p className="text-lg font-semibold text-zinc-100">Authentication required</p>
        <p className="mt-2">You need to sign in with the listing owner account before editing this job.</p>
      </div>
    );
  }

  return (
    <>
      {/* Action name must match the backend contract (RECAPTCHA_ACTION = "submit_job", EMP-003). */}
      <RecaptchaWidget action="submit_job" refreshKey={recaptchaRefresh} onVerify={handleRecaptcha} />
      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="card-surface space-y-4 p-5">
            <h2 className="text-xl font-semibold text-zinc-100">Role details</h2>
            <Input label="Job title" name="title" value={values.title} error={errors.title} onChange={(event) => update("title", event.target.value)} />
            <Input label="Company" name="company" value={values.company} onChange={(event) => update("company", event.target.value)} />
            <Input label="Location" name="location" value={values.location} onChange={(event) => update("location", event.target.value)} hint="City, region, or province" />
            <Select label="Job type" name="jobtype" value={values.jobtype} onChange={(event) => update("jobtype", event.target.value as JobFormValues["jobtype"])} options={JOB_TYPES.map((type) => ({ label: type, value: type }))} />
            <label className="flex items-center gap-3 rounded-xl border border-zinc-800 bg-[#111827] px-4 py-3 text-sm text-zinc-300">
              <input type="checkbox" checked={values.remote} onChange={(event) => update("remote", event.target.checked)} className="size-4 rounded border-zinc-600 bg-zinc-950 text-indigo-500" />
              This role can be performed remotely.
            </label>
            <Input label="Country" name="country" value={market.country} disabled readOnly />
          </div>

          <div className="card-surface space-y-4 p-5">
            <h2 className="text-xl font-semibold text-zinc-100">How candidates apply</h2>
            <Input label="Contact" name="contact" value={values.contact} error={errors.contact} onChange={(event) => update("contact", event.target.value)} hint="Email address or recruiting contact" />
            <Input label="Apply URL" name="url" value={values.url} onChange={(event) => update("url", event.target.value)} placeholder="https://company.example/jobs/role" />
            <Input label="WhatsApp apply number" name="apply_whatsapp" value={values.apply_whatsapp} onChange={(event) => update("apply_whatsapp", event.target.value)} placeholder="+258 84 000 0000" />
            <div className="grid gap-4 sm:grid-cols-2">
              <Input label="Salary min" type="number" name="salary_min" value={values.salary_min ?? ""} onChange={(event) => update("salary_min", coerceNumber(event.target.value))} />
              <Input label="Salary max" type="number" name="salary_max" value={values.salary_max ?? ""} error={errors.salary_max} onChange={(event) => update("salary_max", coerceNumber(event.target.value))} />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Select label="Currency" name="salary_currency" value={values.salary_currency ?? ""} onChange={(event) => update("salary_currency", (event.target.value || undefined) as JobFormValues["salary_currency"])} options={[{ label: "Choose currency", value: "" }, ...salaryOptions]} />
              <Select label="Period" name="salary_period" value={values.salary_period ?? ""} onChange={(event) => update("salary_period", (event.target.value || undefined) as JobFormValues["salary_period"])} options={[{ label: "Choose period", value: "" }, ...periodOptions]} />
            </div>
          </div>
        </div>

        <div className="card-surface space-y-4 p-5">
          <RichTextEditor label="Job description" value={values.description} onChange={(value) => update("description", value)} error={errors.description} />
        </div>

        {errors.form ? (
          <div className="rounded-2xl border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
            <p>{errors.form}</p>
            <button
              type="button"
              className="mt-2 text-xs font-medium text-rose-300 underline underline-offset-2 hover:text-rose-100"
              onClick={() => {
                setErrors({});
                setSubmitting(false);
              }}
            >
              Dismiss and try again
            </button>
          </div>
        ) : null}
        {success ? <div className="rounded-2xl border border-emerald-500/40 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">{success}</div> : null}

        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" size="lg" disabled={submitting}>
            {submitting ? "Saving…" : mode === "edit" ? "Save changes" : "Post job"}
          </Button>
          <p className="text-sm text-zinc-500">
            {isAuthenticated ? "Signed-in employers can edit later from the job detail view." : "Anonymous submissions require reCAPTCHA verification before posting."}
          </p>
        </div>
      </form>
    </>
  );
}
