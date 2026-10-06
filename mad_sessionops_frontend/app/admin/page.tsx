"use client";

import { Suspense, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAppSelector } from "@/lib/redux";
import { selectUser, selectIsInitialized } from "@/lib/redux/features/auth/authSlice";
import { AdminPage } from "@/components/admin/AdminPage";

const ADMIN_ROLES = ["Function Lead", "Project Associate", "Project Lead"];

function isAdminRole(roleStr: string | undefined): boolean {
  if (!roleStr) return false;
  const roles = roleStr.split(",").map((r) => r.trim());
  return ADMIN_ROLES.some((ar) => roles.includes(ar));
}

export default function AdminRoute() {
  const router = useRouter();
  const user = useAppSelector(selectUser);
  const isInitialized = useAppSelector(selectIsInitialized);

  useEffect(() => {
    if (isInitialized && !isAdminRole(user?.role)) {
      router.replace("/schools");
    }
  }, [isInitialized, user, router]);

  if (!isInitialized || !isAdminRole(user?.role)) {
    return null;
  }

  // AdminPage reads ?tab= (useSearchParams), which needs a Suspense boundary.
  return (
    <Suspense fallback={null}>
      <AdminPage />
    </Suspense>
  );
}
