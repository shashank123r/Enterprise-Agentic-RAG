import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Sparkles, Eye, EyeOff } from "lucide-react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { useAuthStore, useNotificationsStore } from "../store";
import { authService } from "../services/auth.service";

const loginSchema = z.object({
  email: z.string().email("Valid email is required"),
  password: z.string().min(1, "Password is required"),
});

type LoginFormData = z.infer<typeof loginSchema>;

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { setUser, setAuthenticated } = useAuthStore();
  const addNotification = useNotificationsStore((s) => s.addNotification);
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const from = (location.state as { from?: { pathname: string } })?.from
    ?.pathname ?? "/dashboard";

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
  });

  const onSubmit = async (data: LoginFormData) => {
    setIsSubmitting(true);
    try {
      const response = await authService.login(data);
      setUser(response.user);
      setAuthenticated(true);
      addNotification({
        type: "success",
        title: "Welcome back!",
        message: `Signed in as ${response.user.full_name ?? response.user.username}`,
      });
      navigate(from, { replace: true });
    } catch (error: unknown) {
      const axiosDetail = (
        error as { response?: { data?: { detail?: string } } }
      )?.response?.data?.detail;
      const message = axiosDetail ?? "Invalid credentials. Please try again.";
      addNotification({
        type: "error",
        title: "Login failed",
        message,
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-50 p-4 dark:bg-surface-950">
      <div className="w-full max-w-sm">
        {/* Logo & Brand */}
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-xl bg-brand-600 shadow-lg">
            <Sparkles className="size-6 text-white" />
          </div>
          <h1 className="text-xl font-semibold text-surface-900 dark:text-surface-50">
            RAG Platform
          </h1>
          <p className="mt-1 text-sm text-surface-500 dark:text-surface-400">
            Sign in to your enterprise knowledge base
          </p>
        </div>

        {/* Login form */}
        <div className="rounded-xl border border-surface-200 bg-white p-6 shadow-card dark:border-surface-700 dark:bg-surface-800">
          <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
            <Input
              label="Email"
              type="email"
              placeholder="you@company.com"
              error={errors.email?.message}
              autoComplete="email"
              autoFocus
              {...register("email")}
            />

            <div className="relative">
              <Input
                label="Password"
                type={showPassword ? "text" : "password"}
                placeholder="Enter your password"
                error={errors.password?.message}
                autoComplete="current-password"
                {...register("password")}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-[34px] text-surface-400 hover:text-surface-600 dark:hover:text-surface-300"
                tabIndex={-1}
              >
                {showPassword ? (
                  <EyeOff className="size-4" />
                ) : (
                  <Eye className="size-4" />
                )}
              </button>
            </div>

            <Button type="submit" className="w-full" disabled={isSubmitting}>
              {isSubmitting ? (
                <div className="flex items-center gap-2">
                  <div className="size-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                  Signing in...
                </div>
              ) : (
                "Sign in"
              )}
            </Button>
          </form>
        </div>

        <p className="mt-6 text-center text-xs text-surface-400">
          Enterprise Hybrid RAG Platform &copy; {new Date().getFullYear()}
        </p>
      </div>
    </div>
  );
}
