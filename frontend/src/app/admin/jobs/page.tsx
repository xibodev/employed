"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AdminJobTable } from "@/components/admin/AdminJobTable";
import { AdminUsersList } from "@/components/admin/AdminUsersList";
import { ReportsPanel } from "@/components/admin/ReportsPanel";
import { StatusTabs } from "@/components/admin/StatusTabs";
import { useAuth } from "@/contexts/AuthContext";
import { apiFetch } from "@/lib/api";
import type { AuthUser, Job } from "@/lib/types";

type AdminJob = Job & {
  _id?: string;
  id?: string;
  title?: string | null;
  status?: string | null;
  company?: string | null;
  createdAt?: string | null;
  created_at?: string | null;
  userName?: string | null;
  owner_name?: string | null;
  poster?: { name?: string | null; email?: string | null };
};

type AdminUser = AuthUser & {
  _id?: string;
  id?: string;
  roles?: string[];
  name?: string;
  email?: string;
};

type ReportItem = {
  id: string;
  jobTitle: string;
  reason: string;
  details?: string;
  createdAt?: string;
};

function jobId(job: AdminJob) {
  return job.id ?? job._id ?? "";
}

function AdminJobsContent() {
  const router = useRouter();
  const { user, isLoading, isAdmin } = useAuth();
  const [status, setStatus] = useState("pending");
  const [jobs, setJobs] = useState<AdminJob[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [adminUsers, setAdminUsers] = useState<AdminUser[]>([]);
  const [reports, setReports] = useState<ReportItem[]>([]);
  const [panelErrors, setPanelErrors] = useState<{ jobs?: string; users?: string; reports?: string }>({});

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace("/sign-in?redirect=/admin/jobs");
      return;
    }

    if (!isLoading && user && !isAdmin) {
      router.replace("/");
    }
  }, [isAdmin, isLoading, router, user]);

  const loadAdminState = useCallback(async () => {
    // EMP-026b: each panel loads independently so one failed request (e.g. a
    // 500 from /admin/reports) cannot blank the whole moderation dashboard.
    const [jobsResult, usersResult, reportsResult] = await Promise.allSettled([
      apiFetch<{ items: AdminJob[]; total: number; page: number; page_size: number }>("/admin/jobs", {
        query: { status },
        cache: "no-store",
      }),
      apiFetch<AdminUser[]>("/admin/users", { cache: "no-store" }),
      apiFetch<ReportItem[]>("/admin/reports", { cache: "no-store" }),
    ]);

    const reasonMessage = (reason: unknown, fallback: string) =>
      reason instanceof Error ? reason.message : fallback;

    if (jobsResult.status === "fulfilled") {
      setJobs(jobsResult.value.items ?? []);
      setCounts({ [status]: jobsResult.value.total ?? 0 });
    } else {
      setJobs([]);
      setCounts({});
    }
    setAdminUsers(usersResult.status === "fulfilled" ? (usersResult.value ?? []) : []);
    setReports(reportsResult.status === "fulfilled" ? (reportsResult.value ?? []) : []);
    setSelectedIds([]);
    setPanelErrors({
      jobs: jobsResult.status === "rejected" ? reasonMessage(jobsResult.reason, "Unable to load jobs.") : undefined,
      users: usersResult.status === "rejected" ? reasonMessage(usersResult.reason, "Unable to load users.") : undefined,
      reports:
        reportsResult.status === "rejected" ? reasonMessage(reportsResult.reason, "Unable to load reports.") : undefined,
    });
  }, [status]);

  useEffect(() => {
    if (user && isAdmin) {
      void loadAdminState();
    }
  }, [isAdmin, loadAdminState, user]);

  const handleToggleSelection = (id: string) => {
    setSelectedIds((current) => (current.includes(id) ? current.filter((value) => value !== id) : [...current, id]));
  };

  const handleToggleAll = (checked: boolean) => {
    setSelectedIds(checked ? jobs.map((job) => jobId(job)) : []);
  };

  const handleBulkApply = async (nextStatus: string, reason: string) => {
    await apiFetch<void>("/admin/jobs/bulk-status", {
      method: "PATCH",
      body: {
        job_ids: selectedIds,
        status: nextStatus,
        reason,
      },
      cache: "no-store",
    });
    await loadAdminState();
  };

  const handleRowStatusChange = async (job: AdminJob, nextStatus: string, reason: string) => {
    await apiFetch<void>(`/admin/jobs/${jobId(job)}/status`, {
      method: "PATCH",
      body: { status: nextStatus, reason },
      cache: "no-store",
    });
    await loadAdminState();
  };

  const handleSearchUsers = useCallback(async (query: string) => {
    return apiFetch<AdminUser[]>("/admin/users", { query: { q: query }, cache: "no-store" });
  }, []);

  const handleGrantAdmin = async (adminUser: AdminUser) => {
    await apiFetch<void>(`/admin/users/${adminUser.id ?? adminUser._id}/roles/admin`, {
      method: "POST",
      cache: "no-store",
    });
    await loadAdminState();
  };

  const handleRevokeAdmin = async (adminUser: AdminUser) => {
    await apiFetch<void>(`/admin/users/${adminUser.id ?? adminUser._id}/roles/admin`, {
      method: "DELETE",
      cache: "no-store",
    });
    await loadAdminState();
  };

  const handleResolveReport = async (report: ReportItem) => {
    await apiFetch<void>(`/reports/${report.id}/resolve`, {
      method: "PATCH",
      body: { resolution: "reviewed" },
      cache: "no-store"
    });
    await loadAdminState();
  };

  const handleDismissReport = async (report: ReportItem) => {
    await apiFetch<void>(`/reports/${report.id}/resolve`, {
      method: "PATCH",
      body: { resolution: "dismissed" },
      cache: "no-store"
    });
    await loadAdminState();
  };

  const derivedCounts = useMemo(() => ({ ...counts, [status]: counts[status] ?? jobs.length }), [counts, jobs.length, status]);

  return (
    <main className="min-h-screen bg-[#1a1a2e] px-4 py-12">
      <div className="mx-auto grid max-w-7xl gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <section className="space-y-6">
          <div className="space-y-2">
            <h1 className="text-3xl font-semibold text-[#e4e4e7]">Admin job moderation</h1>
            <p className="text-sm text-[#a1a1aa]">Review submissions, update statuses, and manage moderation operations.</p>
          </div>

          <StatusTabs value={status} counts={derivedCounts} onChange={setStatus} />
          {panelErrors.jobs ? (
            <p className="rounded-2xl bg-red-500/10 px-4 py-3 text-sm text-red-300">{panelErrors.jobs}</p>
          ) : null}
          <AdminJobTable
            jobs={jobs}
            selectedIds={selectedIds}
            onToggleSelection={handleToggleSelection}
            onToggleAll={handleToggleAll}
            onBulkApply={handleBulkApply}
            onClearSelection={() => setSelectedIds([])}
            onRowStatusChange={handleRowStatusChange}
          />
        </section>

        <aside className="space-y-6">
          {panelErrors.users ? (
            <p className="rounded-2xl bg-red-500/10 px-4 py-3 text-sm text-red-300">{panelErrors.users}</p>
          ) : null}
          <AdminUsersList
            users={adminUsers}
            onGrant={handleGrantAdmin}
            onRevoke={handleRevokeAdmin}
            onSearch={handleSearchUsers}
          />
          {panelErrors.reports ? (
            <p className="rounded-2xl bg-red-500/10 px-4 py-3 text-sm text-red-300">{panelErrors.reports}</p>
          ) : null}
          <ReportsPanel reports={reports} onResolve={handleResolveReport} onDismiss={handleDismissReport} />
        </aside>
      </div>
    </main>
  );
}

export default function AdminJobsPage() {
  return <AdminJobsContent />;
}
