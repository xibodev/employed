"use client";

import Link from "next/link";
import { type FormEvent, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useAuth } from "@/contexts/AuthContext";
import { OAuthButtons } from "./OAuthButtons";

const inputClassName =
  "w-full rounded-xl border border-white/10 bg-[#0f172a]/70 px-4 py-3 text-sm text-[#e4e4e7] outline-none placeholder:text-[#71717a] focus:border-[#4F46E5] focus:ring-2 focus:ring-[#4F46E5]/30";

interface LoginFormProps {
  onSuccess?: () => void;
}

export function LoginForm({ onSuccess }: LoginFormProps) {
  const t = useTranslations("auth");
  const { login, loginWithOAuth } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const isDisabled = useMemo(
    () => isSubmitting || email.trim().length === 0 || password.trim().length === 0,
    [email, isSubmitting, password],
  );

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      await login(email.trim(), password);
      onSuccess?.();
    } catch (submitError) {
      const message = submitError instanceof Error ? submitError.message : t("signInError");
      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="rounded-3xl border border-white/10 bg-[#16213e] p-8 shadow-2xl shadow-black/30">
      <div className="mb-8 space-y-2">
        <h1 className="text-3xl font-semibold text-[#e4e4e7]">{t("signInTitle")}</h1>
        <p className="text-sm text-[#a1a1aa]">{t("signInSubtitle")}</p>
      </div>

      <form className="space-y-4" onSubmit={handleSubmit}>
        <div className="space-y-2">
          <label className="text-sm font-medium text-[#e4e4e7]" htmlFor="login-email">
            {t("email")}
          </label>
          <input
            id="login-email"
            type="email"
            autoComplete="email"
            className={inputClassName}
            placeholder={t("emailPlaceholder")}
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-[#e4e4e7]" htmlFor="login-password">
              {t("password")}
            </label>
            <Link className="text-sm text-[#F59E0B] hover:text-[#fbbf24]" href="/forgot-password">
              {t("forgotPasswordLink")}
            </Link>
          </div>
          <input
            id="login-password"
            type="password"
            autoComplete="current-password"
            className={inputClassName}
            placeholder={t("passwordPlaceholder")}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>

        {error ? <p className="rounded-xl bg-red-500/10 px-4 py-3 text-sm text-red-300">{error}</p> : null}

        <button
          type="submit"
          disabled={isDisabled}
          className="w-full rounded-xl bg-[#4F46E5] px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#4338ca] disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isSubmitting ? t("signingIn") : t("signInButton")}
        </button>
      </form>

      <div className="my-6 flex items-center gap-4 text-xs uppercase tracking-[0.2em] text-[#71717a]">
        <span className="h-px flex-1 bg-white/10" />
        <span>{t("or")}</span>
        <span className="h-px flex-1 bg-white/10" />
      </div>

      <OAuthButtons disabled={isSubmitting} onProviderClick={loginWithOAuth} />

      <p className="mt-6 text-center text-sm text-[#a1a1aa]">
        {t("needAccount")}{" "}
        <Link className="font-medium text-[#F59E0B] hover:text-[#fbbf24]" href="/sign-up">
          {t("createOne")}
        </Link>
      </p>
    </div>
  );
}
