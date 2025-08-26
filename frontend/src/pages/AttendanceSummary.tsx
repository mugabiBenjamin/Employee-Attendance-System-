import { useEffect, useState } from "react";
import { useSelector, useDispatch } from "react-redux";
import type { RootState } from "@/store";
import { attendanceApi } from "@/api/attendance";
import { setSummary } from "@/store/slices/attendanceSlice";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircleIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

function AttendanceSummary() {
  const dispatch = useDispatch();
  const { user } = useSelector((state: RootState) => state.auth);
  const { summary } = useSelector((state: RootState) => state.attendance);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  const fetchSummary = async () => {
    if (!user) return;
    setLoading(true);
    setError(null);
    try {
      const data = await attendanceApi.getSummary(user.id);
      dispatch(setSummary(data));
    } catch {
      setError("Failed to load summary");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSummary();
  }, [user, dispatch]);

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 md:p-6">
      {error && (
        <Alert variant="destructive">
          <AlertCircleIcon className="h-4 w-4" />
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>
            {error}
            <Button
              variant="outline"
              size="sm"
              className="ml-4"
              onClick={fetchSummary}
            >
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      )}
      <Card>
        <CardHeader>
          <CardTitle>Monthly Attendance Summary</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="grid gap-4">
              {[...Array(4)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : (
            <div className="grid gap-4">
              <div>
                <h3 className="text-lg font-semibold">Total Hours</h3>
                <p>{summary?.total_hours || "0"} hours</p>
              </div>
              <div>
                <h3 className="text-lg font-semibold">Overtime Hours</h3>
                <p>{summary?.overtime_hours || "0"} hours</p>
              </div>
              <div>
                <h3 className="text-lg font-semibold">Leave Balance</h3>
                <p>{summary?.leave_balance || "0"} days</p>
              </div>
              <div>
                <h3 className="text-lg font-semibold">Pending Requests</h3>
                <p>{summary?.pending_requests || "0"}</p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default AttendanceSummary;