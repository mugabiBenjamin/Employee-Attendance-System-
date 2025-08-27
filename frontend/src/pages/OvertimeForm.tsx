import { useState, useCallback } from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store";
import { overtimeApi } from "@/api/overtime";
import { z } from "zod";
import GenericForm, {
  type FormFieldConfig,
} from "@/components/common/GenericForm";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircleIcon, CheckCircle2 } from "lucide-react";
import { format, parseISO } from "date-fns";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import type { OvertimeRecord } from "@/api/types";

const overtimeSchema = z.object({
  date: z.string().min(1, "Date is required"),
  hours: z
    .number()
    .min(0.5, "Hours must be at least 0.5")
    .max(24, "Hours cannot exceed 24"),
  reason: z.string().min(1, "Reason is required"),
});

type OvertimeFormData = z.infer<typeof overtimeSchema>;

interface OvertimeFormProps {
  editRecord?: OvertimeRecord;
  onSuccess?: () => void;
}

function OvertimeForm({ editRecord, onSuccess }: OvertimeFormProps) {
  const { user } = useSelector((state: RootState) => state.auth);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onSubmit = useCallback(
    async (data: OvertimeFormData) => {
      if (!user) {
        setError("User not authenticated");
        return;
      }
      setLoading(true);
      setError(null);
      setSuccess(null);
      try {
        if (editRecord) {
          await overtimeApi.updateOvertimeRecord(editRecord.overtime_id, {
            ...data,
            user_id: user.id,
          });
          toast("Overtime Updated", {
            description: `Overtime record for ${format(
              new Date(data.date),
              "MMM d, yyyy"
            )} updated successfully.`,
            style: {
              background: "var(--green-100)",
              color: "var(--green-800)",
            },
            duration: 3000,
          });
        } else {
          await overtimeApi.createOvertimeRecord({
            ...data,
            user_id: user.id,
          });
          toast("Overtime Created", {
            description: `Overtime record for ${format(
              new Date(data.date),
              "MMM d, yyyy"
            )} created successfully.`,
            style: {
              background: "var(--green-100)",
              color: "var(--green-800)",
            },
            duration: 3000,
          });
        }
        setSuccess("Overtime request submitted successfully");
        if (onSuccess) onSuccess();
      } catch {
        setError(
          `Failed to ${editRecord ? "update" : "create"} overtime record`
        );
      } finally {
        setLoading(false);
      }
    },
    [user, editRecord, onSuccess]
  );

  const formatDate = (value: unknown): string => {
    if (!value || typeof value !== "string") return "";
    try {
      return format(parseISO(value), "yyyy-MM-dd");
    } catch {
      return "";
    }
  };

  const fields: FormFieldConfig<OvertimeFormData>[] = [
    {
      name: "date",
      label: "Date",
      type: "date",
      placeholder: "Select date",
      description: "Date of the overtime work",
      transform: {
        toInput: formatDate,
        fromInput: (value: string | string[]) =>
          typeof value === "string" && value
            ? new Date(value).toISOString()
            : "",
      },
    },
    {
      name: "hours",
      label: "Hours",
      type: "number",
      placeholder: "Enter hours",
      description: "Number of overtime hours (0.5 to 24)",
      transform: {
        toInput: (value: unknown) =>
          typeof value === "number" ? value.toString() : "",
        fromInput: (value: string | string[]) =>
          typeof value === "string" && value ? parseFloat(value) : 0,
      },
    },
    {
      name: "reason",
      label: "Reason",
      type: "text",
      placeholder: "Enter reason for overtime",
      description: "Reason for requesting overtime",
    },
  ];

  const defaultValues: OvertimeFormData = {
    date: editRecord ? formatDate(editRecord.date) : "",
    hours: editRecord?.hours || 1,
    reason: editRecord?.reason || "",
  };

  const formContent = (
    <Card>
      <CardHeader>
        <CardTitle>
          {editRecord ? "Edit Overtime Request" : "Request Overtime"}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <GenericForm<OvertimeFormData>
          schema={overtimeSchema}
          defaultValues={defaultValues}
          fields={fields}
          onSubmit={onSubmit}
          submitButtonText={editRecord ? "Update Request" : "Submit Request"}
          disabled={loading}
        />
      </CardContent>
    </Card>
  );

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
      {editRecord ? (
        <Dialog>
          <DialogTrigger asChild>
            <Button variant="outline">Edit Overtime Request</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Edit Overtime Request</DialogTitle>
            </DialogHeader>
            {formContent}
          </DialogContent>
        </Dialog>
      ) : (
        formContent
      )}
    </div>
  );
}

export default OvertimeForm;
