import apiClient from "./api";
import { storeTokens } from "./api";
import type { LoginRequest, LoginResponse, User } from "../types/auth";

export const authService = {
  async login(data: LoginRequest): Promise<LoginResponse> {
    const response = await apiClient.post<LoginResponse>(
      "/auth/login",
      data,
    );

    storeTokens({
      access_token: response.data.access_token,
      refresh_token: response.data.refresh_token,
    });

    return response.data;
  },

  async logout(): Promise<void> {
    try {
      await apiClient.post("/auth/logout");
    } catch {
      // Even if the server call fails, clear local state
    }
    localStorage.removeItem("rag_auth_tokens");
  },

  async refreshToken(refreshToken: string): Promise<{
    access_token: string;
    refresh_token: string;
  }> {
    const response = await apiClient.post<{
      access_token: string;
      refresh_token: string;
    }>("/auth/refresh", { refresh_token: refreshToken });
    return response.data;
  },

  async getCurrentUser(): Promise<User> {
    const response = await apiClient.get<User>("/auth/me");
    return response.data;
  },

  async updateProfile(data: Partial<User>): Promise<User> {
    const response = await apiClient.put<User>("/auth/profile", data);
    return response.data;
  },
};
