import { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store";
import { emergencyApi } from "@/api/emergency";
import type { ColumnDef } from "@tanstack/react-table";
import { Navigate, useNavigate } from "react-router-dom";
import GenericTable from "@/components/common/GenericTable";
import { Button } from "@/components/ui/button";
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";
import type { EmergencyContact, PaginatedResponse } from "@/api/types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircleIcon } from "lucide-react";

function EmergencyContactsList() {
  const navigate = useNavigate();
  const { user } = useSelector((state: RootState) => state.auth);
  const [contacts, setContacts] =
    useState<PaginatedResponse<EmergencyContact> | null>(null);
  const [page, setPage] = useState(1);
  const [limit] = useState(10);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (user) {
      emergencyApi
        .getEmergencyContacts({
          user_id: user.permissions.includes("manage_employees")
            ? undefined
            : user.id,
          page,
          limit,
        })
        .then(setContacts)
        .catch(() => setError("Failed to load emergency contacts"));
    }
  }, [user, page, limit]);

  const columns: ColumnDef<EmergencyContact>[] = [
    {
      accessorKey: "name",
      header: "Name",
    },
    {
      accessorKey: "relationship",
      header: "Relationship",
    },
    {
      accessorKey: "phone",
      header: "Phone",
    },
    {
      accessorKey: "email",
      header: "Email",
      cell: ({ row }) => row.getValue("email") || "-",
    },
    {
      id: "actions",
      cell: ({ row }) => (
        <Button
          variant="outline"
          size="sm"
          onClick={() =>
            navigate(`/emergency-contacts/edit/${row.original.id}`)
          }
        >
          Edit
        </Button>
      ),
    },
  ];

  if (
    !user?.permissions.includes("view_own_attendance") &&
    !user?.permissions.includes("manage_employees")
  ) {
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
      <Button
        onClick={() => navigate("/emergency-contacts/edit")}
        className="self-start"
      >
        Add Emergency Contact
      </Button>
      <GenericTable
        data={contacts?.items || []}
        columns={columns}
        filterColumn="name"
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
              disabled={!contacts?.total || page * limit >= contacts.total}
            />
          </PaginationItem>
        </PaginationContent>
      </Pagination>
    </div>
  );
}

export default EmergencyContactsList;
