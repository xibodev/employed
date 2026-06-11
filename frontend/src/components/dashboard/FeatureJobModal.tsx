"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { apiFetch } from "@/lib/api";
import { MARKETS, resolveMarketFromHostname } from "@/lib/market";
import type { MarketKey } from "@/lib/types";
import { PaymentPoller } from "./PaymentPoller";

const PROVIDER_META: Record<string, { label: string; descriptionKey: string }> = {
  stripe: { label: "Stripe", descriptionKey: "stripeDesc" },
  mpesa: { label: "M-Pesa", descriptionKey: "mpesaDesc" },
  emola: { label: "e-Mola", descriptionKey: "emolaDesc" },
};


interface ProviderSnapshot {
  key: string;
  name?: string;
  simulator?: boolean;
  ui?: { collect?: "msisdn" | "redirect" | "none" };
}

interface FeatureJobModalProps {
  isOpen: boolean;
  jobId: string;
  jobTitle: string;
  marketKey?: MarketKey | string;
  onClose: () => void;
  onCompleted?: () => void;
}

function sanitizeMsisdn(msisdn: string) {
  return msisdn.replace(/\D+/g, "");
}

const STATUS_KEYS: Record<string, string> = {
  pending: "statusPending",
  awaiting_user: "statusAwaitingUser",
  completed: "statusCompleted",
  failed: "statusFailed",
  cancelled: "statusCancelled",
  expired: "statusExpired",
};

function statuslabel(t: (key: string) => string, status: string) {
  const key = STATUS_KEYS[status];
  return key ? t(key) : status.replace(/_/g, " ");
}

function validateMsisdn(provider: string, msisdn: string) {
  if (provider === "mpesa") {
    return /^(84|85)\d{7}$/.test(msisdn);
  }
  if (provider === "emola") {
    return /^(86|87)\d{7}$/.test(msisdn);
  }
  return true;
}

