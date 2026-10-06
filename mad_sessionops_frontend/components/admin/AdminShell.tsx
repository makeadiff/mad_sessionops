"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import {
  Activity,
  ArrowLeft,
  CalendarRange,
  Database,
  Layers,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";

const SIDEBAR_W = 200;
const SIDEBAR_BG = "#FFFFFF";
const SIDEBAR_BORDER = "#E2E8F0";
const ACTIVE_BG = "#E0F2FE";
const ACTIVE_COLOR = "#0284C7";
const ACTIVE_TEXT = "#0C4A6E";
const HOVER_BG = "#F5F3FF";
const TEXT_MUTED = "#94A3B8";
const TEXT_DEFAULT = "#64748B";

export type AdminTabKey = "data-sync" | "realtime-events";
export type AdminNavKey = AdminTabKey | "classes" | "academic-years" | "progression";

interface NavItem<K extends string> {
  key: K;
  label: string;
  icon: LucideIcon;
  href: string;
}

export const ADMIN_TABS: NavItem<AdminTabKey>[] = [
  { key: "data-sync", label: "Data Sync", icon: Database, href: "/admin" },
  {
    key: "realtime-events",
    label: "Realtime Events",
    icon: Activity,
    href: "/admin?tab=realtime-events",
  },
];

const SETUP_LINKS: NavItem<AdminNavKey>[] = [
  { key: "classes", label: "Classes", icon: Layers, href: "/admin/classes" },
  {
    key: "academic-years",
    label: "Academic Years",
    icon: CalendarRange,
    href: "/admin/academic-years",
  },
  { key: "progression", label: "Year Progression", icon: TrendingUp, href: "/admin/progression" },
];

function NavRow({ item, active }: { item: NavItem<string>; active: boolean }) {
  const Icon = item.icon;
  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        gap: 1.25,
        px: 1.5,
        py: 0.875,
        mx: 1,
        borderRadius: "7px",
        cursor: "pointer",
        position: "relative",
        transition: "background 0.15s ease",
        bgcolor: active ? ACTIVE_BG : "transparent",
        ...(active && {
          "&::before": {
            content: '""',
            position: "absolute",
            left: -8,
            top: "25%",
            bottom: "25%",
            width: "3px",
            borderRadius: "0 3px 3px 0",
            bgcolor: "#E53935",
          },
        }),
        ...(!active && { "&:hover": { bgcolor: HOVER_BG } }),
      }}
    >
      <Icon
        size={16}
        strokeWidth={active ? 2 : 1.75}
        color={active ? ACTIVE_COLOR : TEXT_MUTED}
        style={{ flexShrink: 0 }}
      />
      <Typography
        sx={{
          fontSize: "13px",
          fontWeight: active ? 600 : 400,
          color: active ? ACTIVE_TEXT : TEXT_DEFAULT,
        }}
      >
        {item.label}
      </Typography>
    </Box>
  );
}

function GroupLabel({ children, first }: { children: ReactNode; first?: boolean }) {
  return (
    <Typography
      sx={{
        fontSize: "10px",
        fontWeight: 600,
        color: TEXT_MUTED,
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        px: 2.5,
        mt: first ? 0 : 2.5,
        mb: 0.75,
      }}
    >
      {children}
    </Typography>
  );
}

/**
 * The admin workspace frame: sidebar + title bar. Every admin screen (the
 * Data Sync / Realtime tabs and the Setup pages) renders inside it so moving
 * between them never drops the navigation.
 *
 * `onSelectTab` lets the /admin page switch its tabs in place; elsewhere the
 * tab rows are plain links back to /admin.
 */
export function AdminShell({
  active,
  title,
  actions,
  onSelectTab,
  children,
}: {
  active: AdminNavKey;
  title: ReactNode;
  actions?: ReactNode;
  onSelectTab?: (key: AdminTabKey) => void;
  children: ReactNode;
}) {
  return (
    <Box sx={{ display: "flex", height: "100vh", overflow: "hidden", bgcolor: "#F8FAFC" }}>
      <Box
        component="nav"
        aria-label="Admin"
        sx={{
          width: SIDEBAR_W,
          flexShrink: 0,
          borderRight: `1px solid ${SIDEBAR_BORDER}`,
          display: "flex",
          flexDirection: "column",
          bgcolor: SIDEBAR_BG,
          height: "100vh",
        }}
      >
        <Box
          sx={{
            px: 2,
            pt: 2,
            pb: 1.25,
            borderBottom: `1px solid ${SIDEBAR_BORDER}`,
            flexShrink: 0,
          }}
        >
          <Link href="/schools" style={{ textDecoration: "none" }}>
            <Box
              sx={{
                display: "inline-flex",
                alignItems: "center",
                gap: 0.75,
                color: TEXT_MUTED,
                fontSize: "12px",
                "&:hover": { color: "#334155" },
                transition: "color 0.15s ease",
              }}
            >
              <ArrowLeft size={13} strokeWidth={2} />
              <Typography sx={{ fontSize: "12px", color: "inherit" }}>Schools</Typography>
            </Box>
          </Link>
          <Typography sx={{ fontSize: "13px", fontWeight: 700, color: "#0F172A", mt: 1 }}>
            Admin
          </Typography>
        </Box>

        <Box sx={{ flex: 1, overflowY: "auto", py: 1.5 }}>
          <GroupLabel first>Sections</GroupLabel>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 0.25 }}>
            {ADMIN_TABS.map((tab) =>
              onSelectTab ? (
                <Box key={tab.key} onClick={() => onSelectTab(tab.key)}>
                  <NavRow item={tab} active={active === tab.key} />
                </Box>
              ) : (
                <Link key={tab.key} href={tab.href} style={{ textDecoration: "none" }}>
                  <NavRow item={tab} active={active === tab.key} />
                </Link>
              )
            )}
          </Box>

          <GroupLabel>Setup</GroupLabel>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 0.25 }}>
            {SETUP_LINKS.map((item) => (
              <Link
                key={item.key}
                href={item.href}
                style={{ textDecoration: "none" }}
                aria-current={active === item.key ? "page" : undefined}
              >
                <NavRow item={item} active={active === item.key} />
              </Link>
            ))}
          </Box>
        </Box>
      </Box>

      <Box
        component="main"
        sx={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, overflowY: "auto" }}
      >
        <Box
          sx={{
            px: 3,
            py: 2,
            borderBottom: `1px solid ${SIDEBAR_BORDER}`,
            bgcolor: SIDEBAR_BG,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 2,
            flexShrink: 0,
          }}
        >
          <Typography component="h1" sx={{ fontSize: "16px", fontWeight: 600, color: "#0F172A" }}>
            {title}
          </Typography>
          {actions}
        </Box>
        {children}
      </Box>
    </Box>
  );
}

/** Content area for Setup pages inside the shell — uses the full width, like the
 * Data Sync / Realtime tabs. */
export function AdminContent({ children }: { children: ReactNode }) {
  return <Box sx={{ px: 3, pt: 3, pb: 8, width: "100%", boxSizing: "border-box" }}>{children}</Box>;
}
