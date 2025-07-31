import { Navigate, Outlet } from "react-router-dom";
import { useSelector } from "react-redux";
import type { RootState } from "@/store";

interface ProtectedRouteProps {
  requiredPermissions: string[];
  children?: React.ReactNode;
}

function ProtectedRoute({
  requiredPermissions,
  children,
}: ProtectedRouteProps) {
  const { user, isAuthenticated } = useSelector(
    (state: RootState) => state.auth
  );

  if (!isAuthenticated || !user) {
    return <Navigate to="/login" replace />;
  }

  const hasPermission =
    requiredPermissions.length === 0 ||
    requiredPermissions.every(
      (perm) =>
        user.permissions.includes(perm) ||
        user.permissions.includes("all_permissions")
    );

  if (!hasPermission) {
    return <Navigate to="/" replace />;
  }

  return children ? <>{children}</> : <Outlet />;
}

export default ProtectedRoute;
