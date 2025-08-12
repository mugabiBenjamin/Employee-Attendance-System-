import { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store";
import { emergencyApi } from "@/api/emergency";
import { z } from "zod";
import { useParams, useNavigate, Navigate } from "react-router-dom";
import GenericForm from "@/components/common/GenericForm";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircleIcon } from "lucide-react";

const emergencyContactSchema = z.object({
  name: z.string().min(1, "Name is required"),
  relationship: z.string().min(1, "Relationship is required"),
  phone: z.string().min(1, "Phone is required"),
  email: z.string().email().optional(),
  address: z.string().optional(),
});

type EmergencyContactForm = z.infer<typeof emergencyContactSchema>;

function EmergencyContactForm() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useSelector((state: RootState) => state.auth);
  const [defaultValues, setDefaultValues] = useState<EmergencyContactForm>({
    name: "",
    relationship: "",
    phone: "",
    email: "",
    address: "",
  });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (id && user?.permissions.includes("manage_employees")) {
      emergencyApi.getEmergencyContacts({}).then((data) => {
        const contact = data.items.find((c) => c.id === parseInt(id));
        if (contact) {
          setDefaultValues({
            name: contact.name,
            relationship: contact.relationship,
            phone: contact.phone,
            email: contact.email || "",
            address: contact.address || "",
          });
        }
      });
    }
  }, [id, user]);

  const onSubmit = async (data: EmergencyContactForm) => {
    try {
      if (id) {
        await emergencyApi.updateEmergencyContact(parseInt(id), data);
      } else {
        await emergencyApi.createEmergencyContact(data);
      }
      navigate("/emergency-contacts");
    } catch {
      setError("Failed to save emergency contact");
    }
  };

  if (
    !user?.permissions.includes("view_own_attendance") &&
    !user?.permissions.includes("manage_employees")
  ) {
    return <Navigate to="/" replace />;
  }

  const fields = [
    {
      name: "name" as const,
      label: "Name",
      type: "text" as const,
      placeholder: "Enter name",
      description: "Contact name",
    },
    {
      name: "relationship" as const,
      label: "Relationship",
      type: "text" as const,
      placeholder: "Enter relationship",
      description: "Relationship to employee",
    },
    {
      name: "phone" as const,
      label: "Phone",
      type: "text" as const,
      placeholder: "Enter phone number",
      description: "Contact phone number",
    },
    {
      name: "email" as const,
      label: "Email",
      type: "email" as const,
      placeholder: "Enter email",
      description: "Optional contact email",
    },
    {
      name: "address" as const,
      label: "Address",
      type: "text" as const,
      placeholder: "Enter address",
      description: "Optional contact address",
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
            {id ? "Edit Emergency Contact" : "Add Emergency Contact"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <GenericForm<EmergencyContactForm>
            schema={emergencyContactSchema}
            defaultValues={defaultValues}
            fields={fields}
            onSubmit={onSubmit}
            submitButtonText={id ? "Update Contact" : "Create Contact"}
          />
        </CardContent>
      </Card>
    </div>
  );
}

export default EmergencyContactForm;
