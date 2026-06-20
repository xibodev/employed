"use client";

import { useState, type FormEvent } from "react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { companyToMembership } from "@/components/company/utils";
import { useTenant } from "@/contexts/TenantContext";
import { createCompany } from "@/lib/api";
import { upsertStoredMembership } from "@/lib/tenant-store";
import type { Company } from "@/lib/types";

/**
 * Creates a Company (`POST /companies`). On success the creator is the active
 * `org_owner`, so the new company is stored as an active membership and selected
 * as the tenant context.
 */
export function CreateCompanyForm({ onCreated }: { onCreated?: (company: Company) => void }) {
  const t = useTranslations("company");
  const { setActiveCompany } = useTenant();
  const [name, setName] = useState("");
  const [website, setWebsite] = useState("");
  const [description, setDescription] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!name.trim()) {
      return;
    }
    setIsSubmitting(true);
    setError(null);
    try {
      const company = await createCompany({
        name: name.trim(),
        website: website.trim() || undefined,
        description: description.trim() || undefined,
      });
      // The creator becomes the active org_owner (R2.4).
      upsertStoredMembership(companyToMembership(company, "org_owner", "active"));
      setActiveCompany(company.id);
      setName("");
      setWebsite("");
      setDescription("");
      onCreated?.(company);
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : t("createError"));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4 rounded-2xl border border-white/10 bg-[#16213e] p-6">
      <div>
        <h2 className="text-lg font-semibold text-[#e4e4e7]">{t("createTitle")}</h2>
        <p className="mt-1 text-sm text-[#a1a1aa]">{t("createSubtitle")}</p>
      </div>

      <Input
        label={t("nameLabel")}
        name="name"
        value={name}
        onChange={(event) => setName(event.target.value)}
        required
        maxLength={256}
      />
      <Input
        label={t("websiteLabel")}
        name="website"
        type="url"
        value={website}
        onChange={(event) => setWebsite(event.target.value)}
        placeholder="https://example.com"
      />
      <label className="flex flex-col gap-2 text-sm text-zinc-300" htmlFor="company-description">
        <span className="font-medium text-zinc-100">{t("descriptionLabel")}</span>
        <textarea
          id="company-description"
          name="description"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          rows={3}
          className="rounded-xl border border-zinc-800 bg-[#111827] px-3 py-2 text-zinc-100 outline-none transition placeholder:text-zinc-500 focus:border-indigo-500"
        />
      </label>

      {error ? <p className="rounded-xl bg-rose-500/10 px-3 py-2 text-xs text-rose-300">{error}</p> : null}

      <Button type="submit" disabled={isSubmitting || !name.trim()}>
        {isSubmitting ? t("creating") : t("createAction")}
      </Button>
    </form>
  );
}
