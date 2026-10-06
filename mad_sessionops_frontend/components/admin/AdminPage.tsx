"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { AdminShell, ADMIN_TABS, type AdminTabKey } from "./AdminShell";
import { DataSyncTab } from "./DataSyncTab";
import { RealtimeEventsTab } from "./RealtimeEventsTab";

function tabFrom(value: string | null | undefined): AdminTabKey {
  return ADMIN_TABS.find((t) => t.key === value)?.key ?? "data-sync";
}

export function AdminPage() {
  // Setup pages link back with ?tab=…; after that, tabs switch in place.
  const searchParams = useSearchParams();
  const [activeTab, setActiveTab] = useState<AdminTabKey>(() => tabFrom(searchParams?.get("tab")));

  return (
    <AdminShell
      active={activeTab}
      title={ADMIN_TABS.find((t) => t.key === activeTab)?.label}
      onSelectTab={setActiveTab}
    >
      {activeTab === "data-sync" && <DataSyncTab />}
      {activeTab === "realtime-events" && <RealtimeEventsTab />}
    </AdminShell>
  );
}
