import { create } from "zustand";
import { persist } from "zustand/middleware";

type ThemeMode = "dark" | "light";

interface ThemeStore {
  mode: ThemeMode;
  sidebarCollapsed: boolean;
  setMode: (mode: ThemeMode) => void;
  toggleMode: () => void;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
}

function applyTheme(mode: ThemeMode) {
  document.documentElement.classList.remove("dark", "light");
  document.documentElement.classList.add(mode);
}

export const useThemeStore = create<ThemeStore>()(
  persist(
    (set, get) => ({
      mode: "dark",
      sidebarCollapsed: false,

      setMode: (mode) => {
        applyTheme(mode);
        set({ mode });
      },

      toggleMode: () => {
        const next = get().mode === "dark" ? "light" : "dark";
        applyTheme(next);
        set({ mode: next });
      },

      toggleSidebar: () => {
        set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed }));
      },

      setSidebarCollapsed: (sidebarCollapsed) => {
        set({ sidebarCollapsed });
      },
    }),
    {
      name: "rag_theme_store",
      onRehydrateStorage: () => (state) => {
        if (state?.mode) {
          applyTheme(state.mode);
        } else {
          applyTheme("dark");
        }
      },
    },
  ),
);
