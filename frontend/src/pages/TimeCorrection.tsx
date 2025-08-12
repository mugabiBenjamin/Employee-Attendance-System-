import { useState, useEffect } from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store";
import { attendanceApi } from "@/api/attendance";
import { z } from "zod";
import GenericForm from "@/components/common/GenericForm";
import type { AttendanceRecord } from "@/api/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircleIcon } from "lucide-react";

const timeCorrectionSchema = z.object({
  attendance_record_id: z.number().min(1, "Select an attendance record"),
  corrected_clock_in: z.string().optional(),
  corrected_clock_out: z.string().optional(),
  reason: z.string().min(1, "Reason is required"),
});

type TimeCorrectionForm = z.infer<typeof timeCorrectionSchema>;

function TimeCorrection() {
  const { user } = useSelector((state: RootState) => state.auth);
  const [records, setRecords] = useState<AttendanceRecord[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (user) {
      attendanceApi
        .getHistory({ user_id: user.id, limit: 10 })
        .then((data) => setRecords(data.items))
        .catch(() => setError("Failed to load attendance records"));
    }
  }, [user]);

  const onSubmit = async (data: TimeCorrectionForm) => {
    try {
      await attendanceApi.requestTimeCorrection(data);
      setError(null);
    } catch {
      setError("Failed to submit time correction");
    }
  };

  const fields = [
    {
      name: "attendance_record_id" as const,
      label: "Attendance Record",
      type: "select" as const,
      placeholder: "Select record",
      description: "Select the attendance record to correct",
      options: records.map((record) => ({
        value: record.id.toString(),
        label: `${record.date} - ${record.clock_in || "No clock in"}`,
      })),
    },
    {
      name: "corrected_clock_in" as const,
      label: "Corrected Clock In",
      type: "datetime-local" as const,
      placeholder: "Select time",
    },
    {
      name: "corrected_clock_out" as const,
      label: "Corrected Clock Out",
      type: "datetime-local" as const,
      placeholder: "Select time",
    },
    {
      name: "reason" as const,
      label: "Reason",
      type: "text" as const,
      placeholder: "Enter reason for correction",
    },
  ];

  const defaultValues: TimeCorrectionForm = {
    attendance_record_id: 0,
    corrected_clock_in: "",
    corrected_clock_out: "",
    reason: "",
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
          <CardTitle>Request Time Correction</CardTitle>
        </CardHeader>
        <CardContent>
          <GenericForm<TimeCorrectionForm>
            schema={timeCorrectionSchema}
            defaultValues={defaultValues}
            fields={fields}
            onSubmit={onSubmit}
            submitButtonText="Submit Correction"
          />
        </CardContent>
      </Card>
    </div>
  );
}

export default TimeCorrection;
