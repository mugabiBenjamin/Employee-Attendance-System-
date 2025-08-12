import { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store";
import { shiftsApi } from "@/api/shifts";
import { z } from "zod";
import { useParams, useNavigate, Navigate } from "react-router-dom";
import GenericForm from "@/components/common/GenericForm";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircleIcon } from "lucide-react";

const shiftPatternSchema = z.object({
  name: z.string().min(1, "Name is required"),
  start_time: z.string().min(1, "Start time is required"),
  end_time: z.string().min(1, "End time is required"),
  days: z.array(z.string()).min(1, "At least one day is required"),
});

function ShiftPatternForm() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useSelector((state: RootState) => state.auth);
  const [defaultValues, setDefaultValues] = useState({
    name: "",
    start_time: "",
    end_time: "",
    days: [] as string[],
  });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (id && user?.permissions.includes("manage_employees")) {
      shiftsApi.getShiftPatterns({}).then((data) => {
        const shift = data.items.find((s) => s.id === parseInt(id));
        if (shift) {
          setDefaultValues({
            name: shift.name,
            start_time: shift.start_time,
            end_time: shift.end_time,
            days: shift.days,
          });
        }
      });
    }
  }, [id, user]);

  const onSubmit = async (data: z.infer<typeof shiftPatternSchema>) => {
    try {
      if (id) {
        await shiftsApi.updateShiftPattern(parseInt(id), data);
      } else {
        await shiftsApi.createShiftPattern(data);
      }
      navigate("/shift-patterns");
    } catch {
      setError("Failed to save shift pattern");
    }
  };

  if (!user?.permissions.includes("manage_employees")) {
    return <Navigate to="/" replace />;
  }

  const fields = [
    {
      name: "name" as const,
      label: "Name",
      type: "text" as const,
      placeholder: "Enter shift name",
      description: "Shift pattern name",
    },
    {
      name: "start_time" as const,
      label: "Start Time",
      type: "time" as const,
      placeholder: "Select start time",
      description: "Shift start time",
    },
    {
      name: "end_time" as const,
      label: "End Time",
      type: "time" as const,
      placeholder: "Select end time",
      description: "Shift end time",
    },
    {
      name: "days" as const,
      label: "Days",
      type: "select" as const,
      placeholder: "Select days",
      description: "Days the shift applies to",
      multiple: true,
      options: [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
      ].map((day) => ({
        value: day,
        label: day,
      })),
    },
  ];

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
          <CardTitle>
            {id ? "Edit Shift Pattern" : "Add Shift Pattern"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <GenericForm
            schema={shiftPatternSchema}
            defaultValues={defaultValues}
            fields={fields}
            onSubmit={onSubmit}
            submitButtonText={
              id ? "Update Shift Pattern" : "Create Shift Pattern"
            }
          />
        </CardContent>
      </Card>
    </div>
  );
}

export default ShiftPatternForm;
