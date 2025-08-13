import { useEffect, useState } from "react";
import { useSelector, useDispatch } from "react-redux";
import type { RootState } from "@/store";
import { usersApi } from "@/api/users";
import { departmentsApi } from "@/api/departments";
import { setUsers } from "@/store/slices/userSlice";
import type { ColumnDef } from "@tanstack/react-table";
import { z } from "zod";
import GenericTable from "@/components/common/GenericTable";
import GenericForm from "@/components/common/GenericForm";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircleIcon } from "lucide-react";
import type { User, Department } from "@/api/types";
import { Navigate } from "react-router-dom";

const userSchema = z.object({
  email: z.string().email("Invalid email address"),
  first_name: z.string().min(1, "First name is required"),
  last_name: z.string().min(1, "Last name is required"),
  password: z
    .string()
    .min(6, "Password must be at least 6 characters")
    .optional(),
  department_id: z.number().optional(),
});

function UserManagement() {
  const dispatch = useDispatch();
  const { user, isAuthenticated } = useSelector(
    (state: RootState) => state.auth
  );
  const { users } = useSelector((state: RootState) => state.user);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [page, setPage] = useState(1);
  const [limit] = useState(10);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (user?.permissions.includes("manage_users")) {
      Promise.all([
        usersApi
          .getUsers({ page, limit })
          .then((data) => dispatch(setUsers(data))),
        departmentsApi
          .getDepartments({})
          .then((data) => setDepartments(data.items)),
      ]).catch(() => setError("Failed to load data"));
    }
  }, [user, page, limit, dispatch]);

  const onSubmit = async (data: z.infer<typeof userSchema>) => {
    try {
      await usersApi.createUser(data);
      const updatedUsers = await usersApi.getUsers({ page, limit });
      dispatch(setUsers(updatedUsers));
      setError(null);
    } catch {
      setError("Failed to create user");
    }
  };

  const columns: ColumnDef<User>[] = [
    { accessorKey: "email", header: "Email" },
    { accessorKey: "first_name", header: "First Name" },
    { accessorKey: "last_name", header: "Last Name" },
    {
      accessorKey: "is_active",
      header: "Status",
      cell: ({ row }) => (row.getValue("is_active") ? "Active" : "Inactive"),
    },
    {
      id: "actions",
      cell: ({ row }) => (
        <Button
          variant="outline"
          size="sm"
          onClick={async () => {
            try {
              await usersApi.updateUser(row.original.id, {
                is_active: !row.original.is_active,
              });
              const updatedUsers = await usersApi.getUsers({ page, limit });
              dispatch(setUsers(updatedUsers));
            } catch {
              setError("Failed to update user status");
            }
          }}
        >
          {row.original.is_active ? "Deactivate" : "Activate"}
        </Button>
      ),
    },
  ];

  const fields = [
  {
    name: "email" as const,
    label: "Email",
    type: "email" as const,
    placeholder: "Enter email",
  },
  {
    name: "first_name" as const,
    label: "First Name", 
    type: "text" as const,
    placeholder: "Enter first name",
  },
  {
    name: "last_name" as const,
    label: "Last Name",
    type: "text" as const, 
    placeholder: "Enter last name",
  },
  {
    name: "password" as const,
    label: "Password",
    type: "password" as const,
    placeholder: "Enter password",
    description: "Optional",
  },
  {
    name: "department_id" as const,
    label: "Department",
    type: "select" as const,
    placeholder: "Select department", 
    description: "Optional",
    options: departments.map((d) => ({
      value: d.department_id.toString(),
      label: d.name,
    })),
  },
];

  if (!isAuthenticated || !user?.permissions.includes("manage_users")) {
    return <Navigate to="/" replace />;
  }

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
          <CardTitle>Add New User</CardTitle>
        </CardHeader>
        <CardContent>
          <GenericForm
            schema={userSchema}
            defaultValues={{
              email: "",
              first_name: "",
              last_name: "",
              password: "",
              department_id: undefined,
            }}
            fields={fields}
            onSubmit={onSubmit}
            submitButtonText="Create User"
          />
        </CardContent>
      </Card>
      <GenericTable
        data={users?.items || []}
        columns={columns}
        filterColumn="email"
      />
      <Pagination>
        <PaginationContent>
          <PaginationItem>
            <PaginationPrevious
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            />
          </PaginationItem>
          <PaginationItem>
            <PaginationNext
              onClick={() => setPage((p) => p + 1)}
              disabled={!users?.total || page * limit >= users.total}
            />
          </PaginationItem>
        </PaginationContent>
      </Pagination>
    </div>
  );
}

export default UserManagement;
