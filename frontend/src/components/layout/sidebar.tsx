import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  FileText,
  Database,
  BarChart3,
  MessageSquare,
  Search,
  Settings,
  HardDrive,
  ChevronLeft,
  ChevronRight,
  Sparkles,
} from "lucide-react";
import { cn } from "../../lib/utils";
import { useThemeStore } from "../../store";
import { Separator } from "../ui/separator";

interface NavItem {
  label: string;
  path: string;
  icon: React.ElementType;
  badge?: string;
}

const mainNavItems: NavItem[] = [
  { label: "Dashboard", path: "/dashboard", icon: LayoutDashboard },
  { label: "Documents", path: "/documents", icon: FileText },
  { label: "Collections", path: "/collections", icon: Database },
  { label: "Indexing", path: "/indexing", icon: HardDrive },
  { label: "Retrieval", path: "/retrieval", icon: Search },
  { label: "Chat", path: "/chat", icon: MessageSquare },
  { label: "Analytics", path: "/analytics", icon: BarChart3 },
];

const secondaryNavItems: NavItem[] = [
  { label: "Settings", path: "/settings", icon: Settings },
];

export function Sidebar() {
  const { sidebarCollapsed, toggleSidebar } = useThemeStore();

  return (
    <aside
      className={cn(
        "fixed left-0 top-0 z-40 flex h-screen flex-col border-r border-surface-200 bg-white transition-all duration-300 dark:border-surface-700 dark:bg-surface-800",
        sidebarCollapsed ? "w-16" : "w-60",
      )}
    >
      {/* Logo area */}
      <div
        className={cn(
          "flex h-14 items-center border-b border-surface-200 px-4 dark:border-surface-700",
          sidebarCollapsed ? "justify-center" : "gap-3",
        )}
      >
        <div className="flex size-8 items-center justify-center rounded-lg bg-brand-600 text-white">
          <Sparkles className="size-4" />
        </div>
        {!sidebarCollapsed && (
          <span className="text-sm font-semibold text-surface-900 dark:text-surface-50">
            RAG Platform
          </span>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto p-2">
        <div className="flex flex-col gap-0.5">
          {mainNavItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200",
                  isActive
                    ? "bg-brand-50 text-brand-700 dark:bg-brand-950 dark:text-brand-300"
                    : "text-surface-600 hover:bg-surface-100 hover:text-surface-900 dark:text-surface-400 dark:hover:bg-surface-700 dark:hover:text-surface-200",
                  sidebarCollapsed && "justify-center px-2",
                )
              }
              title={sidebarCollapsed ? item.label : undefined}
            >
              <item.icon className="size-4 shrink-0" />
              {!sidebarCollapsed && (
                <>
                  <span className="flex-1 truncate">{item.label}</span>
                  {item.badge && (
                    <span className="rounded-full bg-brand-100 px-2 py-0.5 text-[10px] font-medium text-brand-700 dark:bg-brand-900 dark:text-brand-300">
                      {item.badge}
                    </span>
                  )}
                </>
              )}
            </NavLink>
          ))}
        </div>

        <Separator className="my-3" />

        <div className="flex flex-col gap-0.5">
          {secondaryNavItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200",
                  isActive
                    ? "bg-brand-50 text-brand-700 dark:bg-brand-950 dark:text-brand-300"
                    : "text-surface-600 hover:bg-surface-100 hover:text-surface-900 dark:text-surface-400 dark:hover:bg-surface-700 dark:hover:text-surface-200",
                  sidebarCollapsed && "justify-center px-2",
                )
              }
              title={sidebarCollapsed ? item.label : undefined}
            >
              <item.icon className="size-4 shrink-0" />
              {!sidebarCollapsed && (
                <span className="flex-1 truncate">{item.label}</span>
              )}
            </NavLink>
          ))}
        </div>
      </nav>

      {/* Collapse toggle */}
      <div className="border-t border-surface-200 p-2 dark:border-surface-700">
        <button
          onClick={toggleSidebar}
          className="flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm text-surface-500 hover:bg-surface-100 hover:text-surface-700 transition-colors dark:text-surface-400 dark:hover:bg-surface-700 dark:hover:text-surface-200"
          title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {sidebarCollapsed ? (
            <ChevronRight className="size-4" />
          ) : (
            <>
              <ChevronLeft className="size-4" />
              <span>Collapse</span>
            </>
          )}
        </button>
      </div>
    </aside>
  );
}
