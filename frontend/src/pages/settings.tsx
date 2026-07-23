import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Settings,
  Bell,
  Palette,
  Database,
  Key,
  Shield,
  CheckCircle2,
  XCircle,
  ExternalLink,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Skeleton } from "../components/ui/skeleton";
import { useLayoutStore, useThemeStore } from "../store";
import { cn } from "../lib/utils";
import { healthService } from "../services/health.service";
import { retrievalService } from "../services/retrieval.service";

const sections = [
  { id: "general", label: "General", icon: Settings },
  { id: "appearance", label: "Appearance", icon: Palette },
  { id: "system", label: "System", icon: Database },
  { id: "storage", label: "Storage", icon: Database },
  { id: "security", label: "Security", icon: Shield },
  { id: "api-keys", label: "API Keys", icon: Key },
];

function ConfigRow({ label, value, status }: { label: string; value: string; status?: "healthy" | "unhealthy" | "warning" }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-surface-100 last:border-0 dark:border-surface-700">
      <div>
        <p className="text-sm font-medium text-surface-900 dark:text-surface-100">{label}</p>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-sm text-surface-500 font-mono">{value}</span>
        {status && (
          <Badge variant={status === "healthy" ? "success" : status === "unhealthy" ? "destructive" : "warning"} className="text-[10px]">
            {status}
          </Badge>
        )}
      </div>
    </div>
  );
}

export function SettingsPage() {
  const setPageTitle = useLayoutStore((s) => s.setPageTitle);
  const { mode, setMode } = useThemeStore();
  const [activeSection, setActiveSection] = useState("system");

  useEffect(() => {
    setPageTitle("Settings");
  }, [setPageTitle]);

  const { data: embeddingHealth, isLoading: healthLoading } = useQuery({
    queryKey: ["embedding", "health"],
    queryFn: () => healthService.getEmbeddingHealth(),
  });

  const { data: vectorHealth } = useQuery({
    queryKey: ["vector-store", "health"],
    queryFn: () => healthService.getVectorStoreHealth(),
  });

  const { data: bm25Status } = useQuery({
    queryKey: ["bm25", "status"],
    queryFn: () => retrievalService.getBM25Status(),
  });

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold text-surface-900 dark:text-surface-50">Settings</h1>
        <p className="mt-1 text-sm text-surface-500">Manage your platform configuration</p>
      </div>

      <div className="flex flex-col gap-6 lg:flex-row">
        {/* Side navigation */}
        <div className="flex flex-row gap-1 overflow-x-auto lg:w-48 lg:flex-col">
          {sections.map((section) => (
            <button
              key={section.id}
              onClick={() => setActiveSection(section.id)}
              className={cn(
                "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors",
                activeSection === section.id
                  ? "bg-brand-50 text-brand-700 dark:bg-brand-950 dark:text-brand-300"
                  : "text-surface-600 hover:bg-surface-100 dark:text-surface-400 dark:hover:bg-surface-700",
              )}
            >
              <section.icon className="size-4" />
              {section.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 space-y-6">
          {activeSection === "system" && (
            <Card>
              <CardHeader>
                <CardTitle>System Configuration</CardTitle>
                <CardDescription>Current runtime configuration from backend</CardDescription>
              </CardHeader>
              <CardContent>
                {healthLoading ? (
                  <div className="space-y-3">
                    {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
                  </div>
                ) : (
                  <div>
                    <ConfigRow
                      label="Embedding Provider"
                      value={embeddingHealth?.provider ?? "N/A"}
                      status={embeddingHealth?.healthy ? "healthy" : "unhealthy"}
                    />
                    <ConfigRow
                      label="Embedding Model"
                      value={embeddingHealth?.model ?? "N/A"}
                    />
                    <ConfigRow
                      label="Embedding Latency"
                      value={embeddingHealth?.latency_ms ? `${Math.round(embeddingHealth.latency_ms)}ms` : "N/A"}
                    />
                    <ConfigRow
                      label="Vector Store"
                      value={vectorHealth?.provider ?? "N/A"}
                      status={vectorHealth?.healthy ? "healthy" : "unhealthy"}
                    />
                    <ConfigRow
                      label="Collections"
                      value={String(vectorHealth?.collections_count ?? 0)}
                    />
                    <ConfigRow
                      label="BM25 Index"
                      value={bm25Status?.healthy ? `Built (${bm25Status.total_docs} docs)` : "Not built"}
                      status={bm25Status?.healthy ? "healthy" : "warning"}
                    />
                    <ConfigRow
                      label="Retrieval Method"
                      value="Dense + BM25 + Hybrid"
                    />
                    <div className="pt-4 text-xs text-surface-400">
                      <p>Configuration is read-only and managed via backend environment variables.</p>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {activeSection === "appearance" && (
            <Card>
              <CardHeader>
                <CardTitle>Appearance</CardTitle>
                <CardDescription>Customize the look and feel of the platform</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-surface-900 dark:text-surface-100">Theme</p>
                    <p className="text-xs text-surface-500">Choose between dark and light mode</p>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant={mode === "dark" ? "default" : "outline"}
                      size="sm"
                      onClick={() => setMode("dark")}
                    >
                      Dark
                    </Button>
                    <Button
                      variant={mode === "light" ? "default" : "outline"}
                      size="sm"
                      onClick={() => setMode("light")}
                    >
                      Light
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {activeSection === "general" && (
            <Card>
              <CardHeader>
                <CardTitle>General Settings</CardTitle>
                <CardDescription>Platform information</CardDescription>
              </CardHeader>
              <CardContent>
                <ConfigRow label="Platform" value="Enterprise RAG Platform" />
                <ConfigRow label="Version" value="0.1.0" />
                <ConfigRow label="Environment" value="development" />
              </CardContent>
            </Card>
          )}

          {(activeSection !== "general" && activeSection !== "appearance" && activeSection !== "system") && (
            <Card>
              <CardContent className="flex flex-col items-center py-12 text-center">
                <Settings className="mb-3 size-10 text-surface-300 dark:text-surface-600" />
                <h3 className="text-sm font-medium text-surface-900 dark:text-surface-100">Under Development</h3>
                <p className="mt-1 text-xs text-surface-500 max-w-xs">
                  This section requires additional backend endpoints to display configuration data.
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
