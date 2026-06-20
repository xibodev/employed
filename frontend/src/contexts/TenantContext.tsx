"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import {
  getStoredActiveCompanyId,
  selectActiveCompany,
  setStoredActiveCompanyId,
  type CompanyMembership,
} from "@/lib/tenant";

interface TenantState {
  /** The company the user is currently acting on behalf of (null for pure job seekers). */
  activeCompany: CompanyMembership | null;
  /** Every membership the user holds, across all companies (R2.11). */
  memberships: CompanyMembership[];
}

interface TenantActions {
  /** Switch the active company by its company id; ignores unknown/inactive ids. */
  setActiveCompany: (companyId: string | null) => void;
}

type TenantContextValue = TenantState & TenantActions;

const TenantContext = createContext<TenantContextValue | null>(null);

export function TenantProvider({
  memberships = [],
  children,
}: {
  memberships?: CompanyMembership[];
  children: ReactNode;
}) {
  // Initialise from the persisted selection so a returning user lands back in
  // the company they were last working in.
  const [activeCompanyId, setActiveCompanyId] = useState<string | null>(() =>
    selectActiveCompany(memberships, getStoredActiveCompanyId())?.id ?? null,
  );

  // Re-resolve whenever the membership set changes (e.g. after login/refresh).
  // The functional updater reconciles against the current selection without
  // needing it in the dependency list.
  useEffect(() => {
    setActiveCompanyId((current) => selectActiveCompany(memberships, current ?? getStoredActiveCompanyId())?.id ?? null);
  }, [memberships]);

  const setActiveCompany = useCallback(
    (companyId: string | null) => {
      const resolved = selectActiveCompany(memberships, companyId);
      setActiveCompanyId(resolved?.id ?? null);
      setStoredActiveCompanyId(resolved?.id ?? null);
    },
    [memberships],
  );

  const value = useMemo<TenantContextValue>(() => {
    const activeCompany = memberships.find((membership) => membership.id === activeCompanyId) ?? null;
    return {
      activeCompany,
      memberships,
      setActiveCompany,
    };
  }, [activeCompanyId, memberships, setActiveCompany]);

  return <TenantContext.Provider value={value}>{children}</TenantContext.Provider>;
}

export function useTenant() {
  const context = useContext(TenantContext);
  if (!context) {
    throw new Error("useTenant must be used within a TenantProvider.");
  }
  return context;
}
