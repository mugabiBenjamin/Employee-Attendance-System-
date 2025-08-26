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

// Restore auth state and prefetch enums on app startup
const initializeAuth = async () => {
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
    } catch {
      // Token is invalid, clear stored tokens
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
    }
  }
};

// Initialize auth and enums before rendering
initializeAuth().then(() => {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <Provider store={store}>
        <App />
      </Provider>
    </StrictMode>
  );
});
