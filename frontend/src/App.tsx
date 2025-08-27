import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Provider } from "react-redux";
import store from "./store";
import MainLayout from "./components/layout/MainLayout";
import ProtectedRoute from "./components/common/ProtectedRoute";
import { ThemeProvider } from "./components/theme-provider";
import { ROUTES } from "./routes/paths";
import { Suspense, lazy } from "react";
import type { Permission } from "./api/types";

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
const OvertimeRecords = lazy(() => import("./pages/OvertimeRecords"));
const OvertimeForm = lazy(() => import("./pages/OvertimeForm"));
const LeaveRequestForm = lazy(() => import("./pages/LeaveRequestForm"));
const LeaveRequests = lazy(() => import("./pages/LeaveRequests"));
const LeaveBalances = lazy(() => import("./pages/LeaveBalances"));
const LeavePolicies = lazy(() => import("./pages/LeavePolicies"));
const HolidayList = lazy(() => import("./pages/HolidayList"));
const HolidayForm = lazy(() => import("./pages/HolidayForm"));
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
                      requiredPermissions={
                        ["clock_in", "clock_out"] as Permission[]
                      }
                    >
                      <AttendanceClock />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.ATTENDANCE_HISTORY}
                  element={
                    <ProtectedRoute
                      requiredPermissions={
                        ["view_own_attendance"] as Permission[]
                      }
                    >
                      <AttendanceHistory />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.TIME_CORRECTION}
                  element={
                    <ProtectedRoute
                      requiredPermissions={
                        ["view_own_attendance"] as Permission[]
                      }
                    >
                      <TimeCorrection />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.ATTENDANCE_SUMMARY}
                  element={
                    <ProtectedRoute
                      requiredPermissions={
                        ["view_own_attendance"] as Permission[]
                      }
                    >
                      <AttendanceSummary />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.DEPARTMENTS}
                  element={
                    <ProtectedRoute
                      requiredPermissions={
                        ["manage_departments"] as Permission[]
                      }
                    >
                      <DepartmentsList />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.DEPARTMENT_EDIT}
                  element={
                    <ProtectedRoute
                      requiredPermissions={
                        ["manage_departments"] as Permission[]
                      }
                    >
                      <DepartmentForm />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.EMERGENCY_CONTACTS}
                  element={
                    <ProtectedRoute
                      requiredPermissions={
                        [
                          "view_own_attendance",
                          "manage_employees",
                        ] as Permission[]
                      }
                    >
                      <EmergencyContactsList />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.EMERGENCY_CONTACT_EDIT}
                  element={
                    <ProtectedRoute
                      requiredPermissions={
                        [
                          "view_own_attendance",
                          "manage_employees",
                        ] as Permission[]
                      }
                    >
                      <EmergencyContactForm />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.EMPLOYEE_HIERARCHY}
                  element={
                    <ProtectedRoute
                      requiredPermissions={
                        [
                          "view_team_attendance",
                          "manage_employees",
                        ] as Permission[]
                      }
                    >
                      <EmployeeHierarchy />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.SHIFT_PATTERNS}
                  element={
                    <ProtectedRoute
                      requiredPermissions={["manage_employees"] as Permission[]}
                    >
                      <ShiftPatternsList />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.SHIFT_PATTERN_EDIT}
                  element={
                    <ProtectedRoute
                      requiredPermissions={["manage_employees"] as Permission[]}
                    >
                      <ShiftPatternForm />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.SYSTEM_LOGS}
                  element={
                    <ProtectedRoute
                      requiredPermissions={["view_logs"] as Permission[]}
                    >
                      <SystemLogs />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.USER_MANAGEMENT}
                  element={
                    <ProtectedRoute
                      requiredPermissions={
                        [
                          "manage_users",
                          "manage_roles",
                          "manage_departments",
                        ] as Permission[]
                      }
                    >
                      <UserManagement />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.OVERTIME_RECORDS}
                  element={
                    <ProtectedRoute
                      requiredPermissions={
                        [
                          "view_own_attendance",
                          "manage_overtime",
                        ] as Permission[]
                      }
                    >
                      <OvertimeRecords />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.OVERTIME_FORM}
                  element={
                    <ProtectedRoute
                      requiredPermissions={["manage_overtime"] as Permission[]}
                    >
                      <OvertimeForm />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.LEAVE_REQUEST}
                  element={
                    <ProtectedRoute
                      requiredPermissions={["request_leave"] as Permission[]}
                    >
                      <LeaveRequestForm />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.LEAVE_REQUESTS}
                  element={
                    <ProtectedRoute
                      requiredPermissions={
                        [
                          "manage_employees",
                          "manage_leave_policies",
                        ] as Permission[]
                      }
                    >
                      <LeaveRequests />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.LEAVE_BALANCES}
                  element={
                    <ProtectedRoute
                      requiredPermissions={
                        [
                          "view_own_attendance",
                          "manage_employees",
                        ] as Permission[]
                      }
                    >
                      <LeaveBalances />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.LEAVE_POLICIES}
                  element={
                    <ProtectedRoute
                      requiredPermissions={
                        ["manage_leave_policies"] as Permission[]
                      }
                    >
                      <LeavePolicies />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.HOLIDAYS}
                  element={
                    <ProtectedRoute
                      requiredPermissions={["manage_employees"] as Permission[]}
                    >
                      <HolidayList />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path={ROUTES.HOLIDAY_FORM}
                  element={
                    <ProtectedRoute
                      requiredPermissions={["manage_employees"] as Permission[]}
                    >
                      <HolidayForm />
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
