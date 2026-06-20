"use client";

import { useEffect, useState, type ReactNode } from "react";

import { useAuth } from "@/contexts/AuthContext";
import { TenantProvider } from "@/contexts/TenantContext";
import { listMyMemberships } from "@/lib/api";
import type { CompanyMembership } from "@/lib/tenant";
import {
  MEMBERSHIPS_CHANGED_EVENT,
  MEMBERSHIPS_STORAGE_KEY,
  getStoredMemberships,
  replaceStoredMemberships,
} from "@/lib/tenant-store";

/**
 * Hydrates {@link TenantProvider} and keeps it in sync.
 *
 * Source of truth is the backend: when a user is authenticated it fetches
 * `GET /users/me/memberships` and reconciles the client store with that
 * authoritative set. The local store still seeds the first paint (instant,
 * survives reloads, supports optimistic create/link) and absorbs in-tab and
 * cross-tab changes via events — so the switcher updates without a reload while
 * the server remains canonical.
 */
export function TenantBootstrap({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [memberships, setMemberships] = useState<CompanyMembership[]>([]);

  useEffect(() => {
    const sync = () => setMemberships(getStoredMemberships());
    // Seed after mount to avoid a server/client hydration mismatch.
    sync();

    const handleStorage = (event: StorageEvent) => {
      if (event.key === null || event.key === MEMBERSHIPS_STORAGE_KEY) {
        sync();
      }
    };

    window.addEventListener(MEMBERSHIPS_CHANGED_EVENT, sync);
    window.addEventListener("storage", handleStorage);
    return () => {
      window.removeEventListener(MEMBERSHIPS_CHANGED_EVENT, sync);
      window.removeEventListener("storage", handleStorage);
    };
  }, []);

  // Reconcile with the authoritative server set whenever the auth identity
  // changes. On sign-out, clear the locally cached membership set so a previous
  // user's tenants never leak into the next session.
  useEffect(() => {
    if (!user) {
      replaceStoredMemberships([]);
      return;
    }

    let cancelled = false;
    void (async () => {
      try {
        const serverMemberships = await listMyMemberships();
        if (!cancelled) {
          replaceStoredMemberships(serverMemberships);
        }
      } catch {
        // Offline or transient failure: keep the locally stored set so the
        // switcher still works; a later navigation will retry.
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [user]);

  return <TenantProvider memberships={memberships}>{children}</TenantProvider>;
}
