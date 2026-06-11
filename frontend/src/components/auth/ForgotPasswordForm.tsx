"use client";

import Link from "next/link";
import { type FormEvent, useState } from "react";
import { useTranslations } from "next-intl";
import { apiFetch } from "@/lib/api";

const inputClassName =
  "w-full rounded-xl border border-white/10 bg-[#0f172a]/70 px-4 py-3 text-sm text-[#e4e4e7] outline-none placeholder:text-[#71717a] focus:border-[#4F46E5] focus:ring-2 focus:ring-[#4F46E5]/30";

export function ForgotPasswordForm() {
  const t = useTranslations("auth");
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setSuccess(null);
    setIsSubmitting(true);

    try {
      await apiFetch<void>("/auth/forgot-password", {
        method: "POST",
        body: { email: email.trim() },
        cache: "no-store",
      });
      setSuccess(t("forgotSuccess"));
    } catch (submitError) {
      const message = submitError instanceof Error ? submitError.message : t("forgotError");
      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="rounded-3xl border border-white/10 bg-[#16213e] p-8 shadow-2xl shadow-black/30">
      <div className="mb-8 space-y-2">
        <h1 className="text-3xl font-semibold text-[#e4e4e7]">{t("forgotTitle")}</h1>
        <p className="text-sm text-[#a1a1aa]">{t("forgotSubtitle")}</p>
      </div>

      <form className="space-y-4" onSubmit={handleSubmit}>
        <div className="space-y-2">
          <label className="text-sm font-medium text-[#e4e4e7]" htmlFor="forgot-password-email">
            {t("email")}
          </label>
          <input
            id="forgot-password-email"
            type="email"
            autoComplete="email"
            className={inputClassName}
            placeholder={t("emailPlaceholder")}
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>

        {success ? <p className="rounded-xl bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">{success}</p> : null}
        {error ? <p className="rounded-xl bg-red-500/10 px-4 py-3 text-sm text-red-300">{error}</p> : null}

        <button
          type="submit"
          disabled={isSubmitting || email.trim().length === 0}
          className="w-full rounded-xl bg-[#4F46E5] px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#4338ca] disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isSubmitting ? t("sendingReset") : t("sendReset")}
        </button>
      </form>

      <p className="mt-6 text-center text-sm text-[#a1a1aa]">
        {t("rememberedIt")}{" "}
        <Link className="font-medium text-[#F59E0B] hover:text-[#fbbf24]" href="/sign-in">
          {t("backToSignIn")}
        </Link>
      </p>
    </div>
  );
}
