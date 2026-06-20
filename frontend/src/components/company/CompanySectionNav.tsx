"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";

import { classNames } from "@/lib/utils";

const SECTIONS = [
  { href: "/company", key: "navDashboard" },
  { href: "/company/members", key: "navMembers" },
  { href: "/company/verification", key: "navVerification" },
] as const;

/** Tab navigation shared across the company management segments. */
export function CompanySectionNav() {
  const t = useTranslations("company");
  const pathname = usePathname();

  return (
    <nav className="flex flex-wrap gap-2" aria-label={t("navLabel")}>
      {SECTIONS.map((section) => {
        const isActive = pathname === section.href;
        return (
          <Link
            key={section.href}
            href={section.href}
            aria-current={isActive ? "page" : undefined}
            className={classNames(
              "rounded-xl border px-4 py-2 text-sm font-medium transition",
              isActive
                ? "border-indigo-500/40 bg-indigo-500/10 text-indigo-200"
                : "border-white/10 text-[#a1a1aa] hover:border-white/20 hover:text-[#e4e4e7]",
            )}
          >
            {t(section.key)}
          </Link>
        );
      })}
    </nav>
  );
}
