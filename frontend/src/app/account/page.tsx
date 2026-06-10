"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AccountSettings } from "@/components/account/AccountSettings";
import { useAuth } from "@/contexts/AuthContext";
import { apiFetch } from "@/lib/api";
import type { AuthUser } from "@/lib/types";

type AccountUser = AuthUser & {
  email_verified?: boolean;
  emailVerified?: boolean;
  deletionScheduledFor?: string;
};

function AccountContent() {
  const router = useRouter();
  const { user, isLoading, isEmailVerified, refreshToken } = useAuth();
  const [accountUser, setAccountUser] = useState<AccountUser | null>(null);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace("/sign-in?redirect=/account");
    }
  }, [isLoading, router, user]);

  useEffect(() => {
    if (user) {
      setAccountUser(user as AccountUser);
    }
  }, [user]);

  const resendVerification = async () => {
    await apiFetch<void>("/auth/resend-verification", { method: "POST", cache: "no-store" });
    setInfoMessage("Verification email sent. Check your inbox.");
  };

  const requestDeletion = async () => {
    const payload = await apiFetch<{ scheduledFor?: string }>("/users/me/deletion", {
      method: "POST",
      cache: "no-store",
    });
    setAccountUser((current) => (current ? { ...current, deletionScheduledFor: payload?.scheduledFor ?? current.deletionScheduledFor } : current));
    setInfoMessage("Account deletion requested. You can still cancel during the 30-day grace period.");
    await refreshToken();
  };

  const cancelDeletion = async () => {
    await apiFetch<void>("/users/me/deletion", { method: "DELETE", cache: "no-store" });
    setAccountUser((current) => (current ? { ...current, deletionScheduledFor: undefined } : current));
    setInfoMessage("Account deletion request canceled.");
    await refreshToken();
  };

  if (!accountUser) {
    return <main className="min-h-screen bg-[#1a1a2e] px-4 py-12 text-sm text-[#a1a1aa]">Loading account...</main>;
  }

  return (
    <main className="min-h-screen bg-[#1a1a2e] px-4 py-12">
      <div className="mx-auto max-w-5xl">
        <AccountSettings
          user={accountUser}
          isEmailVerified={isEmailVerified}
          onResendVerification={isEmailVerified ? undefined : resendVerification}
          onRequestDeletion={requestDeletion}
          onCancelDeletion={cancelDeletion}
          infoMessage={infoMessage}
        />
      </div>
    </main>
  );
}

export default function AccountPage() {
  return <AccountContent />;
}
