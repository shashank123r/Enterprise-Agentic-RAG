import { create } from "zustand";

interface Breadcrumb {
  label: string;
  href?: string;
}

interface LayoutStore {
  pageTitle: string;
  breadcrumbs: Breadcrumb[];
  mobileMenuOpen: boolean;
  setPageTitle: (title: string) => void;
  setBreadcrumbs: (breadcrumbs: Breadcrumb[]) => void;
  setMobileMenuOpen: (open: boolean) => void;
}

export const useLayoutStore = create<LayoutStore>()((set) => ({
  pageTitle: "",
  breadcrumbs: [],
  mobileMenuOpen: false,

  setPageTitle: (pageTitle) => set({ pageTitle }),
  setBreadcrumbs: (breadcrumbs) => set({ breadcrumbs }),
  setMobileMenuOpen: (mobileMenuOpen) => set({ mobileMenuOpen }),
}));
