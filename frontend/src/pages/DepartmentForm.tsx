import { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store";
import { departmentsApi } from "@/api/departments";
import { z } from "zod";
import { useParams, useNavigate, Navigate } from "react-router-dom";
import GenericForm, { type FormFieldConfig } from "@/components/common/GenericForm";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircleIcon } from "lucide-react";

const departmentSchema = z.object({
  name: z.string().min(1, "Name is required"),
  description: z.string().optional(),
});

function DepartmentForm() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useSelector((state: RootState) => state.auth);
  const [defaultValues, setDefaultValues] = useState({
    name: "",
    description: "",
  });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (id && user?.permissions.includes("manage_departments")) {
      departmentsApi.getDepartments({}).then((data) => {
        const department = data.items.find((d) => d.id === parseInt(id));
        if (department) {
          setDefaultValues({
            name: department.name,
            description: department.description || "",
          });
        }
      });
    }
  }, [id, user]);

  const onSubmit = async (data: z.infer<typeof departmentSchema>) => {
    try {
      if (id) {
        await departmentsApi.updateDepartment(parseInt(id), data);
      } else {
        await departmentsApi.createDepartment(data);
      }
      navigate("/departments");
    } catch {
      setError("Failed to save department");
    }
  };

  if (!user?.permissions.includes("manage_departments")) {
    return <Navigate to="/" replace />;
  }

  const fields: FormFieldConfig<z.infer<typeof departmentSchema>>[] = [
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
          <AlertCircleIcon />
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <Card>
        <CardHeader>
          <CardTitle>{id ? "Edit Department" : "Add Department"}</CardTitle>
        </CardHeader>
        <CardContent>
          <GenericForm
            schema={departmentSchema}
            defaultValues={defaultValues}
            fields={fields}
            onSubmit={onSubmit}
            submitButtonText={id ? "Update Department" : "Create Department"}
          />
        </CardContent>
      </Card>
    </div>
  );
}

export default DepartmentForm;
