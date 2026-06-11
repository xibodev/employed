"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { LoginForm } from "@/components/auth/LoginForm";
import { useAuth } from "@/contexts/AuthContext";

function SignInContent() {
  const t = useTranslations("auth");
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, isLoading } = useAuth();
  const redirectTo = searchParams.get("redirect") || "/";
  const resetSuccess = searchParams.get("reset") === "success";

  useEffect(() => {
    if (!isLoading && user) {
      router.replace("/");
    }
  }, [isLoading, router, user]);

  return (
    <main className="min-h-screen bg-[#1a1a2e] px-4 py-16">
      <div className="mx-auto max-w-lg space-y-4">
        {resetSuccess ? <p className="rounded-2xl bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">{t("resetSuccessBanner")}</p> : null}
        <LoginForm onSuccess={() => router.replace(redirectTo)} />
      </div>
    </main>
  );
}

export default function SignInPage() {
  return <SignInContent />;
}
