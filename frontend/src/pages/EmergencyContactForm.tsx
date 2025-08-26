import { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store";
import { emergencyApi } from "@/api/emergency";
import { z } from "zod";
import { useParams, useNavigate } from "react-router-dom";
import GenericForm, {
  type FormFieldConfig,
} from "@/components/common/GenericForm";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircleIcon } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import type { EmergencyContact } from "@/api/types";

const emergencyContactSchema = z.object({
  user_id: z.number().min(1, "User ID is required"),
  name: z.string().min(1, "Name is required"),
  relationship: z.string().min(1, "Relationship is required"),
  phone: z.string().min(1, "Phone is required"),
  email: z.string().email("Invalid email").optional(),
  address: z.string().optional(),
});

type EmergencyContactFormData = z.infer<typeof emergencyContactSchema>;

function EmergencyContactForm() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useSelector((state: RootState) => state.auth);
  const [defaultValues, setDefaultValues] = useState<EmergencyContactFormData>({
    user_id: user?.id || 0,
    name: "",
    relationship: "",
    phone: "",
    email: "",
    address: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [fetchLoading, setFetchLoading] = useState<boolean>(false);

  useEffect(() => {
    if (id && user?.permissions.includes("manage_employees")) {
      setFetchLoading(true);
      emergencyApi
        .getEmergencyContactById(parseInt(id))
        .then((contact: EmergencyContact) => {
          setDefaultValues({
            user_id: contact.user_id,
            name: contact.name,
            relationship: contact.relationship,
            phone: contact.phone,
            email: contact.email || "",
            address: contact.address || "",
          });
          setError(null);
        })
        .catch(() => {
          setError("Failed to load emergency contact data");
        })
        .finally(() => setFetchLoading(false));
    } else if (user) {
      setDefaultValues((prev) => ({ ...prev, user_id: user.id }));
    }
  }, [id, user]);

  const onSubmit = async (data: EmergencyContactFormData) => {
    setLoading(true);
    setError(null);
    try {
      if (id) {
        await emergencyApi.updateEmergencyContact(parseInt(id), data);
      } else {
        await emergencyApi.createEmergencyContact(data);
      }
      navigate("/emergency-contacts");
    } catch {
      setError(`Failed to ${id ? "update" : "create"} emergency contact`);
    } finally {
      setLoading(false);
    }
  };

  const fields: FormFieldConfig<EmergencyContactFormData>[] = [
    {
      name: "user_id",
      label: "User ID",
      type: "number",
      placeholder: "Enter user ID",
      description: "The ID of the employee this contact is for",
      disabled: !user?.permissions.includes("manage_employees"),
    },
    {
      name: "name",
      label: "Name",
      type: "text",
      placeholder: "Enter name",
      description: "Contact name",
    },
    {
      name: "relationship",
      label: "Relationship",
      type: "text",
      placeholder: "Enter relationship",
      description: "Relationship to employee",
    },
    {
      name: "phone",
      label: "Phone",
      type: "text",
      placeholder: "Enter phone number",
      description: "Contact phone number",
    },
    {
      name: "email",
      label: "Email",
      type: "email",
      placeholder: "Enter email",
      description: "Optional contact email",
    },
    {
      name: "address",
      label: "Address",
      type: "text",
      placeholder: "Enter address",
      description: "Optional contact address",
    },
  ];

  if (
    !user?.permissions.includes("view_own_attendance") &&
    !user?.permissions.includes("manage_employees")
  ) {
    return null; // ProtectedRoute handles navigation
  }

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
            {id ? "Edit Emergency Contact" : "Add Emergency Contact"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {fetchLoading ? (
            <div className="space-y-4">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : (
            <GenericForm<EmergencyContactFormData>
              schema={emergencyContactSchema}
              defaultValues={defaultValues}
              fields={fields}
              onSubmit={onSubmit}
              submitButtonText={id ? "Update Contact" : "Create Contact"}
              disabled={loading}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default EmergencyContactForm;
