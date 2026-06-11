"use client";

import Link from "next/link";
import { type FormEvent, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useAuth } from "@/contexts/AuthContext";
import { OAuthButtons } from "./OAuthButtons";

const inputClassName =
  "w-full rounded-xl border border-white/10 bg-[#0f172a]/70 px-4 py-3 text-sm text-[#e4e4e7] outline-none placeholder:text-[#71717a] focus:border-[#4F46E5] focus:ring-2 focus:ring-[#4F46E5]/30";

function getPasswordStrength(password: string) {
  const checks = [password.length >= 8, /[A-Z]/.test(password), /[a-z]/.test(password), /\d/.test(password), /[^A-Za-z0-9]/.test(password)];
  const score = checks.filter(Boolean).length;

  if (score <= 2) {
    return { labelKey: "strengthWeak", color: "bg-red-500", width: "w-1/3" } as const;
  }
  if (score <= 4) {
    return { labelKey: "strengthMedium", color: "bg-[#F59E0B]", width: "w-2/3" } as const;
  }
  return { labelKey: "strengthStrong", color: "bg-emerald-500", width: "w-full" } as const;
}

interface RegisterFormProps {
  onSuccess?: () => void;
}

export function RegisterForm({ onSuccess }: RegisterFormProps) {
  const t = useTranslations("auth");
  const { register, loginWithOAuth } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const strength = useMemo(() => getPasswordStrength(password), [password]);
  const passwordMismatch = confirmPassword.length > 0 && confirmPassword !== password;
  const isDisabled = isSubmitting || !name.trim() || !email.trim() || password.length < 8 || passwordMismatch;

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);

    if (passwordMismatch) {
      setError(t("passwordsMismatch"));
      return;
    }

    setIsSubmitting(true);
    try {
      await register(email.trim(), password, name.trim());
      onSuccess?.();
    } catch (submitError) {
      const message = submitError instanceof Error ? submitError.message : t("registerError");
      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="rounded-3xl border border-white/10 bg-[#16213e] p-8 shadow-2xl shadow-black/30">
      <div className="mb-8 space-y-2">
        <h1 className="text-3xl font-semibold text-[#e4e4e7]">{t("registerTitle")}</h1>
        <p className="text-sm text-[#a1a1aa]">{t("registerSubtitle")}</p>
      </div>

      <form className="space-y-4" onSubmit={handleSubmit}>
        <div className="space-y-2">
          <label className="text-sm font-medium text-[#e4e4e7]" htmlFor="register-name">
            {t("fullName")}
          </label>
          <input
            id="register-name"
            autoComplete="name"
            className={inputClassName}
            placeholder={t("namePlaceholder")}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-[#e4e4e7]" htmlFor="register-email">
            {t("email")}
          </label>
          <input
            id="register-email"
            type="email"
            autoComplete="email"
            className={inputClassName}
            placeholder={t("registerEmailPlaceholder")}
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-[#e4e4e7]" htmlFor="register-password">
            {t("password")}
          </label>
          <input
            id="register-password"
            type="password"
            autoComplete="new-password"
            className={inputClassName}
            placeholder={t("passwordHint")}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <div className="space-y-2">
            {password.length > 0 ? (
              <>
                <div className="h-2 rounded-full bg-white/10">
                  <div className={`h-2 rounded-full ${strength.color} ${strength.width}`} />
                </div>
                <p className="text-xs text-[#a1a1aa]">{t("passwordStrength", { label: t(strength.labelKey) })}</p>
              </>
            ) : null}
          </div>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-[#e4e4e7]" htmlFor="register-confirm-password">
            {t("confirmPassword")}
          </label>
          <input
            id="register-confirm-password"
            type="password"
            autoComplete="new-password"
            className={inputClassName}
            placeholder={t("confirmPasswordPlaceholder")}
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
          />
          {passwordMismatch ? <p className="text-xs text-red-300">{t("passwordsMismatch")}</p> : null}
        </div>

        {error ? <p className="rounded-xl bg-red-500/10 px-4 py-3 text-sm text-red-300">{error}</p> : null}

        <button
          type="submit"
          disabled={isDisabled}
          className="w-full rounded-xl bg-[#4F46E5] px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#4338ca] disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isSubmitting ? t("creatingAccount") : t("createAccountButton")}
        </button>
      </form>

      <div className="my-6 flex items-center gap-4 text-xs uppercase tracking-[0.2em] text-[#71717a]">
        <span className="h-px flex-1 bg-white/10" />
        <span>{t("or")}</span>
        <span className="h-px flex-1 bg-white/10" />
      </div>

      <OAuthButtons disabled={isSubmitting} onProviderClick={loginWithOAuth} />

      <p className="mt-6 text-center text-sm text-[#a1a1aa]">
        {t("haveAccount")}{" "}
        <Link className="font-medium text-[#F59E0B] hover:text-[#fbbf24]" href="/sign-in">
          {t("signInButton")}
        </Link>
      </p>
    </div>
  );
}
