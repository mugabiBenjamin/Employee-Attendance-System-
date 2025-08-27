import { useEffect, useState, useCallback } from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store";
import { emergencyApi } from "@/api/emergency";
import type { ColumnDef } from "@tanstack/react-table";
import { useNavigate } from "react-router-dom";
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
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";

function EmergencyContactsList() {
  const navigate = useNavigate();
  const { user } = useSelector((state: RootState) => state.auth);
  const [contacts, setContacts] =
    useState<PaginatedResponse<EmergencyContact> | null>(null);
  const [page, setPage] = useState(1);
  const [limit] = useState(10);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [search, setSearch] = useState<string>("");

  const fetchContacts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await emergencyApi.getEmergencyContacts({
        user_id: user?.permissions.includes("manage_employees")
          ? undefined
          : user?.id,
        page,
        limit,
        search,
      });
      setContacts(data);
    } catch {
      setError("Failed to load emergency contacts");
    } finally {
      setLoading(false);
    }
  }, [user, page, limit, search]);

  useEffect(() => {
    if (user) {
      fetchContacts();
    }
  }, [user, fetchContacts]);

  const handleDelete = async () => {
    if (!deleteId) return;
    try {
      await emergencyApi.deleteEmergencyContact(deleteId);
      await fetchContacts();
      setDeleteId(null);
    } catch {
      setError("Failed to delete emergency contact");
    }
  };

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
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              navigate(
                `/emergency-contacts/edit/${row.original.emergency_contact_id}`
              )
            }
          >
            Edit
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={() => setDeleteId(row.original.emergency_contact_id)}
          >
            Delete
          </Button>
        </div>
      ),
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
      <div className="flex gap-4">
        <Button
          onClick={() => navigate("/emergency-contacts/edit")}
          className="self-start"
        >
          Add Emergency Contact
        </Button>
        <Input
          placeholder="Search by name..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
      </div>
      {loading ? (
        <div className="space-y-2">
          {[...Array(5)].map((_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : contacts?.items.length === 0 ? (
        <div className="text-center text-sm text-muted-foreground">
          No emergency contacts found
        </div>
      ) : (
        <>
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
                  disabled={page === 1}
                />
              </PaginationItem>
              <PaginationItem>
                <PaginationNext
                  onClick={() => setPage((p) => p + 1)}
                  disabled={!contacts || (contacts?.total ?? 0) <= page * limit}
                />
              </PaginationItem>
            </PaginationContent>
          </Pagination>
        </>
      )}
      <AlertDialog open={!!deleteId} onOpenChange={() => setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Confirm Deletion</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete this emergency contact? This
              action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

export default EmergencyContactsList;
