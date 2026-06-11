"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { RegisterForm } from "@/components/auth/RegisterForm";
import { useAuth } from "@/contexts/AuthContext";

function SignUpContent() {
  const t = useTranslations("auth");
  const router = useRouter();
  const { user, isLoading } = useAuth();
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (!isLoading && user) {
      router.replace("/");
    }
  }, [isLoading, router, user]);

  return (
    <main className="min-h-screen bg-[#1a1a2e] px-4 py-16">
      <div className="mx-auto max-w-lg space-y-4">
        {success ? (
          <div className="rounded-3xl border border-emerald-500/20 bg-emerald-500/10 p-8 text-sm text-emerald-100">
            <h1 className="text-2xl font-semibold text-white">{t("checkEmailTitle")}</h1>
            <p className="mt-3">{t("checkEmailBody")}</p>
            <Link className="mt-5 inline-flex font-medium text-[#F59E0B] hover:text-[#fbbf24]" href="/sign-in">
              {t("continueToSignIn")}
            </Link>
          </div>
        ) : (
          <RegisterForm onSuccess={() => setSuccess(true)} />
        )}
      </div>
    </main>
  );
}

export default function SignUpPage() {
  return <SignUpContent />;
}
