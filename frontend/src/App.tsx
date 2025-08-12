import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Provider } from "react-redux";
import store from "./store";
import MainLayout from "./components/layout/MainLayout";
import ProtectedRoute from "./components/common/ProtectedRoute";
import { ThemeProvider } from "./components/theme-provider";
import {
  Login,
  Dashboard,
  AttendanceClock,
  AttendanceHistory,
  TimeCorrection,
  AttendanceSummary,
  DepartmentsList,
  EmployeeHierarchy,
  DepartmentForm,
  EmergencyContactsList,
  EmergencyContactForm,
  ShiftPatternsList,
  ShiftPatternForm,
  SystemLogs,
  UserManagement,
} from "./pages/index";

function App() {
  return (
    <ThemeProvider defaultTheme="dark" storageKey="vite-ui-theme">
    <Provider store={store}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<MainLayout />}>
            <Route
              path="/"
              element={
                <ProtectedRoute requiredPermissions={[]}>
                  <Dashboard />
                </ProtectedRoute>
              }
            />
            <Route
              path="/attendance/clock"
              element={
                <ProtectedRoute requiredPermissions={["clock_in", "clock_out"]}>
                  <AttendanceClock />
                </ProtectedRoute>
              }
            />
            <Route
              path="/attendance/history"
              element={
                <ProtectedRoute requiredPermissions={["view_own_attendance"]}>
                  <AttendanceHistory />
                </ProtectedRoute>
              }
            />
            <Route
              path="/attendance/time-correction"
              element={
                <ProtectedRoute requiredPermissions={["view_own_attendance"]}>
                  <TimeCorrection />
                </ProtectedRoute>
              }
            />
            <Route
              path="/attendance/summary"
              element={
                <ProtectedRoute requiredPermissions={["view_own_attendance"]}>
                  <AttendanceSummary />
                </ProtectedRoute>
              }
            />
            <Route
              path="/departments"
              element={
                <ProtectedRoute requiredPermissions={["manage_departments"]}>
                  <DepartmentsList />
                </ProtectedRoute>
              }
            />
            <Route
              path="/departments/edit/:id?"
              element={
                <ProtectedRoute requiredPermissions={["manage_departments"]}>
                  <DepartmentForm />
                </ProtectedRoute>
              }
            />
            <Route
              path="/emergency-contacts"
              element={
                <ProtectedRoute
                  requiredPermissions={[
                    "view_own_attendance",
                    "manage_employees",
                  ]}
                >
                  <EmergencyContactsList />
                </ProtectedRoute>
              }
            />
            <Route
              path="/emergency-contacts/edit/:id?"
              element={
                <ProtectedRoute
                  requiredPermissions={[
                    "view_own_attendance",
                    "manage_employees",
                  ]}
                >
                  <EmergencyContactForm />
                </ProtectedRoute>
              }
            />
            <Route
              path="/employee-hierarchy"
              element={
                <ProtectedRoute
                  requiredPermissions={[
                    "view_team_attendance",
                    "manage_employees",
                  ]}
                >
                  <EmployeeHierarchy />
                </ProtectedRoute>
              }
            />
            <Route
              path="/shift-patterns"
              element={
                <ProtectedRoute requiredPermissions={["manage_employees"]}>
                  <ShiftPatternsList />
                </ProtectedRoute>
              }
            />
            <Route
              path="/shift-patterns/edit/:id?"
              element={
                <ProtectedRoute requiredPermissions={["manage_employees"]}>
                  <ShiftPatternForm />
                </ProtectedRoute>
              }
            />
            <Route
              path="/system-logs"
              element={
                <ProtectedRoute requiredPermissions={["view_logs"]}>
                  <SystemLogs />
                </ProtectedRoute>
              }
            />
            <Route
              path="/user-management"
              element={
                <ProtectedRoute
                  requiredPermissions={[
                    "manage_users",
                    "manage_roles",
                    "manage_departments",
                  ]}
                >
                  <UserManagement />
                </ProtectedRoute>
              }
            />
          </Route>
        </Routes>
      </BrowserRouter>
    </Provider>
    </ThemeProvider>
  );
}

export default App;
