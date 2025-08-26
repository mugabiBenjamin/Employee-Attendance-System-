import { useEffect, useState } from "react";
import { useSelector, useDispatch } from "react-redux";
import type { RootState } from "@/store";
import { leaveApi } from "@/api/leave";
import type { ColumnDef } from "@tanstack/react-table";
import { z } from "zod";
import GenericTable from "@/components/common/GenericTable";
import GenericForm, {
  type FormFieldConfig,
} from "@/components/common/GenericForm";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircleIcon } from "lucide-react";
import { toast } from "sonner";
import type { LeavePolicy } from "@/api/types";
import { useLeaveTypeOptions } from "@/hooks/useEnums";
import { Skeleton } from "@/components/ui/skeleton";

const leavePolicySchema = z.object({
  name: z.string().min(1, "Policy name is required"),
  description: z.string().optional(),
  leave_type: z.enum([
    "annual",
    "sick",
    "maternity",
    "paternity",
    "emergency",
    "unpaid",
    "casual",
    "compensatory",
    "bereavement",
    "leave_of_absence",
    "public_holiday",
  ]),
  max_days: z.number().min(1, "Maximum days must be at least 1"),
});

type LeavePolicyFormData = z.infer<typeof leavePolicySchema>;

function LeavePolicies() {
  const dispatch = useDispatch();
  const { user } = useSelector((state: RootState) => state.auth);
  const [policies, setPolicies] = useState<LeavePolicy[]>([]);
  const [page, setPage] = useState(1);
  const [limit] = useState(10);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [editPolicy, setEditPolicy] = useState<LeavePolicy | null>(null);
  const leaveTypeOptions = useLeaveTypeOptions();

  const fetchPolicies = async () => {
    if (!user?.permissions.includes("manage_leave_policies")) return;
    setLoading(true);
    try {
      const data = await leaveApi.getLeavePolicies({ page, limit });
      setPolicies(data.items);
      setError(null);
    } catch {
      setError("Failed to load leave policies");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPolicies();
  }, [user, page, limit]);

  const handleSubmit = async (data: LeavePolicyFormData, isEdit: boolean) => {
    try {
      if (isEdit && editPolicy) {
        await leaveApi.updateLeavePolicy(editPolicy.leave_policy_id, data);
        toast("Policy Updated", {
          description: `Leave policy ${data.name} updated successfully.`,
          style: {
            background: "var(--green-100)",
            color: "var(--green-800)",
          },
          duration: 3000,
        });
      } else {
        await leaveApi.createLeavePolicy(data);
        toast("Policy Created", {
          description: `Leave policy ${data.name} created successfully.`,
          style: {
            background: "var(--green-100)",
            color: "var(--green-800)",
          },
          duration: 3000,
        });
      }
      setEditPolicy(null);
      fetchPolicies();
    } catch {
      setError(`Failed to ${isEdit ? "update" : "create"} leave policy`);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await leaveApi.deleteLeavePolicy(id);
      toast("Policy Deleted", {
        description: "Leave policy deleted successfully.",
        style: {
          background: "var(--green-100)",
          color: "var(--green-800)",
        },
        duration: 3000,
      });
      fetchPolicies();
    } catch {
      setError("Failed to delete leave policy");
    }
  };

  const columns: ColumnDef<LeavePolicy>[] = [
    { accessorKey: "name", header: "Policy Name" },
    {
      accessorKey: "leave_type",
      header: "Leave Type",
      cell: ({ row }) =>
        row
          .getValue("leave_type")
          .replace(/_/g, " ")
          .replace(/\b\w/g, (l) => l.toUpperCase()),
    },
    {
      accessorKey: "max_days",
      header: "Max Days",
      cell: ({ row }) => `${row.getValue("max_days")} days`,
    },
    {
      id: "actions",
      header: "Actions",
      cell: ({ row }) => (
        <div className="flex gap-2">
          <DialogTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setEditPolicy(row.original)}
            >
              Edit
            </Button>
          </DialogTrigger>
          <Button
            variant="outline"
            size="sm"
            onClick={() => handleDelete(row.original.leave_policy_id)}
          >
            Delete
          </Button>
        </div>
      ),
    },
  ];

  const fields: FormFieldConfig<LeavePolicyFormData>[] = [
    {
      name: "name",
      label: "Policy Name",
      type: "text",
      placeholder: "Enter policy name",
      description: "Name of the leave policy",
    },
    {
      name: "leave_type",
      label: "Leave Type",
      type: "select",
      placeholder: "Select leave type",
      description: "Type of leave for this policy",
      options: leaveTypeOptions,
    },
    {
      name: "max_days",
      label: "Maximum Days",
      type: "number",
      placeholder: "Enter maximum days",
      description: "Maximum days allowed for this leave type",
    },
    {
      name: "description",
      label: "Description",
      type: "text",
      placeholder: "Enter description (optional)",
      description: "Optional description of the policy",
    },
  ];

  const defaultValues: LeavePolicyFormData = {
    name: "",
    leave_type: "annual",
    max_days: 1,
    description: "",
  };

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
          <CardTitle>Add New Leave Policy</CardTitle>
        </CardHeader>
        <CardContent>
          <GenericForm
            schema={leavePolicySchema}
            defaultValues={defaultValues}
            fields={fields}
            onSubmit={(data) => handleSubmit(data, false)}
            submitButtonText="Create Policy"
          />
        </CardContent>
      </Card>
      {loading ? (
        <div className="space-y-2">
          {[...Array(5)].map((_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : (
        <>
          <Dialog>
            <GenericTable
              data={policies}
              columns={columns}
              filterColumn="name"
            />
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Edit Leave Policy</DialogTitle>
              </DialogHeader>
              {editPolicy && (
                <GenericForm
                  schema={leavePolicySchema}
                  defaultValues={{
                    name: editPolicy.name,
                    leave_type: editPolicy.leave_type,
                    max_days: editPolicy.max_days,
                    description: editPolicy.description || "",
                  }}
                  fields={fields}
                  onSubmit={(data) => handleSubmit(data, true)}
                  submitButtonText="Update Policy"
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
                  disabled={policies.length < limit}
                />
              </PaginationItem>
            </PaginationContent>
          </Pagination>
        </>
      )}
    </div>
  );
}

export default LeavePolicies;
