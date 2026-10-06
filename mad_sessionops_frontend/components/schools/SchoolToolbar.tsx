"use client";

import { useState, useRef } from "react";
import Box from "@mui/material/Box";
import InputAdornment from "@mui/material/InputAdornment";
import OutlinedInput from "@mui/material/OutlinedInput";
import IconButton from "@mui/material/IconButton";
import Popover from "@mui/material/Popover";
import MenuItem from "@mui/material/MenuItem";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import { Search, X, ArrowUpDown, Check } from "lucide-react";
import { colors } from "@/config/design-tokens";
import { describeSortOption, type SortOption } from "@/lib/api/services/schools.service";
import { ExportButton, type ExportOption } from "@/components/ui/ExportButton";

// Curated quick presets for the dropdown, with their original labels
// preserved. Any other column/direction is reachable by clicking a table
// header instead, and falls back to a generic description (see below).
const SORT_PRESETS: Partial<Record<SortOption, string>> = {
  updated_desc: "Recently updated",
  name_asc: "Name (A–Z)",
  city_asc: "City (A–Z)",
  children_desc: "Most children",
};
const PRESET_ORDER: SortOption[] = ["updated_desc", "name_asc", "city_asc", "children_desc"];

function labelFor(sort: SortOption): string {
  return SORT_PRESETS[sort] ?? describeSortOption(sort);
}

interface SchoolToolbarProps {
  search: string;
  onSearchChange: (v: string) => void;
  sort: SortOption;
  onSortChange: (v: SortOption) => void;
  /** M9 cross-school CSV exports; the Export control is hidden when omitted. */
  exportOptions?: ExportOption[];
}

export function SchoolToolbar({
  search,
  onSearchChange,
  sort,
  onSortChange,
  exportOptions,
}: SchoolToolbarProps) {
  const [anchorEl, setAnchorEl] = useState<HTMLButtonElement | null>(null);
  const sortBtnRef = useRef<HTMLButtonElement>(null);

  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
      {/* Search */}
      <OutlinedInput
        value={search}
        onChange={(e) => onSearchChange(e.target.value)}
        placeholder="Search by school name, city, or organizer…"
        size="small"
        sx={{
          flex: 1,
          minWidth: 240,
          bgcolor: colors.white,
          fontSize: "14px",
          "& .MuiOutlinedInput-notchedOutline": { borderColor: colors.gray[200] },
          "&:hover .MuiOutlinedInput-notchedOutline": { borderColor: colors.gray[400] },
        }}
        startAdornment={
          <InputAdornment position="start">
            <Search size={16} color={colors.gray[500]} strokeWidth={1.5} />
          </InputAdornment>
        }
        endAdornment={
          search ? (
            <InputAdornment position="end">
              <IconButton size="small" onClick={() => onSearchChange("")} edge="end">
                <X size={14} color={colors.gray[500]} />
              </IconButton>
            </InputAdornment>
          ) : null
        }
      />

      {/* Sort */}
      <Button
        ref={sortBtnRef}
        variant="outlined"
        size="small"
        startIcon={<ArrowUpDown size={14} strokeWidth={1.5} />}
        onClick={(e) => setAnchorEl(e.currentTarget)}
        sx={{
          textTransform: "none",
          fontSize: "13px",
          borderColor: colors.gray[200],
          color: colors.gray[700],
          bgcolor: colors.white,
          whiteSpace: "nowrap",
          "&:hover": { borderColor: colors.gray[400], bgcolor: colors.gray[50] },
        }}
      >
        Sort: {labelFor(sort)}
      </Button>

      <Popover
        open={Boolean(anchorEl)}
        anchorEl={anchorEl}
        onClose={() => setAnchorEl(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
        PaperProps={{
          sx: {
            mt: 0.5,
            borderRadius: "8px",
            border: `1px solid ${colors.gray[200]}`,
            boxShadow: "0 4px 12px rgba(15,23,42,0.08)",
            minWidth: 200,
          },
        }}
      >
        {PRESET_ORDER.map((value) => (
          <MenuItem
            key={value}
            selected={sort === value}
            onClick={() => {
              onSortChange(value);
              setAnchorEl(null);
            }}
            sx={{
              fontSize: "14px",
              color: colors.gray[700],
              display: "flex",
              justifyContent: "space-between",
              gap: 2,
              py: 1,
            }}
          >
            <Typography sx={{ fontSize: "14px" }}>{labelFor(value)}</Typography>
            {sort === value && <Check size={14} color={colors.gray[700]} />}
          </MenuItem>
        ))}
      </Popover>

      {exportOptions && exportOptions.length > 0 && (
        <ExportButton label="Export" options={exportOptions} />
      )}
    </Box>
  );
}