export function FeatureJobModal({ isOpen, jobId, jobTitle, marketKey, onClose, onCompleted }: FeatureJobModalProps) {
  const t = useTranslations("featurePayment");
  const inferredMarketKey = useMemo<MarketKey>(() => {
    if (marketKey === "mx" || marketKey === "mz") {
      return marketKey;
    }

    if (typeof window === "undefined") {
      return "mz";
    }

    return resolveMarketFromHostname(window.location.hostname).key;
  }, [marketKey]);

  const [providers, setProviders] = useState<ProviderSnapshot[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string | null>(null);
  const [msisdn, setMsisdn] = useState("");
  const [paymentId, setPaymentId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!isOpen) {
      setSelectedProvider(null);
      setMsisdn("");
      setPaymentId(null);
      setError(null);
      setIsLoading(false);
      return;
    }

    let active = true;

    const loadProviders = async () => {
      try {
        const payload = await apiFetch<{ providers?: ProviderSnapshot[] }>("/payments/providers", {
          query: { market: inferredMarketKey },
          cache: "no-store",
        });
        if (!active) {
          return;
        }
        setProviders(payload.providers ?? []);
      } catch {
        if (!active) {
          return;
        }
        setProviders(
          MARKETS[inferredMarketKey].paymentProviders.map((key) => ({
            key,
            name: PROVIDER_META[key]?.label ?? key,
            ui: key === "stripe" ? { collect: "redirect" } : { collect: "msisdn" },
          })),
        );
      }
    };

    void loadProviders();

    return () => {
      active = false;
    };
  }, [inferredMarketKey, isOpen]);

  const currentProvider = useMemo(
    () => providers.find((provider) => provider.key === selectedProvider) ?? null,
    [providers, selectedProvider],
  );

  const submitFeature = async () => {
    if (!selectedProvider) {
      setError(t("chooseProvider"));
      return;
    }

    const digits = sanitizeMsisdn(msisdn);
    if (currentProvider?.ui?.collect === "msisdn" && !validateMsisdn(selectedProvider, digits)) {
      setError(selectedProvider === "mpesa" ? t("msisdnMpesa") : t("msisdnEmola"));
      return;
    }

    setError(null);
    setIsLoading(true);

    try {
      const payload = await apiFetch<Record<string, unknown>>("/payments/initiate", {
        method: "POST",
        body: {
          job_id: jobId,
          provider_key: selectedProvider,
          payer_msisdn: digits || undefined,
        },
        cache: "no-store",
      });
      const redirectUrl =
        (payload.redirect_url as string | undefined) ??
        (payload.redirectUrl as string | undefined) ??
        (payload.url as string | undefined);
      const nextPaymentId =
        (payload.intent_id as string | undefined) ??
        (payload.paymentId as string | undefined) ??
        (payload.intentId as string | undefined) ??
        null;
      const kind = (payload.kind as string | undefined) ?? (redirectUrl ? "redirect" : "await");

      if (kind === "redirect" && redirectUrl) {
        window.location.assign(redirectUrl);
        return;
      }

      setPaymentId(nextPaymentId);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : t("initiateError"));
    } finally {
      setIsLoading(false);
    }
  };

  const cancelPayment = async () => {
    if (!paymentId) {
      return;
    }

    await apiFetch<void>(`/payments/${paymentId}/cancel`, { method: "POST", cache: "no-store" });
    setPaymentId(null);
    setSelectedProvider(null);
  };

  const handleResolved = (status: string) => {
    if (status === "completed") {
      onCompleted?.();
      onClose();
      return;
    }

    if (status !== "pending" && status !== "awaiting_user") {
      setError(t("paymentFailed", { status: statuslabel(t, status) }));
      setPaymentId(null);
    }
  };

  if (!isOpen) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#020617]/80 p-4 backdrop-blur-sm">
      <div className="w-full max-w-2xl rounded-3xl border border-white/10 bg-[#16213e] p-6 shadow-2xl shadow-black/40">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-2xl font-semibold text-[#e4e4e7]">{t("title")}</h3>
            <p className="mt-2 text-sm text-[#a1a1aa]">{t("promote", { title: jobTitle })}</p>
          </div>
          <button type="button" onClick={onClose} className="text-sm text-[#a1a1aa] transition hover:text-white">
            {t("close")}
          </button>
        </div>

        <div className="mt-6 grid gap-3 md:grid-cols-3">
          {providers.map((provider) => {
            const meta = PROVIDER_META[provider.key] ?? { label: provider.name ?? provider.key, descriptionKey: "paySecurely" };
            const active = selectedProvider === provider.key;
            return (
              <button
                key={provider.key}
                type="button"
                onClick={() => setSelectedProvider(provider.key)}
                className={`rounded-2xl border px-4 py-4 text-left transition ${
                  active ? "border-[#4F46E5] bg-[#4F46E5]/10" : "border-white/10 bg-[#0f172a]/50 hover:bg-white/5"
                }`}
              >
                <p className="text-sm font-semibold text-[#e4e4e7]">{meta.label}</p>
                <p className="mt-2 text-sm text-[#a1a1aa]">{t(meta.descriptionKey)}</p>
                {provider.simulator ? <p className="mt-3 text-xs uppercase tracking-[0.2em] text-[#F59E0B]">{t("simulator")}</p> : null}
              </button>
            );
          })}
        </div>

        {currentProvider?.ui?.collect === "msisdn" ? (
          <div className="mt-6 space-y-2">
            <label className="text-sm font-medium text-[#e4e4e7]" htmlFor="feature-msisdn">
              {t("mobileNumber")}
            </label>
            <input
              id="feature-msisdn"
              value={msisdn}
              onChange={(event) => setMsisdn(event.target.value)}
              className="w-full rounded-xl border border-white/10 bg-[#0f172a]/70 px-4 py-3 text-sm text-[#e4e4e7] outline-none placeholder:text-[#71717a] focus:border-[#4F46E5] focus:ring-2 focus:ring-[#4F46E5]/30"
              placeholder={selectedProvider === "mpesa" ? "84xxxxxxx" : "86xxxxxxx"}
            />
          </div>
        ) : null}

        {paymentId ? (
          <div className="mt-6">
            <PaymentPoller paymentId={paymentId} onResolved={handleResolved} onCancel={cancelPayment} />
          </div>
        ) : null}

        {error ? <p className="mt-4 rounded-xl bg-red-500/10 px-4 py-3 text-sm text-red-300">{error}</p> : null}

        {!paymentId ? (
          <div className="mt-6 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => void submitFeature()}
              disabled={isLoading || !selectedProvider}
              className="rounded-xl bg-[#4F46E5] px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#4338ca] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isLoading ? t("startingPayment") : t("continue")}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl border border-white/10 px-4 py-3 text-sm font-medium text-[#e4e4e7] transition hover:bg-white/5"
            >
              {t("cancel")}
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
