"use client";

import { useCallback, useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Switch from "@mui/material/Switch";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { ArrowRight, Plus } from "lucide-react";
import {
  fetchAdminClasses,
  updateClass,
  type AdminClass,
} from "@/lib/api/services/catalog.service";
import { showApiError, showSuccess } from "@/lib/toast/toast";
import { AdminContent, AdminShell } from "./AdminShell";
import {
  BODY,
  HeadRow,
  LoadingRows,
  MUTED,
  Notice,
  PageIntro,
  Pill,
  TableShell,
  bodyRowSx,
  cellSx,
  linkButtonSx,
  nameCellSx,
  primaryButtonSx,
  secondaryButtonSx,
  EmptyRow,
} from "./adminUi";
import { ClassEditDrawer } from "./ClassEditDrawer";

const COLUMNS = [
  "Class",
  "Code",
  "Next class",
  "Open for enrolment",
  { label: "Used by", align: "right" as const },
  "Status",
  "",
];

/**
 * F-M10-1 Admin → Classes. Catalog only: order, next class, open for enrolment.
 * Year progression uses "Next class" to decide where each class's children go.
 */
export function ClassCatalogPage() {
  const [classes, setClasses] = useState<AdminClass[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<AdminClass | null>(null);
  const [togglingId, setTogglingId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      setClasses(await fetchAdminClasses());
    } catch (error) {
      setLoadError(true);
      showApiError(error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const openDrawer = (cls: AdminClass | null) => {
    setEditing(cls);
    setDrawerOpen(true);
  };

  const toggleEnrolment = async (cls: AdminClass, value: boolean) => {
    setTogglingId(cls.classId);
    try {
      await updateClass(cls.classId, { openForEnrolment: value });
      showSuccess(`${cls.className} is now ${value ? "open" : "closed"} for new enrolment.`);
      await load();
    } catch (error) {
      showApiError(error);
    } finally {
      setTogglingId(null);
    }
  };

  return (
    <AdminShell active="classes" title="Classes">
      <AdminContent>
        <PageIntro
          description={
            <>
              The class catalog used by every school. <strong>Next class</strong> is where year
              progression moves each class&apos;s children; a class with no next class keeps its
              children. Classes are listed in next-class order. Closing a class stops new enrolments
              into it.
            </>
          }
          actions={
            <Button
              variant="contained"
              size="small"
              startIcon={<Plus size={14} />}
              onClick={() => openDrawer(null)}
              sx={primaryButtonSx}
            >
              Add class
            </Button>
          }
        />

        {loadError && !loading ? (
          <Notice
            tone="error"
            action={
              <Button size="small" variant="outlined" onClick={load} sx={secondaryButtonSx}>
                Retry
              </Button>
            }
          >
            Could not load classes.
          </Notice>
        ) : (
          <TableShell>
            <Table size="small">
              <TableHead>
                <HeadRow columns={COLUMNS} />
              </TableHead>
              <TableBody>
                {loading ? (
                  <LoadingRows cols={COLUMNS.length} />
                ) : classes.length === 0 ? (
                  <EmptyRow cols={COLUMNS.length} message="No classes yet. Add the first one." />
                ) : (
                  classes.map((cls) => (
                    <TableRow
                      key={cls.classId}
                      data-testid={`class-row-${cls.classCode}`}
                      sx={{ ...bodyRowSx, opacity: cls.isActive ? 1 : 0.6 }}
                    >
                      <TableCell sx={nameCellSx}>{cls.className}</TableCell>
                      <TableCell sx={cellSx}>{cls.classCode}</TableCell>
                      <TableCell sx={cellSx}>
                        {cls.nextClassName ? (
                          <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.75 }}>
                            <ArrowRight size={12} color={MUTED} />
                            <Typography component="span" sx={{ fontSize: "13px", color: BODY }}>
                              {cls.nextClassName}
                            </Typography>
                          </Box>
                        ) : (
                          <Typography component="span" sx={{ fontSize: "12px", color: MUTED }}>
                            None — children stay
                          </Typography>
                        )}
                      </TableCell>
                      <TableCell sx={{ ...cellSx, py: 0.5 }}>
                        <Switch
                          size="small"
                          checked={cls.openForEnrolment}
                          disabled={togglingId === cls.classId || !cls.isActive}
                          onChange={(_, v) => toggleEnrolment(cls, v)}
                          slotProps={{
                            input: { "aria-label": `Open ${cls.className} for enrolment` },
                          }}
                        />
                      </TableCell>
                      <TableCell sx={cellSx} align="right">
                        {cls.inUseCount} {cls.inUseCount === 1 ? "school" : "schools"}
                      </TableCell>
                      <TableCell sx={cellSx}>
                        <Pill
                          label={cls.isActive ? "Active" : "Inactive"}
                          tone={cls.isActive ? "success" : "neutral"}
                        />
                      </TableCell>
                      <TableCell sx={cellSx} align="right">
                        <Button size="small" onClick={() => openDrawer(cls)} sx={linkButtonSx}>
                          Edit
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </TableShell>
        )}
      </AdminContent>

      <ClassEditDrawer
        open={drawerOpen}
        editing={editing}
        classes={classes}
        onClose={() => setDrawerOpen(false)}
        onSaved={(saved) => {
          setDrawerOpen(false);
          showSuccess(`${saved.className} saved.`);
          load();
        }}
      />
    </AdminShell>
  );
}

export default ClassCatalogPage;
