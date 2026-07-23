import { useEffect } from "react";
import { User, Mail, Shield, Calendar } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { useLayoutStore } from "../store";
import { useAuthStore } from "../store";

export function ProfilePage() {
  const setPageTitle = useLayoutStore((s) => s.setPageTitle);
  const { user } = useAuthStore();

  useEffect(() => {
    setPageTitle("Profile");
  }, [setPageTitle]);

  if (!user) {
    return (
      <div className="flex items-center justify-center py-16">
        <p className="text-sm text-surface-500">No user data available.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <div className="flex size-14 items-center justify-center rounded-full bg-brand-50 text-xl font-bold text-brand-600 dark:bg-brand-950 dark:text-brand-400">
          {(user.name ?? user.email ?? "U").slice(0, 2).toUpperCase()}
        </div>
        <div>
          <h1 className="text-xl font-bold text-surface-900 dark:text-surface-50">
            {user.name ?? "User"}
          </h1>
          <p className="mt-0.5 text-sm text-surface-500">{user.email}</p>
        </div>
      </div>

      {/* Details card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold">Account Details</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="flex items-center gap-3">
              <User className="size-4 text-surface-400" />
              <div>
                <dt className="text-xs text-surface-500">Username</dt>
                <dd className="text-sm font-medium text-surface-900 dark:text-surface-50">
                  {user.username ?? "N/A"}
                </dd>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Mail className="size-4 text-surface-400" />
              <div>
                <dt className="text-xs text-surface-500">Email</dt>
                <dd className="text-sm font-medium text-surface-900 dark:text-surface-50">{user.email}</dd>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Shield className="size-4 text-surface-400" />
              <div>
                <dt className="text-xs text-surface-500">Role</dt>
                <dd className="text-sm">
                  <Badge variant="secondary" className="text-[10px] capitalize">{user.role ?? "user"}</Badge>
                </dd>
              </div>
            </div>
            {user.created_at && (
              <div className="flex items-center gap-3">
                <Calendar className="size-4 text-surface-400" />
                <div>
                  <dt className="text-xs text-surface-500">Member Since</dt>
                  <dd className="text-sm font-medium text-surface-900 dark:text-surface-50">
                    {new Date(user.created_at).toLocaleDateString()}
                  </dd>
                </div>
              </div>
            )}
          </dl>
        </CardContent>
      </Card>
    </div>
  );
}
