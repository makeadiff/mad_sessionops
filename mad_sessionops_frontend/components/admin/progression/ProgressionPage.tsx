"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import { AdminContent, AdminShell } from "../AdminShell";
import { PageIntro, SegmentedTabs } from "../adminUi";
import { ProgressionWizard } from "./ProgressionWizard";
import { RunsTab } from "./RunsTab";

/** F-M10-9 Admin → Year Progression: New run (wizard) | Runs (history). */
export function ProgressionPage() {
  const [tab, setTab] = useState<"new" | "runs">("new");

  return (
    <AdminShell active="progression" title="Year Progression">
      <AdminContent>
        <PageIntro description="Move schools into the next academic year: children go up to their next class, sections are copied, and old timetables are archived. Each school moves on its own and can be undone until new-year data is added." />
        <Box sx={{ mb: 2 }}>
          <SegmentedTabs
            ariaLabel="Year progression"
            value={tab}
            onChange={setTab}
            options={[
              { value: "new", label: "New run" },
              { value: "runs", label: "Runs" },
            ]}
          />
        </Box>
        {tab === "new" ? <ProgressionWizard onOpenRuns={() => setTab("runs")} /> : <RunsTab />}
      </AdminContent>
    </AdminShell>
  );
}

export default ProgressionPage;
