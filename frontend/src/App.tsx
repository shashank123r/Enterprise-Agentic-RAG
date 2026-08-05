import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ErrorBoundary } from "./components/ui/error-boundary";
import { AppShell } from "./components/layout/app-shell";
import { ProtectedRoute } from "./components/layout/protected-route";

// Lazy-loaded pages
const LoginPage = lazy(() => import("./pages/login").then((m) => ({ default: m.LoginPage })));
const DashboardPage = lazy(() => import("./pages/dashboard").then((m) => ({ default: m.DashboardPage })));
const DocumentsPage = lazy(() => import("./pages/documents-page").then((m) => ({ default: m.DocumentsPage })));
const DocumentDetailPage = lazy(() => import("./pages/document-detail-page").then((m) => ({ default: m.DocumentDetailPage })));
const CollectionsPage = lazy(() => import("./pages/collections").then((m) => ({ default: m.CollectionsPage })));
const IndexingPage = lazy(() => import("./pages/indexing").then((m) => ({ default: m.IndexingPage })));
const RetrievalPage = lazy(() => import("./pages/retrieval").then((m) => ({ default: m.RetrievalPage })));
const ChatPage = lazy(() => import("./pages/chat").then((m) => ({ default: m.ChatPage })));
const AnalyticsPage = lazy(() => import("./pages/analytics").then((m) => ({ default: m.AnalyticsPage })));
const SettingsPage = lazy(() => import("./pages/settings").then((m) => ({ default: m.SettingsPage })));
const ProfilePage = lazy(() => import("./pages/profile").then((m) => ({ default: m.ProfilePage })));
const NotFoundPage = lazy(() => import("./pages/not-found").then((m) => ({ default: m.NotFoundPage })));

// Loading fallback
function PageLoader() {
  return (
    <div className="flex h-[calc(100vh-8rem)] items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <div className="size-8 animate-spin rounded-full border-2 border-brand-600 border-t-transparent" />
        <p className="text-sm text-surface-500 dark:text-surface-400">Loading...</p>
      </div>
    </div>
  );
}

// Lazy loading wrapper
function LazyPage({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<PageLoader />}>{children}</Suspense>;
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary>
        <BrowserRouter>
          <Routes>
          {/* Public routes */}
          <Route
            path="/login"
            element={
              <LazyPage>
                <LoginPage />
              </LazyPage>
            }
          />

          {/* Protected routes */}
          <Route
            element={
              <ProtectedRoute>
                <AppShell />
              </ProtectedRoute>
            }
          >
            <Route
              index
              element={<Navigate to="/dashboard" replace />}
            />
            <Route
              path="dashboard"
              element={
                <LazyPage>
                  <DashboardPage />
                </LazyPage>
              }
            />
            <Route path="documents" element={<LazyPage><DocumentsPage /></LazyPage>} />
            <Route path="documents/:id" element={<LazyPage><DocumentDetailPage /></LazyPage>} />
            <Route
              path="collections"
              element={
                <LazyPage>
                  <CollectionsPage />
                </LazyPage>
              }
            />
            <Route
              path="indexing"
              element={
                <LazyPage>
                  <IndexingPage />
                </LazyPage>
              }
            />
            <Route
              path="retrieval"
              element={
                <LazyPage>
                  <RetrievalPage />
                </LazyPage>
              }
            />
            <Route
              path="chat"
              element={
                <LazyPage>
                  <ChatPage />
                </LazyPage>
              }
            />
            <Route
              path="analytics"
              element={
                <LazyPage>
                  <AnalyticsPage />
                </LazyPage>
              }
            />
            <Route
              path="settings"
              element={
                <LazyPage>
                  <SettingsPage />
                </LazyPage>
              }
            />
            <Route
              path="profile"
              element={
                <LazyPage>
                  <ProfilePage />
                </LazyPage>
              }
            />
          </Route>

          {/* 404 */}
          <Route
            path="*"
            element={
              <LazyPage>
                <NotFoundPage />
              </LazyPage>
            }
          />
          </Routes>
        </BrowserRouter>
      </ErrorBoundary>
    </QueryClientProvider>
  );
}
