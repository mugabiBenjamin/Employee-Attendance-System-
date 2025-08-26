import { useState } from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store";
import { leaveApi } from "@/api/leave";
import { z } from "zod";
import GenericForm, {
  type FormFieldConfig,
} from "@/components/common/GenericForm";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircleIcon, CheckCircle2 } from "lucide-react";
import { format, parseISO } from "date-fns";
import { useLeaveTypeOptions } from "@/hooks/useEnums";

const leaveRequestSchema = z.object({
  start_date: z.string().min(1, "Start date is required"),
  end_date: z
    .string()
    .min(1, "End date is required")
    .refine(
      (endDate, ctx) => {
        const start = new Date(ctx.parent.start_date);
        const end = new Date(endDate);
        return end >= start;
      },
      { message: "End date must be after start date" }
    ),
  leave_type: z.enum([
    "annual",
    "sick",
    "maternity",
    "paternity",
    "emergency",
    "unpaid",
    "casual",
    "compensatory",
    "bereavement",
    "leave_of_absence",
    "public_holiday",
  ]),
  reason: z.string().min(1, "Reason is required"),
});

type LeaveRequestFormData = z.infer<typeof leaveRequestSchema>;

function LeaveRequestForm() {
  const { user } = useSelector((state: RootState) => state.auth);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const leaveTypeOptions = useLeaveTypeOptions();

  const onSubmit = async (data: LeaveRequestFormData) => {
    if (!user) {
      setError("User not authenticated");
      return;
    }
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      await leaveApi.createLeaveRequest({
        ...data,
        user_id: user.id,
      });
      setSuccess("Leave request submitted successfully");
    } catch {
      setError("Failed to submit leave request");
    } finally {
      setLoading(false);
    }
  };

  const formatDateTime = (dateTime: string) => {
    if (!dateTime) return "";
    try {
      return format(parseISO(dateTime), "yyyy-MM-dd");
    } catch {
      return "";
    }
  };

  const fields: FormFieldConfig<LeaveRequestFormData>[] = [
    {
      name: "start_date",
      label: "Start Date",
      type: "date",
      placeholder: "Select start date",
      description: "Start date of the leave",
      transform: {
        toInput: formatDateTime,
        fromInput: (value: string) =>
          value ? new Date(value).toISOString() : "",
      },
    },
    {
      name: "end_date",
      label: "End Date",
      type: "date",
      placeholder: "Select end date",
      description: "End date of the leave",
      transform: {
        toInput: formatDateTime,
        fromInput: (value: string) =>
          value ? new Date(value).toISOString() : "",
      },
    },
    {
      name: "leave_type",
      label: "Leave Type",
      type: "select",
      placeholder: "Select leave type",
      description: "Type of leave requested",
      options: leaveTypeOptions,
    },
    {
      name: "reason",
      label: "Reason",
      type: "text",
      placeholder: "Enter reason for leave",
      description: "Reason for requesting the leave",
    },
  ];

  const defaultValues: LeaveRequestFormData = {
    start_date: "",
    end_date: "",
    leave_type: "annual",
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
          <CardTitle>Request Leave</CardTitle>
        </CardHeader>
        <CardContent>
          <GenericForm<LeaveRequestFormData>
            schema={leaveRequestSchema}
            defaultValues={defaultValues}
            fields={fields}
            onSubmit={onSubmit}
            submitButtonText="Submit Leave Request"
            disabled={loading}
          />
        </CardContent>
      </Card>
    </div>
  );
}

export default LeaveRequestForm;
