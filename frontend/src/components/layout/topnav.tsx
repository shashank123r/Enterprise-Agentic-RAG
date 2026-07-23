import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  Menu,
  Moon,
  Sun,
  Bell,
  Search,
  LogOut,
  User,
  ChevronDown,
} from "lucide-react";
import { cn } from "../../lib/utils";
import { useAuthStore, useThemeStore, useLayoutStore } from "../../store";
import { authService } from "../../services/auth.service";
import { Avatar, AvatarFallback, AvatarImage } from "../ui/avatar";
import { Button } from "../ui/button";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";

export function TopNav() {
  const navigate = useNavigate();
  const { user, logout: clearAuth } = useAuthStore();
  const { mode, toggleMode, sidebarCollapsed } = useThemeStore();
  const { pageTitle, breadcrumbs, setMobileMenuOpen } = useLayoutStore();

  // Handle keyboard shortcut for search (⌘K / Ctrl+K)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        navigate("/retrieval");
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  const handleLogout = async () => {
    try {
      await authService.logout();
    } catch {
      // Ignore errors during logout
    }
    clearAuth();
    navigate("/login");
  };

  const userInitials = user?.name
    ?.split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2) ?? "U";

  return (
    <header
      className={cn(
        "sticky top-0 z-30 flex h-14 items-center gap-4 border-b border-surface-200 bg-white/80 backdrop-blur-md px-4 transition-all duration-300 dark:border-surface-700 dark:bg-surface-900/80",
        sidebarCollapsed ? "ml-16" : "ml-60",
      )}
    >
      {/* Mobile menu toggle */}
      <Button
        variant="ghost"
        size="icon"
        className="lg:hidden"
        onClick={() => setMobileMenuOpen(true)}
      >
        <Menu className="size-4" />
      </Button>

      {/* Breadcrumbs */}
      <div className="flex items-center gap-2 min-w-0">
        {breadcrumbs.length > 0 ? (
          breadcrumbs.map((crumb, index) => (
            <span key={index} className="flex items-center gap-2 text-sm">
              {index > 0 && (
                <span className="text-surface-300 dark:text-surface-600">
                  /
                </span>
              )}
              {crumb.href ? (
                <button
                  onClick={() => navigate(crumb.href!)}
                  className="text-surface-500 hover:text-surface-900 dark:text-surface-400 dark:hover:text-surface-200 transition-colors"
                >
                  {crumb.label}
                </button>
              ) : (
                <span className="text-surface-900 dark:text-surface-100 font-medium">
                  {crumb.label}
                </span>
              )}
            </span>
          ))
        ) : (
          <h1 className="text-sm font-semibold text-surface-900 dark:text-surface-100">
            {pageTitle || "Dashboard"}
          </h1>
        )}
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Search */}
      <button
        className="hidden sm:flex items-center gap-2 rounded-lg border border-surface-200 bg-surface-50 px-3 py-1.5 text-xs text-surface-400 hover:border-surface-300 transition-colors dark:border-surface-600 dark:bg-surface-800 dark:text-surface-500 dark:hover:border-surface-500"
        onClick={() => navigate("/retrieval")}
        aria-label="Search documents (⌘K)"
      >
        <Search className="size-3.5" />
        <span>Search documents...</span>
        <kbd className="ml-4 rounded border border-surface-200 bg-white px-1.5 py-0.5 text-[10px] font-medium dark:border-surface-600 dark:bg-surface-700">
          ⌘K
        </kbd>
      </button>

      {/* Theme toggle */}
      <Button variant="ghost" size="icon" onClick={toggleMode}>
        {mode === "dark" ? (
          <Sun className="size-4" />
        ) : (
          <Moon className="size-4" />
        )}
      </Button>

      {/* Notifications */}
      <Button variant="ghost" size="icon" className="relative" aria-label="Notifications">
        <Bell className="size-4" />
      </Button>

      {/* User menu */}
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <button className="flex items-center gap-2 rounded-lg p-1.5 hover:bg-surface-100 dark:hover:bg-surface-700 transition-colors">
            <Avatar className="size-7">
              <AvatarImage src={user?.avatar_url} />
              <AvatarFallback>{userInitials}</AvatarFallback>
            </Avatar>
            <span className="hidden md:block text-sm font-medium text-surface-700 dark:text-surface-300">
              {user?.name ?? "User"}
            </span>
            <ChevronDown className="hidden md:block size-3.5 text-surface-400" />
          </button>
        </DropdownMenu.Trigger>

        <DropdownMenu.Portal>
          <DropdownMenu.Content
            className="z-50 min-w-48 rounded-xl border border-surface-200 bg-white p-1.5 shadow-dropdown data-[side=bottom]:animate-slide-up dark:border-surface-700 dark:bg-surface-800"
            sideOffset={8}
            align="end"
          >
            <DropdownMenu.Item
              className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-surface-700 hover:bg-surface-100 cursor-pointer outline-none dark:text-surface-300 dark:hover:bg-surface-700"
              onClick={() => navigate("/profile")}
            >
              <User className="size-4" />
              Profile
            </DropdownMenu.Item>

            <DropdownMenu.Separator className="my-1 h-px bg-surface-200 dark:bg-surface-700" />

            <DropdownMenu.Item
              className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-surface-700 hover:bg-surface-100 cursor-pointer outline-none dark:text-surface-300 dark:hover:bg-surface-700"
              onClick={handleLogout}
            >
              <LogOut className="size-4" />
              Log out
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
    </header>
  );
}
