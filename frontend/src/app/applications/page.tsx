"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { ApplicationsClient } from "@/components/applications/ApplicationsClient";
import { useAuth } from "@/contexts/AuthContext";

/**
 * Recruiter applications + pipeline segment (R17.2/R17.3). Requires an
 * authenticated user; the active company is resolved from the tenant context
 * and the backend enforces the review/advance permissions per request.
 */
function ApplicationsPageContent() {
  const router = useRouter();
  const { user, isLoading } = useAuth();

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace("/sign-in?redirect=/applications");
    }
  }, [isLoading, router, user]);

  if (!user) {
    return null;
  }

  return <ApplicationsClient />;
}

export default function ApplicationsPage() {
  return <ApplicationsPageContent />;
}
