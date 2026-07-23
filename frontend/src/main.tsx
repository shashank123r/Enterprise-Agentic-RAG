import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles/globals.css";

// Initialize theme from store
const storedTheme = localStorage.getItem("rag_theme_store");
if (storedTheme) {
  try {
    const { state } = JSON.parse(storedTheme);
    if (state?.mode) {
      document.documentElement.classList.add(state.mode);
    } else {
      document.documentElement.classList.add("dark");
    }
  } catch {
    document.documentElement.classList.add("dark");
  }
} else {
  document.documentElement.classList.add("dark");
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
