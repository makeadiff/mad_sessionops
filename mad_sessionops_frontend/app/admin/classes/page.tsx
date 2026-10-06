"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAppSelector } from "@/lib/redux";
import { selectUser, selectIsInitialized } from "@/lib/redux/features/auth/authSlice";
import { ClassCatalogPage } from "@/components/admin/ClassCatalogPage";

const ADMIN_ROLES = ["Function Lead", "Project Associate", "Project Lead"];

function isAdminRole(roleStr: string | undefined): boolean {
  if (!roleStr) return false;
  const roles = roleStr.split(",").map((r) => r.trim());
  return ADMIN_ROLES.some((ar) => roles.includes(ar));
}

export default function AdminClassesRoute() {
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

  return <ClassCatalogPage />;
}
