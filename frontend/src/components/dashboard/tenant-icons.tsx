export type TenantIconName =
  | "home"
  | "dashboard"
  | "setup"
  | "users"
  | "profile"
  | "privacy"
  | "employees"
  | "document-types"
  | "reports"
  | "requests"
  | "leave"
  | "manager"
  | "leave-approvals"
  | "leave-admin"
  | "profile-change-requests"
  | "hr-requests"
  | "announcements"
  | "announcement-management"
  | "notifications"
  | "organization"
  | "audit"
  | "privacy-management"
  | "menu"
  | "close"
  | "chevron-down"
  | "logout";

const ICON_PATHS = {
  home: ["m3.5 10.5 8.5-7.5 8.5 7.5", "M5.5 9v11h13V9", "M9 20v-6h6v6"],
  dashboard: ["M4 4h6v6H4z", "M14 4h6v6h-6z", "M4 14h6v6H4z", "M14 14h6v6h-6z"],
  setup: ["M9 6h11M9 12h11M9 18h11", "m4 6 1.5 1.5L7.5 5m-3.5 7 1.5 1.5L7.5 11m-3.5 7 1.5 1.5L7.5 17"],
  users: ["M15 20v-1.5a4.5 4.5 0 0 0-9 0V20", "M10.5 12a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z", "M17 7a2.5 2.5 0 0 1 0 5", "M18 13.5a3.5 3.5 0 0 1 3 3.5v1"],
  profile: ["M5 3.5h14a1.5 1.5 0 0 1 1.5 1.5v14a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 19V5A1.5 1.5 0 0 1 5 3.5Z", "M14 16.5a4 4 0 0 0-8 0", "M10 12a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z"],
  privacy: ["M12 3 19 6v5c0 4.7-2.8 8-7 10-4.2-2-7-5.3-7-10V6l7-3Z", "M9.5 12 11 13.5l3.5-4"],
  employees: ["M3.5 20v-2a4 4 0 0 1 4-4h2a4 4 0 0 1 4 4v2", "M8.5 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z", "M15.5 12a2.5 2.5 0 1 0 0-5", "M15.5 14.5h1a4 4 0 0 1 4 4V20"],
  "document-types": ["M6 3h8l4 4v14H6z", "M14 3v5h4", "M9 12h6M9 16h6"],
  reports: ["M4 20V10h4v10M10 20V4h4v16M16 20v-7h4v7", "M3 20.5h18"],
  requests: ["M4 5h16v11H8l-4 4V5Z", "M8 9h8M8 12.5h5"],
  leave: ["M5 5h14a2 2 0 0 1 2 2v12H3V7a2 2 0 0 1 2-2Z", "M7 3v4m10-4v4M3 9h18", "m8 14 2 2 5-5"],
  manager: ["M13.5 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z", "M6.5 20v-1.5a7 7 0 0 1 14 0V20", "m5.5 5.5-1 1-1-1m18 0-1 1-1-1"],
  "leave-approvals": ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "m8 12 2.5 2.5L16 9"],
  "leave-admin": ["M5 5h14a2 2 0 0 1 2 2v12H3V7a2 2 0 0 1 2-2Z", "M7 3v4m10-4v4M3 9h18", "M7 13h4m4 0h2M7 17h2m4 0h4"],
  "profile-change-requests": ["M14 5H6a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-8", "M9 15h2l8.5-8.5-2-2L9 13v2Z", "M8 10a2 2 0 1 0 0-4"],
  "hr-requests": ["M4 8h16v11H4z", "M9 8V5h6v3", "M4 12h16", "M10 15h4"],
  announcements: ["M4 13V9l11-4v12L4 13Z", "M15 9a4 4 0 0 1 0 4", "m6 13 1 6h3l-1-7"],
  "announcement-management": ["M3.5 13V9l10-4v12l-10-4Z", "M13.5 9a4 4 0 0 1 0 4", "m15 18 1.5 1.5L20 16"],
  notifications: ["M18 9a6 6 0 0 0-12 0c0 7-3 7-3 8h18c0-1-3-1-3-8", "M10 21h4"],
  organization: ["M12 3v5M5 13V8h14v5", "M3 13h4v5H3zM10 13h4v5h-4zM17 13h4v5h-4z"],
  audit: ["M8 4h8M9 3h6v3H9z", "M6 5H4v16h16V5h-2", "M8 11h8M8 15h5", "m15 17 4 4"],
  "privacy-management": ["M12 3 19 6v5c0 4.7-2.8 8-7 10-4.2-2-7-5.3-7-10V6l7-3Z", "M8.5 12h7M12 8.5v7"],
  menu: ["M4 7h16M4 12h16M4 17h16"],
  close: ["m6 6 12 12M18 6 6 18"],
  "chevron-down": ["m7 9 5 5 5-5"],
  logout: ["M10 5V3H4v18h6v-2", "M13 8l4 4-4 4M8 12h9"],
} as const satisfies Record<TenantIconName, readonly string[]>;

export function TenantIcon({
  name,
  className,
}: {
  name: TenantIconName;
  className?: string;
}) {
  return (
    <svg
      className={className}
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      focusable="false"
      aria-hidden="true"
    >
      {ICON_PATHS[name].map((path) => (
        <path d={path} key={path} />
      ))}
    </svg>
  );
}
