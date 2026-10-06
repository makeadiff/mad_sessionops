"use client";

import { useState } from "react";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import FileDownloadOutlined from "@mui/icons-material/FileDownloadOutlined";
import type { ApiRejection } from "@/lib/api/client";
import { showError } from "@/lib/toast/toast";

export interface ExportOption {
  label: string;
  onExport: () => Promise<void>;
}

export interface ExportButtonProps {
  /** One option renders a plain button; several render a menu. */
  options: ExportOption[];
  label?: string;
  disabled?: boolean;
}

/**
 * M9 CSV export trigger. Shows a spinner and blocks repeat clicks while a
 * download is in flight; backend errors surface as a toast. Scope is enforced
 * server-side, so the button is not role-gated here.
 */
export function ExportButton({
  options,
  label = "Export CSV",
  disabled = false,
}: ExportButtonProps) {
  const [busy, setBusy] = useState(false);
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);

  const run = async (option: ExportOption) => {
    setAnchorEl(null);
    setBusy(true);
    try {
      await option.onExport();
    } catch (caught) {
      const error = caught as Partial<ApiRejection> | undefined;
      // Session expiry already redirects to login — no toast.
      if (error?.code !== "SESSION_EXPIRED") {
        // Show the backend text (e.g. "No active academic year is configured.")
        // rather than showApiError's generic per-code messages.
        showError(error?.message || "Export failed. Please try again.");
      }
    } finally {
      setBusy(false);
    }
  };

  const isMenu = options.length > 1;

  return (
    <>
      <Button
        variant="outlined"
        size="small"
        disabled={disabled || busy || options.length === 0}
        startIcon={busy ? <CircularProgress size={16} color="inherit" /> : <FileDownloadOutlined />}
        onClick={(e) => (isMenu ? setAnchorEl(e.currentTarget) : run(options[0]))}
        aria-haspopup={isMenu ? "menu" : undefined}
        aria-busy={busy}
      >
        {label}
      </Button>
      {isMenu && (
        <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={() => setAnchorEl(null)}>
          {options.map((option) => (
            <MenuItem key={option.label} onClick={() => run(option)}>
              {option.label}
            </MenuItem>
          ))}
        </Menu>
      )}
    </>
  );
}

export default ExportButton;
