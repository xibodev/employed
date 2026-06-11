"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { apiFetch } from "@/lib/api";

type VerifyState = "loading" | "success" | "already-verified" | "error";

export function VerifyEmail({ token }: { token: string }) {
  const t = useTranslations("auth");
  const [state, setState] = useState<VerifyState>("loading");

  useEffect(() => {
    let active = true;

    const verify = async () => {
      try {
        const payload = await apiFetch<{ status?: string; message?: string }>(`/auth/verify-email/${token}`, {
          method: "POST",
          cache: "no-store",
        });
        if (!active) {
          return;
        }

        if (payload?.status === "already-verified") {
          setState("already-verified");
          return;
        }

        setState("success");
      } catch {
        if (!active) {
          return;
        }
        setState("error");
      }
    };

    void verify();

    return () => {
      active = false;
    };
  }, [token]);

  const message =
    state === "loading"
      ? t("verifying")
      : state === "success"
        ? t("verifySuccess")
        : state === "already-verified"
          ? t("verifyAlready")
          : t("verifyError");

  const tone = state === "error" ? "text-red-300" : state === "success" ? "text-emerald-200" : "text-[#a1a1aa]";

  return (
    <div className="rounded-3xl border border-white/10 bg-[#16213e] p-8 shadow-2xl shadow-black/30">
      <h1 className="text-3xl font-semibold text-[#e4e4e7]">{t("verifyTitle")}</h1>
      <p className={`mt-4 text-sm ${tone}`}>{message}</p>
      <div className="mt-6 flex flex-wrap gap-3">
        <Link className="rounded-xl bg-[#4F46E5] px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#4338ca]" href="/sign-in">
          {t("goToSignIn")}
        </Link>
        <Link className="rounded-xl border border-white/10 px-4 py-3 text-sm font-medium text-[#e4e4e7] transition hover:bg-white/5" href="/">
          {t("returnHome")}
        </Link>
      </div>
    </div>
  );
}
