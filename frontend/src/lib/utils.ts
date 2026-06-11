import type { Job } from "@/lib/types";

export function classNames(...values: Array<string | false | null | undefined>): string {
  return values.filter(Boolean).join(" ");
}

export function formatDate(value?: string | Date | null, locale = "en-US"): string {
  if (!value) return "—";
  const date = value instanceof Date ? value : new Date(value);
  return new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "short",
    day: "numeric"
  }).format(date);
}

export function stripHtml(html?: string | null): string {
  if (!html) return "";
  return html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

export function truncateHtml(html: string, limit = 180): string {
  const text = stripHtml(html);
  return text.length > limit ? `${text.slice(0, limit).trim()}…` : text;
}

export function slugify(value: string): string {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)+/g, "");
}

export function formatSalary(job: Pick<Job, "salary_min" | "salary_max" | "salary_currency" | "salary_period">): string | null {
  if (!job.salary_currency || (job.salary_min == null && job.salary_max == null)) {
    return null;
  }

  const formatter = new Intl.NumberFormat("en", {
    style: "currency",
    currency: job.salary_currency,
    maximumFractionDigits: 0
  });

  const min = job.salary_min != null ? formatter.format(job.salary_min) : null;
  const max = job.salary_max != null ? formatter.format(job.salary_max) : null;
  const range = min && max ? `${min} – ${max}` : min ?? max;
  const period = job.salary_period ? ` / ${job.salary_period}` : "";

  return range ? `${range}${period}` : null;
}

export function pickRandomItems<T>(items: T[], count: number): T[] {
  return [...items]
    .sort(() => Math.random() - 0.5)
    .slice(0, count);
}

export function toWhatsAppUrl(value?: string | null): string | null {
  if (!value) return null;
  const digits = value.replace(/\D/g, "");
  return digits ? `https://wa.me/${digits}` : null;
}

/**
 * Localized display name for a market country (EMP-027). The canonical API
 * value ("Mexico"/"Mozambique") is a data contract and must not change;
 * only the rendered label is localized (e.g. "Moçambique", "México").
 */
const COUNTRY_MESSAGE_KEYS: Record<string, string> = {
  Mexico: "mexico",
  Mozambique: "mozambique",
};

export function countryLabel(t: (key: string) => string, country?: string | null): string {
  if (!country) return "";
  const key = COUNTRY_MESSAGE_KEYS[country];
  return key ? t(key) : country;
}
