"use client";

import { useTranslations } from "next-intl";

const PROVIDERS = [
  { key: "google", labelKey: "continueWithGoogle", color: "#4285F4" },
] as const;

interface OAuthButtonsProps {
  onProviderClick: (provider: string) => void;
  disabled?: boolean;
}

export function OAuthButtons({ onProviderClick, disabled = false }: OAuthButtonsProps) {
  const t = useTranslations("auth");
  return (
    <div className="space-y-3">
      {PROVIDERS.map((provider) => (
        <button
          key={provider.key}
          type="button"
          disabled={disabled}
          onClick={() => onProviderClick(provider.key)}
          className="flex w-full items-center justify-center rounded-xl border border-white/10 px-4 py-3 text-sm font-medium text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
          style={{ backgroundColor: provider.color }}
        >
          {t(provider.labelKey)}
        </button>
      ))}
    </div>
  );
}
