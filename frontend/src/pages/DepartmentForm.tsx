import { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store";
import { departmentsApi } from "@/api/departments";
import { z } from "zod";
import { useParams, useNavigate } from "react-router-dom";
import GenericForm, {
  type FormFieldConfig,
} from "@/components/common/GenericForm";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircleIcon } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import type { Department } from "@/api/types";

const departmentSchema = z.object({
  name: z.string().min(1, "Name is required"),
  description: z.string().optional(),
});

type DepartmentFormData = z.infer<typeof departmentSchema>;

function DepartmentForm() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useSelector((state: RootState) => state.auth);
  const [defaultValues, setDefaultValues] = useState<DepartmentFormData>({
    name: "",
    description: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [fetchLoading, setFetchLoading] = useState<boolean>(false);

  useEffect(() => {
    if (id && user?.permissions.includes("manage_departments")) {
      setFetchLoading(true);
      // Note: The backend API does not support direct ID filtering. Consider adding a `getDepartmentById` endpoint for efficiency.
      departmentsApi
        .getDepartments({ page: 1, limit: 100 }) // Fetch a reasonable number of departments
        .then((response) => {
          const department = response.items.find(
            (d: Department) => d.department_id === parseInt(id)
          );
          if (!department) {
            throw new Error("Department not found");
          }
          setDefaultValues({
            name: department.name,
            description: department.description || "",
          });
          setError(null);
        })
        .catch(() => {
          setError("Failed to load department data");
        })
        .finally(() => setFetchLoading(false));
    }
  }, [id, user]);

  const onSubmit = async (data: DepartmentFormData) => {
    setLoading(true);
    setError(null);
    try {
      if (id) {
        await departmentsApi.updateDepartment(parseInt(id), data);
      } else {
        await departmentsApi.createDepartment(data);
      }
      navigate("/departments");
    } catch {
      setError(`Failed to ${id ? "update" : "create"} department`);
    } finally {
      setLoading(false);
    }
  };

  const fields: FormFieldConfig<DepartmentFormData>[] = [
    {
      name: "name",
      label: "Department Name",
      type: "text",
      placeholder: "Enter department name",
      description: "The name of the department",
    },
    {
      name: "description",
      label: "Description",
      type: "text",
      placeholder: "Enter description",
      description: "Optional description of the department",
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
          <CardTitle>{id ? "Edit Department" : "Add Department"}</CardTitle>
        </CardHeader>
        <CardContent>
          {fetchLoading ? (
            <div className="space-y-4">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-12 w-32" />
            </div>
          ) : (
            <GenericForm
              schema={departmentSchema}
              defaultValues={defaultValues}
              fields={fields}
              onSubmit={onSubmit}
              submitButtonText={id ? "Update Department" : "Create Department"}
              disabled={loading}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default DepartmentForm;
