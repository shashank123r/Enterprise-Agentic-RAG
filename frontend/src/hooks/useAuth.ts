import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore, useNotificationsStore } from "../store";
import { authService } from "../services/auth.service";

export function useAuth() {
  const navigate = useNavigate();
  const {
    user,
    isAuthenticated,
    isLoading,
    setUser,
    setAuthenticated,
    logout: clearAuth,
  } = useAuthStore();
  const addNotification = useNotificationsStore((s) => s.addNotification);

  const login = useCallback(
    async (email: string, password: string) => {
      try {
        const response = await authService.login({ email, password });
        setUser(response.user);
        setAuthenticated(true);
        addNotification({
          type: "success",
          title: "Welcome back!",
          message: `Signed in as ${response.user.full_name || response.user.email}`,
        });
        return response.user;
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Invalid credentials";
        addNotification({
          type: "error",
          title: "Login failed",
          message,
        });
        throw error;
      }
    },
    [setUser, setAuthenticated, addNotification],
  );

  const logout = useCallback(async () => {
    try {
      await authService.logout();
    } catch {
      // Ignore logout errors
    }
    clearAuth();
    navigate("/login");
  }, [clearAuth, navigate]);

  return {
    user,
    isAuthenticated,
    isLoading,
    login,
    logout,
  };
}
