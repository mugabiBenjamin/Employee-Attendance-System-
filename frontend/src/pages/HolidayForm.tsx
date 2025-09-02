import { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store";
import { holidaysApi } from "@/api/holidays";
import { z } from "zod";
import { useParams, useNavigate } from "react-router-dom";
import GenericForm, {
  type FormFieldConfig,
} from "@/components/common/GenericForm";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircleIcon } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { format } from "date-fns";
import type { Holiday, PaginatedResponse, HolidayQuery } from "@/api/types";

const holidaySchema = z.object({
  name: z.string().min(1, "Name is required"),
  date: z.string().min(1, "Date is required"),
  description: z.string().optional(),
});

type HolidayFormData = z.infer<typeof holidaySchema>;

function HolidayForm() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useSelector((state: RootState) => state.auth);
  const [defaultValues, setDefaultValues] = useState<HolidayFormData>({
    name: "",
    date: "",
    description: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [fetchLoading, setFetchLoading] = useState<boolean>(false);

  useEffect(() => {
    if (id && user?.permissions.includes("manage_employees")) {
      setFetchLoading(true);
      holidaysApi
        .getHolidays({ id: parseInt(id) } as HolidayQuery) // Use HolidayQuery, assuming it's defined
        .then((response: PaginatedResponse<Holiday>) => {
          const holiday = response.items[0];
          if (!holiday) {
            throw new Error("Holiday not found");
          }
          setDefaultValues({
            name: holiday.name,
            date: format(new Date(holiday.date), "yyyy-MM-dd"),
            description: holiday.description || "",
          });
          setError(null);
        })
        .catch(() => {
          setError("Failed to load holiday data");
        })
        .finally(() => setFetchLoading(false));
    }
  }, [id, user]);

  const onSubmit = async (data: HolidayFormData) => {
    setLoading(true);
    setError(null);
    try {
      if (id) {
        await holidaysApi.updateHoliday(parseInt(id), data);
      } else {
        await holidaysApi.createHoliday(data);
      }
      navigate("/holidays");
    } catch {
      setError(`Failed to ${id ? "update" : "create"} holiday`);
    } finally {
      setLoading(false);
    }
  };

  const fields: FormFieldConfig<HolidayFormData>[] = [
    {
      name: "name",
      label: "Holiday Name",
      type: "text",
      placeholder: "Enter holiday name",
      description: "The name of the holiday",
    },
    {
      name: "date",
      label: "Date",
      type: "date",
      placeholder: "Select date",
      description: "The date of the holiday",
    },
    {
      name: "description",
      label: "Description",
      type: "text",
      placeholder: "Enter description",
      description: "Optional description of the holiday",
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
          <CardTitle>{id ? "Edit Holiday" : "Add Holiday"}</CardTitle>
        </CardHeader>
        <CardContent>
          {fetchLoading ? (
            <div className="space-y-4">
              {[...Array(3)].map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : (
            <GenericForm
              schema={holidaySchema}
              defaultValues={defaultValues}
              fields={fields}
              onSubmit={onSubmit}
              submitButtonText={id ? "Update Holiday" : "Create Holiday"}
              disabled={loading}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default HolidayForm;
