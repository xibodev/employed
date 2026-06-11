"use client";

import { type FormEvent, useState } from "react";
import type { AuthUser } from "@/lib/types";

type AdminUser = AuthUser & {
  _id?: string;
  id?: string;
  name?: string;
  email?: string;
  roles?: string[];
};

interface AdminUsersListProps {
  users: AdminUser[];
  onGrant: (user: AdminUser) => Promise<void>;
  onRevoke: (user: AdminUser) => Promise<void>;
  /** EMP-015: search ALL users (by email/name) to find someone to promote. */
  onSearch?: (query: string) => Promise<AdminUser[]>;
}

function userId(user: AdminUser) {
  return user.id ?? user._id ?? "";
}

export function AdminUsersList({ users, onGrant, onRevoke, onSearch }: AdminUsersListProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<AdminUser[] | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const handleSearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!onSearch) return;
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setResults(null);
      return;
    }
    setIsSearching(true);
    setSearchError(null);
    try {
      setResults(await onSearch(trimmed));
    } catch (error) {
      setSearchError(error instanceof Error ? error.message : "Search failed.");
      setResults(null);
    } finally {
      setIsSearching(false);
    }
  };

  const clearSearch = () => {
    setQuery("");
    setResults(null);
    setSearchError(null);
  };

  const visibleUsers = results ?? users;

  return (
    <section className="rounded-2xl border border-white/10 bg-[#16213e] p-5 shadow-lg shadow-black/20">
      <div className="mb-4">
        <h2 className="text-lg font-semibold text-[#e4e4e7]">Admin users</h2>
        <p className="text-sm text-[#a1a1aa]">Grant or revoke moderation access.</p>
      </div>

      {onSearch ? (
        <form onSubmit={handleSearch} className="mb-4 flex gap-2">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search users by email or name"
            className="w-full rounded-xl border border-white/10 bg-[#0f172a]/70 px-3 py-2 text-sm text-[#e4e4e7] outline-none placeholder:text-[#71717a] focus:border-[#4F46E5]"
          />
          <button
            type="submit"
            disabled={isSearching || query.trim().length < 2}
            className="rounded-xl bg-[#4F46E5] px-3 py-2 text-sm font-semibold text-white transition hover:bg-[#4338ca] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSearching ? "..." : "Search"}
          </button>
        </form>
      ) : null}

      {searchError ? <p className="mb-3 rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-300">{searchError}</p> : null}
      {results ? (
        <p className="mb-3 text-xs text-[#71717a]">
          {results.length} result{results.length === 1 ? "" : "s"} for &ldquo;{query.trim()}&rdquo;{" "}
          <button type="button" onClick={clearSearch} className="text-[#F59E0B] underline underline-offset-2">
            Show admins
          </button>
        </p>
      ) : null}

      <div className="space-y-3">
        {visibleUsers.length === 0 ? (
          <p className="text-sm text-[#71717a]">{results ? "No users matched." : "No admin users yet."}</p>
        ) : null}
        {visibleUsers.map((user) => {
          const isAdmin = user.roles?.includes("admin") ?? false;
          return (
            <div key={userId(user)} className="rounded-2xl border border-white/10 bg-[#0f172a]/50 p-4">
              <p className="font-medium text-[#e4e4e7]">{user.name ?? user.email ?? "Unnamed user"}</p>
              <p className="mt-1 text-sm text-[#a1a1aa]">{user.email ?? "No email"}</p>
              <div className="mt-3 flex gap-3">
                {isAdmin ? (
                  <button
                    type="button"
                    onClick={() => void onRevoke(user)}
                    className="rounded-xl border border-red-400/30 px-4 py-2 text-sm font-medium text-red-300 transition hover:bg-red-500/10"
                  >
                    Revoke admin
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => void onGrant(user)}
                    className="rounded-xl bg-[#4F46E5] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#4338ca]"
                  >
                    Grant admin
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
