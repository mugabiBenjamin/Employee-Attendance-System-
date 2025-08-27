import React, { type ReactNode, useContext } from "react";
import { Navigate, Outlet } from "react-router-dom";
import { useSelector } from "react-redux";
import { AuthContext } from "@/context/AuthContext";
import type { RootState } from "@/store";
import { Skeleton } from "@/components/ui/skeleton";
import type { Permission } from "@/api/types";

interface ProtectedRouteProps {
  requiredPermissions: Permission[];
  children?: ReactNode;
}

const ProtectedRoute: React.FC<ProtectedRouteProps> = ({
  requiredPermissions,
  children,
}) => {
  // Get user data from Redux
  const { user, isAuthenticated } = useSelector(
    (state: RootState) => state.auth
  );

  // Also check AuthContext if available
  const authContext = useContext(AuthContext);
  const {
    isLoading: contextLoading,
    isAuthenticated: contextIsAuthenticated,
    user: contextUser,
  } = authContext || {};

  const isAuth = isAuthenticated || contextIsAuthenticated || false;
  const authUser = user || contextUser || null;
  const isLoading = contextLoading || false;

  // Loading skeleton
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Skeleton className="w-[100px] h-[20px] rounded-full" />
      </div>
    );
  }

  // Redirect to login if unauthenticated
  if (!isAuth || !authUser) {
    return <Navigate to="/login" replace />;
  }

  // ✅ Permission check is now type-safe
  const hasPermission =
    requiredPermissions.length === 0 ||
    requiredPermissions.every(
      (perm) =>
        authUser.permissions.includes(perm) ||
        authUser.permissions.includes("all_permissions")
    );

  if (!hasPermission) {
    return <Navigate to="/" replace />;
  }

  return children ? <>{children}</> : <Outlet />;
};

export default ProtectedRoute;
