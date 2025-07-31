import { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store";
import { attendanceApi } from "@/api/attendance";
import type { AttendanceRecord, AttendanceSummary } from "@/api/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircleIcon } from "lucide-react";
import { format } from "date-fns";
import { Navigate } from "react-router-dom";

function Dashboard() {
  const { user } = useSelector((state: RootState) => state.auth);
  const [attendanceSummary, setAttendanceSummary] =
    useState<AttendanceSummary | null>(null);
  const [recentAttendance, setRecentAttendance] = useState<AttendanceRecord[]>(
    []
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        if (user) {
          const summary = await attendanceApi.getSummary(user.id);
          setAttendanceSummary(summary);
          const history = await attendanceApi.getHistory({
            user_id: user.id,
            limit: 5,
          });
          setRecentAttendance(history.items);
        }
      } catch {
        setError("Failed to load dashboard data");
      }
    };
    fetchData();
  }, [user]);

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 md:p-6">
      {error && (
        <Alert variant="destructive">
          <AlertCircleIcon />
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Attendance Overview</CardTitle>
          </CardHeader>
          <CardContent>
            <p>Total Hours: {attendanceSummary?.total_hours || "0"} hours</p>
            <p>Overtime: {attendanceSummary?.overtime_hours || "0"} hours</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Leave Balance</CardTitle>
          </CardHeader>
          <CardContent>
            <p>
              Available Leave: {attendanceSummary?.leave_balance || "0"} days
            </p>
            <p>
              Pending Requests: {attendanceSummary?.pending_requests || "0"}
            </p>
          </CardContent>
        </Card>
        {user.permissions.includes("view_team_attendance") && (
          <Card>
            <CardHeader>
              <CardTitle>Team Attendance</CardTitle>
            </CardHeader>
            <CardContent>
              <p>
                Team Members Present: {attendanceSummary?.team_present || "0"}
              </p>
            </CardContent>
          </Card>
        )}
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Recent Attendance</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-hidden rounded-md border">
            <table className="w-full">
              <thead>
                <tr className="bg-muted">
                  <th className="p-2 text-left">Date</th>
                  <th className="p-2 text-left">Clock In</th>
                  <th className="p-2 text-left">Clock Out</th>
                  <th className="p-2 text-left">Status</th>
                </tr>
              </thead>
              <tbody>
                {recentAttendance.map((record) => (
                  <tr key={record.id}>
                    <td className="p-2">
                      {format(new Date(record.created_at), "MMM d, yyyy")}
                    </td>
                    <td className="p-2">
                      {format(new Date(record.clock_in), "h:mm a")}
                    </td>
                    <td className="p-2">
                      {record.clock_out
                        ? format(new Date(record.clock_out), "h:mm a")
                        : "-"}
                    </td>
                    <td className="p-2">{record.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default Dashboard;
