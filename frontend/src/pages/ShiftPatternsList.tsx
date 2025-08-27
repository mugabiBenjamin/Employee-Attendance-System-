import { useEffect, useState, useCallback } from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store";
import { shiftsApi } from "@/api/shifts";
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
import type { PaginatedResponse, ShiftPattern } from "@/api/types";
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

function ShiftPatternsList() {
  const navigate = useNavigate();
  const { user } = useSelector((state: RootState) => state.auth);
  const [shiftPatterns, setShiftPatterns] =
    useState<PaginatedResponse<ShiftPattern> | null>(null);
  const [page, setPage] = useState(1);
  const [limit] = useState(10);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [search, setSearch] = useState<string>("");

  const fetchShiftPatterns = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await shiftsApi.getShiftPatterns({ page, limit });
      setShiftPatterns(data);
    } catch {
      setError("Failed to load shift patterns");
    } finally {
      setLoading(false);
    }
  }, [page, limit]);

  useEffect(() => {
    if (user?.permissions.includes("manage_employees")) {
      fetchShiftPatterns();
    }
  }, [user, page, limit, fetchShiftPatterns]);

  const handleDelete = async () => {
    if (!deleteId) return;
    try {
      await shiftsApi.deleteShiftPattern(deleteId);
      await fetchShiftPatterns();
      setDeleteId(null);
    } catch {
      setError("Failed to delete shift pattern");
    }
  };

  const columns: ColumnDef<ShiftPattern>[] = [
    {
      accessorKey: "name",
      header: "Name",
    },
    {
      accessorKey: "start_time",
      header: "Start Time",
    },
    {
      accessorKey: "end_time",
      header: "End Time",
    },
    {
      accessorKey: "days",
      header: "Days",
      cell: ({ row }) => (row.getValue("days") as string[]).join(", "),
    },
    {
      id: "actions",
      cell: ({ row }) => (
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              navigate(`/shift-patterns/edit/${row.original.shift_pattern_id}`)
            }
          >
            Edit
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={() => setDeleteId(row.original.shift_pattern_id)}
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
          onClick={() => navigate("/shift-patterns/edit")}
          className="self-start"
        >
          Add Shift Pattern
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
      ) : (
        <>
          <GenericTable
            data={shiftPatterns?.items || []}
            columns={columns}
            filterColumn="name"
            globalFilter={search}
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
                  disabled={
                    !shiftPatterns ||
                    (shiftPatterns?.total ?? 0) <= page * limit
                  }
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
              Are you sure you want to delete this shift pattern? This action
              cannot be undone.
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

export default ShiftPatternsList;
