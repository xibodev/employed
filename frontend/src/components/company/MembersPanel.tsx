"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useTranslations } from "next-intl";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { TENANT_ROLE_VALUES, membershipStatusVariant } from "@/components/company/utils";
import { ApiError, acceptMembership, inviteMember, listMembers, suspendMembership } from "@/lib/api";
import type { CompanyMembership } from "@/lib/tenant";
import type { Membership, TenantRoleValue } from "@/lib/types";

/** Member list with invite / accept / suspend actions (R2.6, R2.7, R2.9). */
export function MembersPanel({ activeCompany }: { activeCompany: CompanyMembership }) {
  const t = useTranslations("members");
  const companyId = activeCompany.id;

  const [members, setMembers] = useState<Membership[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [inviteUserId, setInviteUserId] = useState("");
  const [inviteRole, setInviteRole] = useState<TenantRoleValue>("member");
  const [isInviting, setIsInviting] = useState(false);
  const [pendingId, setPendingId] = useState<string | null>(null);

  const loadMembers = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      setMembers(await listMembers(companyId));
    } catch (loadError) {
      if (loadError instanceof ApiError && loadError.status === 403) {
        setError(t("forbidden"));
      } else {
        setError(loadError instanceof Error ? loadError.message : t("loadError"));
      }
    } finally {
      setIsLoading(false);
    }
  }, [companyId, t]);

  useEffect(() => {
    void loadMembers();
  }, [loadMembers]);

  const handleInvite = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!inviteUserId.trim()) {
      return;
    }
    setIsInviting(true);
    setError(null);
    setNotice(null);
    try {
      await inviteMember(companyId, { user_id: inviteUserId.trim(), role: inviteRole });
      setInviteUserId("");
      setInviteRole("member");
      setNotice(t("inviteSuccess"));
      await loadMembers();
    } catch (inviteError) {
      setError(inviteError instanceof Error ? inviteError.message : t("inviteError"));
    } finally {
      setIsInviting(false);
    }
  };

  const handleAccept = async (membership: Membership) => {
    setPendingId(membership.id);
    setError(null);
    setNotice(null);
    try {
      await acceptMembership(companyId, membership.id);
      setNotice(t("acceptSuccess"));
      await loadMembers();
    } catch (acceptError) {
      setError(acceptError instanceof Error ? acceptError.message : t("acceptError"));
    } finally {
      setPendingId(null);
    }
  };

  const handleSuspend = async (membership: Membership) => {
    if (!window.confirm(t("suspendConfirm"))) {
      return;
    }
    setPendingId(membership.id);
    setError(null);
    setNotice(null);
    try {
      await suspendMembership(companyId, membership.id);
      setNotice(t("suspendSuccess"));
      await loadMembers();
    } catch (suspendError) {
      setError(suspendError instanceof Error ? suspendError.message : t("suspendError"));
    } finally {
      setPendingId(null);
    }
  };

  return (
    <div className="space-y-6">
      <form onSubmit={handleInvite} className="space-y-4 rounded-2xl border border-white/10 bg-[#16213e] p-6">
        <div>
          <h2 className="text-lg font-semibold text-[#e4e4e7]">{t("inviteTitle")}</h2>
          <p className="mt-1 text-sm text-[#a1a1aa]">{t("inviteSubtitle")}</p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Input
            label={t("userIdLabel")}
            name="userId"
            value={inviteUserId}
            onChange={(event) => setInviteUserId(event.target.value)}
            placeholder={t("userIdPlaceholder")}
            required
          />
          <Select
            label={t("roleLabel")}
            name="role"
            value={inviteRole}
            onChange={(event) => setInviteRole(event.target.value as TenantRoleValue)}
            options={TENANT_ROLE_VALUES.map((role) => ({ value: role, label: t(`role.${role}`) }))}
          />
        </div>
        <Button type="submit" disabled={isInviting || !inviteUserId.trim()}>
          {isInviting ? t("inviting") : t("inviteAction")}
        </Button>
      </form>

      {notice ? <p className="rounded-2xl bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">{notice}</p> : null}
      {error ? <p className="rounded-2xl bg-rose-500/10 px-4 py-3 text-sm text-rose-300">{error}</p> : null}

      <div className="overflow-hidden rounded-2xl border border-white/10 bg-[#16213e]">
        <div className="border-b border-white/10 px-6 py-4">
          <h2 className="text-lg font-semibold text-[#e4e4e7]">{t("listTitle")}</h2>
        </div>

        {isLoading ? (
          <p className="px-6 py-6 text-sm text-[#a1a1aa]">{t("loading")}</p>
        ) : members.length === 0 ? (
          <p className="px-6 py-6 text-sm text-[#71717a]">{t("empty")}</p>
        ) : (
          <ul className="divide-y divide-white/10">
            {members.map((member) => (
              <li key={member.id} className="flex flex-col gap-3 px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="space-y-1">
                  <p className="text-sm font-medium text-[#e4e4e7]">{member.user_id}</p>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="default">{t(`role.${member.role}`)}</Badge>
                    <Badge variant={membershipStatusVariant(member.status)}>{t(`status.${member.status}`)}</Badge>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  {member.status === "invited" ? (
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={pendingId === member.id}
                      onClick={() => void handleAccept(member)}
                    >
                      {t("acceptAction")}
                    </Button>
                  ) : null}
                  {member.status !== "suspended" ? (
                    <Button
                      variant="danger"
                      size="sm"
                      disabled={pendingId === member.id}
                      onClick={() => void handleSuspend(member)}
                    >
                      {t("suspendAction")}
                    </Button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
