export type MarketKey = "mx" | "mz";

export interface MarketConfig {
  key: MarketKey;
  country: string;
  locale: string;
  siteName: string;
  tagline: string;
  host: string;
  featuredJob: {
    amount: number;
    currency: string;
    label: string;
  };
  paymentProviders: string[];
}

export type JobType =
  | "Full Time"
  | "Part Time"
  | "Contract"
  | "Temporary"
  | "Internship"
  | "Freelance"
  | "Remote"
  | "Volunteer"
  | "Other";

export type JobStatus = "pending" | "active" | "flagged" | "inactive" | "filled";
export type SalaryCurrency = "MXN" | "MZN" | "USD" | "EUR" | "ZAR";
export type SalaryPeriod = "hour" | "day" | "week" | "month" | "year";

export interface Job {
  id: string;
  slug?: string | null;
  title: string;
  company?: string | null;
  country: string;
  location?: string | null;
  url?: string | null;
  // EMP-028: auth-gated — null in anonymous payloads; revealed via an
  // authenticated re-fetch of the job detail.
  contact?: string | null;
  apply_whatsapp?: string | null;
  jobtype: JobType;
  remote: boolean;
  salary_min?: number | null;
  salary_max?: number | null;
  salary_currency?: SalaryCurrency | null;
  salary_period?: SalaryPeriod | null;
  description?: string | null;
  html_description?: string | null;
  status: JobStatus;
  featured: boolean;
  featured_through?: string | null;
  created_at: string;
  updated_at?: string | null;
  published_at?: string | null;
  expires_at?: string | null;
  owner_id?: string | null;
  owner_name?: string | null;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface JobsQuery {
  search?: string;
  job_type?: string;
  remote?: boolean;
  page?: number;
  per_page?: number;
  country?: string;
  featured?: boolean;
  status?: JobStatus | "all";
}

export interface JobFormValues {
  title: string;
  company?: string;
  location?: string;
  url?: string;
  contact: string;
  apply_whatsapp?: string;
  jobtype: JobType;
  remote: boolean;
  salary_min?: number;
  salary_max?: number;
  salary_currency?: SalaryCurrency;
  salary_period?: SalaryPeriod;
  description: string;
  country: string;
  recaptcha_token?: string;
}

export interface ApiErrorShape {
  detail?: string | { message?: string };
  message?: string;
  errors?: Record<string, string[]>;
  [key: string]: unknown;
}

export interface AuthUser {
  id: string;
  name?: string;
  email?: string;
  roles?: string[];
}
