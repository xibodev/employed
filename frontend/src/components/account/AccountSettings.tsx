"use client";

import type { AuthUser } from "@/lib/types";
import { ExportDataButton } from "./ExportDataButton";
import { DeletionSection } from "./DeletionSection";

type AccountUser = AuthUser & {
  name?: string;
  email?: string;
  emails?: Array<{ address?: string; verified?: boolean }>;
  email_verified?: boolean;
  emailVerified?: boolean;
  deletionScheduledFor?: string;
};

interface AccountSettingsProps {
  user: AccountUser;
  isEmailVerified: boolean;
  onResendVerification?: () => Promise<void>;
  onRequestDeletion: () => Promise<void>;
  onCancelDeletion: () => Promise<void>;
  infoMessage?: string | null;
}

function primaryEmail(user: AccountUser) {
  return user.email ?? user.emails?.[0]?.address ?? "Unknown";
}

export function AccountSettings({
  user,
  isEmailVerified,
  onResendVerification,
  onRequestDeletion,
  onCancelDeletion,
  infoMessage,
}: AccountSettingsProps) {
  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-white/10 bg-[#16213e] p-6 shadow-lg shadow-black/20">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-2">
            <h1 className="text-3xl font-semibold text-[#e4e4e7]">Account settings</h1>
            <p className="text-sm text-[#a1a1aa]">Manage your profile, compliance data, and account lifecycle.</p>
          </div>
          <ExportDataButton />
        </div>

        <dl className="mt-6 grid gap-4 rounded-2xl border border-white/10 bg-[#0f172a]/40 p-5 sm:grid-cols-3">
          <div>
            <dt className="text-xs uppercase tracking-[0.2em] text-[#71717a]">Name</dt>
            <dd className="mt-2 text-sm text-[#e4e4e7]">{user.name ?? "Not provided"}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-[0.2em] text-[#71717a]">Email</dt>
            <dd className="mt-2 text-sm text-[#e4e4e7]">{primaryEmail(user)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-[0.2em] text-[#71717a]">Verification</dt>
            <dd className="mt-2 text-sm text-[#e4e4e7]">{isEmailVerified ? "Verified" : "Pending verification"}</dd>
          </div>
        </dl>

        {!isEmailVerified && onResendVerification ? (
          <div className="mt-6 flex flex-wrap items-center gap-3 rounded-2xl border border-amber-400/20 bg-amber-400/5 p-4 text-sm text-[#fde68a]">
            <span>Your email is not verified yet.</span>
            <button
              type="button"
              onClick={() => void onResendVerification()}
              className="rounded-xl bg-[#F59E0B] px-4 py-2 font-semibold text-[#1a1a2e] transition hover:bg-[#fbbf24]"
            >
              Resend verification email
            </button>
          </div>
        ) : null}

        {infoMessage ? <p className="mt-4 text-sm text-emerald-200">{infoMessage}</p> : null}
      </section>

      <DeletionSection
        scheduledFor={user.deletionScheduledFor ?? null}
        onRequest={onRequestDeletion}
        onCancel={onCancelDeletion}
      />
    </div>
  );
}
