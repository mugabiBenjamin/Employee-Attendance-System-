import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Provider } from "react-redux";
import "./index.css";
import App from "./App.tsx";
import store from "./store";
import { setAuth } from "./store/slices/authSlice";
import { authApi } from "./api/auth";
import { enumsCache } from "./lib/enumsCache";
import { enumsApi } from "./api/enums";
import ErrorBoundary from "./components/common/ErrorBoundary.tsx";

// Initialize auth and enums before rendering
const initializeAuth = async () => {
  try {
    // Prefetch enums to ensure permissions are available
    await enumsCache.prefetch(enumsApi.getAllEnums);

    const accessToken = localStorage.getItem("access_token");
    const refreshToken = localStorage.getItem("refresh_token");

    if (accessToken && refreshToken) {
      try {
        // Verify token is still valid by getting current user
        const user = await authApi.getCurrentUser();

        // Restore auth state
        store.dispatch(
          setAuth({
            access_token: accessToken,
            refresh_token: refreshToken,
            token_type: "bearer",
            user,
          })
        );
      } catch (error) {
        console.error("Failed to verify auth token:", error);
        // Clear invalid tokens
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
      }
    }
  } catch (error) {
    console.error("Failed to initialize auth or prefetch enums:", error);
  }
};

// Ensure root element exists before rendering
const rootElement = document.getElementById("root");
if (!rootElement) {
  console.error("Root element not found");
} else {
  // Initialize auth and enums before rendering
  initializeAuth().then(() => {
    createRoot(rootElement).render(
      <StrictMode>
        <Provider store={store}>
          <ErrorBoundary>
            <App />
          </ErrorBoundary>
        </Provider>
      </StrictMode>
    );
  });
}
