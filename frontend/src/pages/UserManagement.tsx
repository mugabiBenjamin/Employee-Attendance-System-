import { useEffect, useState } from "react";
import { useSelector, useDispatch } from "react-redux";
import type { RootState } from "@/store";
import { usersApi } from "@/api/users";
import { departmentsApi } from "@/api/departments";
import { rolesApi } from "@/api/roles";
import { setUsers } from "@/store/slices/userSlice";
import type { ColumnDef } from "@tanstack/react-table";
import { z } from "zod";
import GenericTable from "@/components/common/GenericTable";
import GenericForm, {
  type FormFieldConfig,
} from "@/components/common/GenericForm";
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
import type { User, Department, Role, PaginatedResponse } from "@/api/types";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useEnums } from "@/hooks/useEnums";
import { toast } from "sonner";

const userSchema = z.object({
  email: z.string().email("Invalid email address").optional(),
  first_name: z.string().min(1, "First name is required"),
  last_name: z.string().min(1, "Last name is required"),
  password: z
    .string()
    .min(6, "Password must be at least 6 characters")
    .optional(),
  department_id: z.number().optional(),
  roles: z.array(z.number()).optional(),
});

type UserFormData = z.infer<typeof userSchema>;

function UserManagement() {
  const dispatch = useDispatch();
  const { user } = useSelector((state: RootState) => state.auth);
  const { users } = useSelector((state: RootState) => state.user);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [page, setPage] = useState(1);
  const [limit] = useState(10);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [editUser, setEditUser] = useState<User | null>(null);
  const { permissions } = useEnums();

  useEffect(() => {
    if (user?.permissions.includes("manage_users")) {
      setLoading(true);
      Promise.all([
        usersApi
          .getUsers({ page, limit })
          .then((data) => dispatch(setUsers(data))),
        departmentsApi
          .getDepartments({})
          .then((data) => setDepartments(data.items)),
        rolesApi
          .getRoles({})
          .then((data: PaginatedResponse<Role>) => setRoles(data.items)),
      ])
        .catch(() => setError("Failed to load data"))
        .finally(() => setLoading(false));
    }
  }, [user, page, limit, dispatch]);

  const handleSubmit = async (data: UserFormData, isEdit: boolean) => {
    try {
      let userId: number;
      if (isEdit && editUser) {
        await usersApi.updateUser(editUser.id, data);
        userId = editUser.id;
        toast("User Updated", {
          description: `User ${data.first_name} ${data.last_name} updated successfully.`,
          style: {
            background: "var(--green-100)",
            color: "var(--green-800)",
          },
          duration: 3000,
        });
      } else {
        const newUser = await usersApi.createUser(data);
        userId = newUser.id;
        toast("User Created", {
          description: `User ${data.first_name} ${data.last_name} created successfully.`,
          style: {
            background: "var(--green-100)",
            color: "var(--green-800)",
          },
          duration: 3000,
        });
      }

      if (data.roles) {
        for (const roleId of data.roles) {
          await usersApi.assignRole({ user_id: userId, role_id });
        }
      }

      const updatedUsers = await usersApi.getUsers({ page, limit });
      dispatch(setUsers(updatedUsers));
      setEditUser(null);
      setError(null);
    } catch {
      setError(`Failed to ${isEdit ? "update" : "create"} user`);
    }
  };

  const handleToggleStatus = async (user: User) => {
    try {
      await usersApi.updateUser(user.id, {
        is_active: !user.is_active,
      });
      const updatedUsers = await usersApi.getUsers({ page, limit });
      dispatch(setUsers(updatedUsers));
      toast(`User ${user.is_active ? "Deactivated" : "Activated"}`, {
        description: `User ${user.first_name} ${user.last_name} has been ${
          user.is_active ? "deactivated" : "activated"
        }.`,
        style: {
          background: "var(--green-100)",
          color: "var(--green-800)",
        },
        duration: 3000,
      });
    } catch {
      setError("Failed to update user status");
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
        <div className="flex gap-2">
          <DialogTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setEditUser(row.original)}
            >
              Edit
            </Button>
          </DialogTrigger>
          <Button
            variant="outline"
            size="sm"
            onClick={() => handleToggleStatus(row.original)}
          >
            {row.original.is_active ? "Deactivate" : "Activate"}
          </Button>
        </div>
      ),
    },
  ];

  const fields: FormFieldConfig<UserFormData>[] = [
    {
      name: "email",
      label: "Email",
      type: "email",
      placeholder: "Enter email",
    },
    {
      name: "first_name",
      label: "First Name",
      type: "text",
      placeholder: "Enter first name",
    },
    {
      name: "last_name",
      label: "Last Name",
      type: "text",
      placeholder: "Enter last name",
    },
    {
      name: "password",
      label: "Password",
      type: "password",
      placeholder: "Enter password",
      description: "Optional for updates",
    },
    {
      name: "department_id",
      label: "Department",
      type: "select",
      placeholder: "Select department",
      description: "Optional",
      options: departments.map((d) => ({
        value: d.department_id.toString(),
        label: d.name,
      })),
    },
    {
      name: "roles",
      label: "Roles",
      type: "select",
      placeholder: "Select roles",
      description: "Assign roles to the user",
      multiple: true,
      options: roles.map((r) => ({
        value: r.role_id.toString(),
        label: r.name,
      })),
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
              roles: [],
            }}
            fields={fields}
            onSubmit={(data) => handleSubmit(data, false)}
            submitButtonText="Create User"
          />
        </CardContent>
      </Card>
      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <>
          <Dialog>
            <GenericTable
              data={users?.items || []}
              columns={columns}
              filterColumn="email"
            />
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Edit User</DialogTitle>
              </DialogHeader>
              {editUser && (
                <GenericForm
                  schema={userSchema}
                  defaultValues={{
                    email: editUser.email,
                    first_name: editUser.first_name,
                    last_name: editUser.last_name,
                    password: "",
                    department_id: editUser.department_id,
                    roles: editUser.roles
                      .map(
                        (roleName) =>
                          roles.find((r) => r.name === roleName)?.role_id
                      )
                      .filter(Boolean) as number[],
                  }}
                  fields={fields}
                  onSubmit={(data) => handleSubmit(data, true)}
                  submitButtonText="Update User"
                />
              )}
            </DialogContent>
          </Dialog>
          <Pagination>
            <PaginationContent>
              <PaginationItem>
                <PaginationPrevious
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                />
              </PaginationItem>
              <PaginationItem>
                <PaginationNext
                  onClick={() => setPage((p) => p + 1)}
                  disabled={!users || (users?.total ?? 0) <= page * limit}
                />
              </PaginationItem>
            </PaginationContent>
          </Pagination>
        </>
      )}
    </div>
  );
}

export default UserManagement;
