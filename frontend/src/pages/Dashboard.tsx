import { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store";
import { attendanceApi } from "@/api/attendance";
import type { AttendanceRecord, AttendanceSummary } from "@/api/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  AlertCircleIcon,
  Clock,
  Calendar,
  Users,
  Timer,
  CalendarDays,
  UserCheck,
} from "lucide-react";
import { format } from "date-fns";
import { Skeleton } from "@/components/ui/skeleton";

function Dashboard() {
  const { user } = useSelector((state: RootState) => state.auth);
  const [attendanceSummary, setAttendanceSummary] =
    useState<AttendanceSummary | null>(null);
  const [recentAttendance, setRecentAttendance] = useState<AttendanceRecord[]>(
    []
  );
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      setError(null);
      try {
        if (user) {
          const [summary, history] = await Promise.all([
            attendanceApi.getSummary(user.id),
            attendanceApi.getHistory({ user_id: user.id, limit: 5 }),
          ]);
          setAttendanceSummary(summary);
          setRecentAttendance(history.items);
        }
      } catch {
        setError("Failed to load dashboard data");
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [user]);

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 md:p-6">
      {error && (
        <Alert variant="destructive">
          <AlertCircleIcon className="h-4 w-4" />
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {loading ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[...Array(3)].map((_, i) => (
            <Skeleton key={i} className="h-32 w-full" />
          ))}
          <Skeleton className="h-48 w-full col-span-full" />
        </div>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {/* Attendance Overview Card */}
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-md font-medium">
                  Attendance Overview
                </CardTitle>
                <Clock className="h-8 w-8 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  <div className="flex items-center space-x-2">
                    <Timer className="h-4 w-4 text-blue-500" />
                    <span className="text-sm">
                      Total Hours: {attendanceSummary?.total_hours ?? "0"} hours
                    </span>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Clock className="h-4 w-4 text-orange-500" />
                    <span className="text-sm">
                      Overtime: {attendanceSummary?.overtime_hours ?? "0"} hours
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Leave Balance Card */}
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-md font-medium">
                  Leave Balance
                </CardTitle>
                <Calendar className="h-8 w-8 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  <div className="flex items-center space-x-2">
                    <CalendarDays className="h-4 w-4 text-green-500" />
                    <span className="text-sm">
                      Available Leave: {attendanceSummary?.leave_balance ?? "0"}{" "}
                      days
                    </span>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Clock className="h-4 w-4 text-yellow-500" />
                    <span className="text-sm">
                      Pending Requests:{" "}
                      {attendanceSummary?.pending_requests ?? "0"}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Team Attendance Card */}
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-md font-medium">
                  Team Attendance
                </CardTitle>
                <Users className="h-8 w-8 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                {user.permissions.includes("view_team_attendance") ? (
                  <div className="flex items-center space-x-2">
                    <UserCheck className="h-4 w-4 text-green-500" />
                    <span className="text-sm">
                      Team Members Present:{" "}
                      {attendanceSummary?.team_present ?? "0"}
                    </span>
                  </div>
                ) : (
                  <span className="text-sm text-muted-foreground">
                    Team attendance data not available
                  </span>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Recent Attendance Table */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-md font-medium">
                Recent Attendance
              </CardTitle>
              <Clock className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <div className="min-w-full overflow-hidden rounded-md border">
                  <table className="w-full">
                    <thead>
                      <tr className="bg-muted">
                        <th className="p-2 text-left text-xs font-medium">
                          Date
                        </th>
                        <th className="p-2 text-left text-xs font-medium">
                          Clock In
                        </th>
                        <th className="p-2 text-left text-xs font-medium">
                          Clock Out
                        </th>
                        <th className="p-2 text-left text-xs font-medium">
                          Status
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {recentAttendance.length > 0 ? (
                        recentAttendance.map((record) => (
                          <tr key={record.attendance_id} className="border-t">
                            <td className="p-2 text-xs">
                              {format(
                                new Date(record.created_at),
                                "MMM d, yyyy"
                              )}
                            </td>
                            <td className="p-2 text-xs">
                              {format(new Date(record.clock_in), "h:mm a")}
                            </td>
                            <td className="p-2 text-xs">
                              {record.clock_out
                                ? format(new Date(record.clock_out), "h:mm a")
                                : "-"}
                            </td>
                            <td className="p-2 text-xs">
                              <span
                                className={`inline-flex items-center rounded-full px-2 py-1 text-xs font-medium ${
                                  record.status === "present"
                                    ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300"
                                    : record.status === "late"
                                    ? "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300"
                                    : "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300"
                                }`}
                              >
                                {record.status}
                              </span>
                            </td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td
                            colSpan={4}
                            className="p-4 text-center text-sm text-muted-foreground"
                          >
                            No recent attendance records found
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

export default Dashboard;
