"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";

function formatRemaining(ms: number) {
  const totalSeconds = Math.max(Math.floor(ms / 1000), 0);
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  return `${days}d ${hours}h ${minutes}m`;
}

interface DeletionSectionProps {
  scheduledFor?: string | null;
  onRequest: () => Promise<void>;
  onCancel: () => Promise<void>;
}

export function DeletionSection({ scheduledFor, onRequest, onCancel }: DeletionSectionProps) {
  const t = useTranslations("account");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [remainingMs, setRemainingMs] = useState<number | null>(null);

  useEffect(() => {
    if (!scheduledFor) {
      setRemainingMs(null);
      return;
    }

    const tick = () => setRemainingMs(new Date(scheduledFor).getTime() - Date.now());
    tick();
    const interval = window.setInterval(tick, 60_000);
    return () => window.clearInterval(interval);
  }, [scheduledFor]);

  const countdown = useMemo(() => (remainingMs === null ? null : formatRemaining(remainingMs)), [remainingMs]);

  const runAction = async (action: () => Promise<void>) => {
    setIsLoading(true);
    setError(null);
    try {
      await action();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : t("deletionError"));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <section className="rounded-2xl border border-red-500/20 bg-red-500/5 p-6">
      <div className="space-y-2">
        <h3 className="text-lg font-semibold text-[#e4e4e7]">{t("dangerTitle")}</h3>
        <p className="text-sm text-[#fca5a5]">{t("dangerBody")}</p>
        {scheduledFor ? (
          <p className="text-sm text-[#fecaca]">
            {t("deletionScheduled", { date: new Date(scheduledFor).toLocaleString() })}
            {countdown ? ` ${t("remainingSuffix", { countdown })}` : ""}
          </p>
        ) : null}
      </div>

      <div className="mt-4 flex flex-wrap gap-3">
        {scheduledFor ? (
          <button
            type="button"
            disabled={isLoading}
            onClick={() => void runAction(onCancel)}
            className="rounded-xl border border-white/10 px-4 py-3 text-sm font-medium text-[#e4e4e7] transition hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isLoading ? t("updating") : t("cancelDeletion")}
          </button>
        ) : (
          <button
            type="button"
            disabled={isLoading}
            onClick={() => void runAction(onRequest)}
            className="rounded-xl bg-red-500 px-4 py-3 text-sm font-semibold text-white transition hover:bg-red-400 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isLoading ? t("submitting") : t("deleteAccount")}
          </button>
        )}
      </div>

      {error ? <p className="mt-3 text-sm text-red-300">{error}</p> : null}
    </section>
  );
}
