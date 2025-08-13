import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Provider } from "react-redux";
import store from "./store";
import MainLayout from "./components/layout/MainLayout";
import ProtectedRoute from "./components/common/ProtectedRoute";
import { ThemeProvider } from "./components/theme-provider";
import { ROUTES } from "./routes/paths";
import { Suspense, lazy } from "react";
import { Permission } from "./api/enums";

// Lazy load pages
const Login = lazy(() => import("./pages/Login"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const AttendanceClock = lazy(() => import("./pages/AttendanceClock"));
const AttendanceHistory = lazy(() => import("./pages/AttendanceHistory"));
const TimeCorrection = lazy(() => import("./pages/TimeCorrection"));
const AttendanceSummary = lazy(() => import("./pages/AttendanceSummary"));
const DepartmentsList = lazy(() => import("./pages/DepartmentsList"));
const DepartmentForm = lazy(() => import("./pages/DepartmentForm"));
const EmergencyContactsList = lazy(
  () => import("./pages/EmergencyContactsList")
);
const EmergencyContactForm = lazy(() => import("./pages/EmergencyContactForm"));
const EmployeeHierarchy = lazy(() => import("./pages/EmployeeHierarchy"));
const ShiftPatternsList = lazy(() => import("./pages/ShiftPatternsList"));
const ShiftPatternForm = lazy(() => import("./pages/ShiftPatternForm"));
const SystemLogs = lazy(() => import("./pages/SystemLogs"));
const UserManagement = lazy(() => import("./pages/UserManagement"));
const NotFound = lazy(() => import("./pages/NotFound"));

function App() {
  return (
    <ThemeProvider defaultTheme="dark" storageKey="vite-ui-theme">
      <Provider store={store}>
        <BrowserRouter>
          <Suspense fallback={<div>Loading...</div>}>
            <Routes>
              <Route path={ROUTES.LOGIN} element={<Login />} />

              <Route element={<MainLayout />}>
                <Route
                  path={ROUTES.DASHBOARD}
                  element={
                    <ProtectedRoute requiredPermissions={[]}>
                      <Dashboard />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.ATTENDANCE_CLOCK}
                  element={
                    <ProtectedRoute
                      requiredPermissions={[
                        Permission.CLOCK_IN,
                        Permission.CLOCK_OUT,
                      ]}
                    >
                      <AttendanceClock />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.ATTENDANCE_HISTORY}
                  element={
                    <ProtectedRoute
                      requiredPermissions={[Permission.VIEW_OWN_ATTENDANCE]}
                    >
                      <AttendanceHistory />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.TIME_CORRECTION}
                  element={
                    <ProtectedRoute
                      requiredPermissions={[Permission.VIEW_OWN_ATTENDANCE]}
                    >
                      <TimeCorrection />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.ATTENDANCE_SUMMARY}
                  element={
                    <ProtectedRoute
                      requiredPermissions={[Permission.VIEW_OWN_ATTENDANCE]}
                    >
                      <AttendanceSummary />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.DEPARTMENTS}
                  element={
                    <ProtectedRoute
                      requiredPermissions={[Permission.MANAGE_DEPARTMENTS]}
                    >
                      <DepartmentsList />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.DEPARTMENT_EDIT}
                  element={
                    <ProtectedRoute
                      requiredPermissions={[Permission.MANAGE_DEPARTMENTS]}
                    >
                      <DepartmentForm />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.EMERGENCY_CONTACTS}
                  element={
                    <ProtectedRoute
                      requiredPermissions={[
                        Permission.VIEW_OWN_ATTENDANCE,
                        Permission.MANAGE_EMPLOYEES,
                      ]}
                    >
                      <EmergencyContactsList />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.EMERGENCY_CONTACT_EDIT}
                  element={
                    <ProtectedRoute
                      requiredPermissions={[
                        Permission.VIEW_OWN_ATTENDANCE,
                        Permission.MANAGE_EMPLOYEES,
                      ]}
                    >
                      <EmergencyContactForm />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.EMPLOYEE_HIERARCHY}
                  element={
                    <ProtectedRoute
                      requiredPermissions={[
                        Permission.VIEW_TEAM_ATTENDANCE,
                        Permission.MANAGE_EMPLOYEES,
                      ]}
                    >
                      <EmployeeHierarchy />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.SHIFT_PATTERNS}
                  element={
                    <ProtectedRoute
                      requiredPermissions={[Permission.MANAGE_EMPLOYEES]}
                    >
                      <ShiftPatternsList />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.SHIFT_PATTERN_EDIT}
                  element={
                    <ProtectedRoute
                      requiredPermissions={[Permission.MANAGE_EMPLOYEES]}
                    >
                      <ShiftPatternForm />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.SYSTEM_LOGS}
                  element={
                    <ProtectedRoute
                      requiredPermissions={[Permission.VIEW_LOGS]}
                    >
                      <SystemLogs />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.USER_MANAGEMENT}
                  element={
                    <ProtectedRoute
                      requiredPermissions={[
                        Permission.MANAGE_USERS,
                        Permission.MANAGE_ROLES,
                        Permission.MANAGE_DEPARTMENTS,
                      ]}
                    >
                      <UserManagement />
                    </ProtectedRoute>
                  }
                />
                <Route path={ROUTES.NOT_FOUND} element={<NotFound />} />
              </Route>
            </Routes>
          </Suspense>
        </BrowserRouter>
      </Provider>
    </ThemeProvider>
  );
}

export default App;
