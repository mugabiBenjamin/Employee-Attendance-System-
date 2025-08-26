import { useState, useEffect, useCallback } from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store";
import { attendanceApi } from "@/api/attendance";
import { z } from "zod";
import GenericForm, {
  type FormFieldConfig,
} from "@/components/common/GenericForm";
import type { AttendanceRecord } from "@/api/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircleIcon, CheckCircle2 } from "lucide-react";
import { format, parseISO } from "date-fns";
import { useInView } from "react-intersection-observer";
import { Skeleton } from "@/components/ui/skeleton";

const timeCorrectionSchema = z.object({
  attendance_record_id: z.number().min(1, "Select an attendance record"),
  corrected_clock_in: z.string().optional(),
  corrected_clock_out: z.string().optional(),
  reason: z.string().min(1, "Reason is required"),
});

type TimeCorrectionFormData = z.infer<typeof timeCorrectionSchema>;

function TimeCorrection() {
  const { user } = useSelector((state: RootState) => state.auth);
  const [records, setRecords] = useState<AttendanceRecord[]>([]);
  const [page, setPage] = useState(1);
  const [limit] = useState(20);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { ref, inView } = useInView({ threshold: 0 });

  const fetchRecords = useCallback(async () => {
    if (!user || !hasMore || loading) return;
    setLoading(true);
    try {
      const data = await attendanceApi.getHistory({
        user_id: user.id,
        page,
        limit,
      });
      setRecords((prev) => [...prev, ...data.items]);
      setHasMore(data.items.length === limit);
      setError(null);
    } catch {
      setError("Failed to load attendance records");
    } finally {
      setLoading(false);
    }
  }, [user, page, limit, hasMore, loading]);

  useEffect(() => {
    fetchRecords();
  }, [fetchRecords]);

  useEffect(() => {
    if (inView && hasMore && !loading) {
      setPage((prev) => prev + 1);
    }
  }, [inView, hasMore, loading]);

  const onSubmit = async (data: TimeCorrectionFormData) => {
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      await attendanceApi.requestTimeCorrection(data);
      setSuccess("Time correction request submitted successfully");
      setRecords([]); // Clear records to trigger reload
      setPage(1);
      setHasMore(true);
    } catch {
      setError("Failed to submit time correction");
    } finally {
      setLoading(false);
    }
  };

  const formatDateTime = (dateTime: string) => {
    if (!dateTime) return "";
    try {
      return format(parseISO(dateTime), "yyyy-MM-dd'T'HH:mm");
    } catch {
      return "";
    }
  };

  const fields: FormFieldConfig<TimeCorrectionFormData>[] = [
    {
      name: "attendance_record_id",
      label: "Attendance Record",
      type: "select",
      placeholder: "Select record",
      description: "Select the attendance record to correct",
      options: records.map((record) => ({
        value: record.attendance_id.toString(),
        label: `${format(new Date(record.created_at), "MMM d, yyyy")} - ${
          record.clock_in
            ? format(new Date(record.clock_in), "h:mm a")
            : "No clock in"
        }`,
      })),
    },
    {
      name: "corrected_clock_in",
      label: "Corrected Clock In",
      type: "datetime-local",
      placeholder: "Select time",
      description: "Corrected clock-in time (optional)",
      transform: {
        toInput: formatDateTime,
        fromInput: (value: string) =>
          value ? new Date(value).toISOString() : "",
      },
    },
    {
      name: "corrected_clock_out",
      label: "Corrected Clock Out",
      type: "datetime-local",
      placeholder: "Select time",
      description: "Corrected clock-out time (optional)",
      transform: {
        toInput: formatDateTime,
        fromInput: (value: string) =>
          value ? new Date(value).toISOString() : "",
      },
    },
    {
      name: "reason",
      label: "Reason",
      type: "text",
      placeholder: "Enter reason for correction",
      description: "Reason for requesting the correction",
    },
  ];

  const defaultValues: TimeCorrectionFormData = {
    attendance_record_id: 0,
    corrected_clock_in: "",
    corrected_clock_out: "",
    reason: "",
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
      {success && (
        <Alert variant="default" className="border-green-500">
          <CheckCircle2 className="h-4 w-4 text-green-500" />
          <AlertTitle>Success</AlertTitle>
          <AlertDescription>{success}</AlertDescription>
        </Alert>
      )}
      <Card>
        <CardHeader>
          <CardTitle>Request Time Correction</CardTitle>
        </CardHeader>
        <CardContent>
          <GenericForm<TimeCorrectionFormData>
            schema={timeCorrectionSchema}
            defaultValues={defaultValues}
            fields={fields}
            onSubmit={onSubmit}
            submitButtonText="Submit Correction"
            disabled={loading}
          />
        </CardContent>
      </Card>
      {loading && (
        <div className="space-y-2">
          {[...Array(3)].map((_, i) => (
            <Skeleton key={i} className="h-8 w-full" />
          ))}
        </div>
      )}
      <div ref={ref} className="h-4" />
    </div>
  );
}

export default TimeCorrection;
