import { Outlet } from "react-router-dom";
import { Sidebar } from "./sidebar";
import { TopNav } from "./topnav";
import { ToastContainer } from "../ui/toast";
import { useThemeStore } from "../../store";
import { cn } from "../../lib/utils";

export function AppShell() {
  const { sidebarCollapsed } = useThemeStore();

  return (
    <div className="min-h-screen bg-surface-50 dark:bg-surface-950">
      {/* Sidebar */}
      <Sidebar />

      {/* Main area */}
      <div
        className={cn(
          "flex flex-col min-h-screen transition-all duration-300",
          sidebarCollapsed ? "ml-16" : "ml-60",
        )}
      >
        {/* Top navigation */}
        <TopNav />

        {/* Page content */}
        <main className="flex-1 p-4 lg:p-6">
          <Outlet />
        </main>

        {/* Footer */}
        <footer
          className={cn(
            "border-t border-surface-200 px-6 py-3 text-xs text-surface-400 dark:border-surface-700 dark:text-surface-500",
          )}
        >
          <div className="flex items-center justify-between">
            <span>&copy; {new Date().getFullYear()} RAG Platform. All rights reserved.</span>
            <span className="hidden sm:block">Enterprise Hybrid RAG v1.0</span>
          </div>
        </footer>
      </div>

      {/* Toast notifications */}
      <ToastContainer />
    </div>
  );
}
