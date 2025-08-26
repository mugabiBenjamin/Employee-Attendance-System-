import { useState } from "react";
import { useSelector, useDispatch } from "react-redux";
import type { RootState } from "@/store";
import { attendanceApi } from "@/api/attendance";
import { setRecords } from "@/store/slices/attendanceSlice";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircleIcon, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";

function AttendanceClock() {
  const dispatch = useDispatch();
  const { user } = useSelector((state: RootState) => state.auth);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  const handleClock = async (type: "in" | "out") => {
    if (!user) {
      setError("User not authenticated");
      return;
    }
    setLoading(true);
    try {
      const record = await attendanceApi.clockInOut({ type });
      dispatch(setRecords([record]));
      setError(null);
      toast(`Clock ${type} Successful`, {
        description: `You have successfully clocked ${type} at ${new Date().toLocaleTimeString()}.`,
        style: {
          background: "var(--green-100)",
          color: "var(--green-800)",
        },
        duration: 3000,
      });
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
          <AlertCircleIcon className="h-4 w-4" />
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <Card>
        <CardHeader>
          <CardTitle>Clock In/Out</CardTitle>
        </CardHeader>
        <CardContent className="flex gap-4">
          <Button
            onClick={() => handleClock("in")}
            disabled={loading}
            className="relative"
          >
            {loading && type === "in" ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <CheckCircle2 className="mr-2 h-4 w-4" />
            )}
            Clock In
          </Button>
          <Button
            onClick={() => handleClock("out")}
            disabled={loading}
            variant="outline"
            className="relative"
          >
            {loading && type === "out" ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <CheckCircle2 className="mr-2 h-4 w-4" />
            )}
            Clock Out
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

export default AttendanceClock;
