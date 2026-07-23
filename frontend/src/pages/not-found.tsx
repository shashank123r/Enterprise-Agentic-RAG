import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { FileQuestion, ArrowLeft } from "lucide-react";
import { Button } from "../components/ui/button";
import { useLayoutStore } from "../store";

export function NotFoundPage() {
  const navigate = useNavigate();
  const setPageTitle = useLayoutStore((s) => s.setPageTitle);

  useEffect(() => {
    setPageTitle("Not Found");
  }, [setPageTitle]);

  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <div className="mb-4 rounded-full bg-surface-100 p-4 dark:bg-surface-800">
        <FileQuestion className="size-12 text-surface-400" />
      </div>
      <h1 className="mb-2 text-2xl font-bold text-surface-900 dark:text-surface-50">Page not found</h1>
      <p className="mb-6 max-w-sm text-sm text-surface-500">
        The page you are looking for does not exist or has been moved.
      </p>
      <Button variant="outline" size="sm" onClick={() => navigate("/dashboard")}>
        <ArrowLeft className="mr-1.5 size-3.5" />
        Back to Dashboard
      </Button>
    </div>
  );
}
