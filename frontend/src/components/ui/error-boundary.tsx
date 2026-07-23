import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "./button";

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    this.setState({ errorInfo });
    console.error("[ErrorBoundary]", error, errorInfo);
  }

  private handleRetry = (): void => {
    this.setState({ error: null, errorInfo: null });
  };

  render(): ReactNode {
    if (this.state.error) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
          <div className="mb-4 rounded-full bg-red-50 p-3 dark:bg-red-950">
            <AlertCircle className="size-8 text-red-500 dark:text-red-400" />
          </div>
          <h2 className="mb-2 text-lg font-semibold text-surface-900 dark:text-surface-50">
            Something went wrong
          </h2>
          <p className="mb-1 max-w-md text-sm text-surface-500">
            An unexpected error occurred while rendering this section.
          </p>
          {this.state.error.message && (
            <p className="mb-4 max-w-md rounded bg-red-50 px-3 py-2 text-xs text-red-600 font-mono dark:bg-red-950 dark:text-red-400">
              {this.state.error.message}
            </p>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={this.handleRetry}
            aria-label="Retry rendering"
          >
            <RefreshCw className="mr-1.5 size-3.5" />
            Try again
          </Button>
        </div>
      );
    }

    return this.props.children;
  }
}
