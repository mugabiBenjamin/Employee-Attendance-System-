import { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store";
import { shiftsApi } from "@/api/shifts";
import { z } from "zod";
import { useParams, useNavigate } from "react-router-dom";
import GenericForm, {
  type FormFieldConfig,
} from "@/components/common/GenericForm";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircleIcon } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { useEnums } from "@/hooks/use-enums"; // Assume a hook for fetching enums

const shiftPatternSchema = z.object({
  name: z.string().min(1, "Name is required"),
  start_time: z.string().min(1, "Start time is required"),
  end_time: z.string().min(1, "End time is required"),
  days: z.array(z.string()).min(1, "At least one day is required"),
});

type ShiftPatternFormData = z.infer<typeof shiftPatternSchema>;

function ShiftPatternForm() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useSelector((state: RootState) => state.auth);
  const { enums } = useEnums(); // Fetch enums for days
  const [defaultValues, setDefaultValues] = useState<ShiftPatternFormData>({
    name: "",
    start_time: "",
    end_time: "",
    days: [],
  });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [fetchLoading, setFetchLoading] = useState<boolean>(false);

  useEffect(() => {
    if (id && user?.permissions.includes("manage_employees")) {
      setFetchLoading(true);
      shiftsApi
        .getShiftPatternById(parseInt(id))
        .then((shift) => {
          setDefaultValues({
            name: shift.name,
            start_time: shift.start_time,
            end_time: shift.end_time,
            days: shift.days,
          });
          setError(null);
        })
        .catch(() => {
          setError("Failed to load shift pattern data");
        })
        .finally(() => setFetchLoading(false));
    }
  }, [id, user]);

  const onSubmit = async (data: ShiftPatternFormData) => {
    setLoading(true);
    setError(null);
    try {
      if (id) {
        await shiftsApi.updateShiftPattern(parseInt(id), data);
      } else {
        await shiftsApi.createShiftPattern(data);
      }
      navigate("/shift-patterns");
    } catch {
      setError(`Failed to ${id ? "update" : "create"} shift pattern`);
    } finally {
      setLoading(false);
    }
  };

  const dayOptions = enums?.days?.map((day: string) => ({
    value: day,
    label: day,
  })) || [
    { value: "Monday", label: "Monday" },
    { value: "Tuesday", label: "Tuesday" },
    { value: "Wednesday", label: "Wednesday" },
    { value: "Thursday", label: "Thursday" },
    { value: "Friday", label: "Friday" },
    { value: "Saturday", label: "Saturday" },
    { value: "Sunday", label: "Sunday" },
  ];

  const fields: FormFieldConfig<ShiftPatternFormData>[] = [
    {
      name: "name",
      label: "Name",
      type: "text",
      placeholder: "Enter shift name",
      description: "Shift pattern name",
    },
    {
      name: "start_time",
      label: "Start Time",
      type: "time",
      placeholder: "Select start time",
      description: "Shift start time",
    },
    {
      name: "end_time",
      label: "End Time",
      type: "time",
      placeholder: "Select end time",
      description: "Shift end time",
    },
    {
      name: "days",
      label: "Days",
      type: "select",
      placeholder: "Select days",
      description: "Days the shift applies to",
      multiple: true,
      options: dayOptions,
    },
  ];

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
          <CardTitle>
            {id ? "Edit Shift Pattern" : "Add Shift Pattern"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {fetchLoading ? (
            <div className="space-y-4">
              {[...Array(4)].map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : (
            <GenericForm
              schema={shiftPatternSchema}
              defaultValues={defaultValues}
              fields={fields}
              onSubmit={onSubmit}
              submitButtonText={
                id ? "Update Shift Pattern" : "Create Shift Pattern"
              }
              disabled={loading}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default ShiftPatternForm;
