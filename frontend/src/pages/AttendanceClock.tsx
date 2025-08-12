import { useState } from "react";
import { useSelector, useDispatch } from "react-redux";
import type { RootState } from "@/store";
import { attendanceApi } from "@/api/attendance";
import { setRecords } from "@/store/slices/attendanceSlice";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircleIcon } from "lucide-react";

function AttendanceClock() {
  const dispatch = useDispatch();
  const { user } = useSelector((state: RootState) => state.auth);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleClock = async (type: "in" | "out") => {
    if (!user) return;
    setLoading(true);
    try {
      const record = await attendanceApi.clockInOut({ type });
      dispatch(setRecords([record]));
      setError(null);
    } catch {
      setError(`Failed to clock ${type}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 md:p-6">
      {error && (
        <Alert variant="destructive">
          <AlertCircleIcon />
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <Card>
        <CardHeader>
          <CardTitle>Clock In/Out</CardTitle>
        </CardHeader>
        <CardContent className="flex gap-4">
          <Button onClick={() => handleClock("in")} disabled={loading}>
            Clock In
          </Button>
          <Button
            onClick={() => handleClock("out")}
            disabled={loading}
            variant="outline"
          >
            Clock Out
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

export default AttendanceClock;
