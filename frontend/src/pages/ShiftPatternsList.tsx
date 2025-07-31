import { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store";
import { shiftsApi } from "@/api/shifts";
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
import type { PaginatedResponse, ShiftPattern } from "@/api/types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircleIcon } from "lucide-react";

function ShiftPatternsList() {
  const navigate = useNavigate();
  const { user } = useSelector((state: RootState) => state.auth);
  const [shiftPatterns, setShiftPatterns] =
    useState<PaginatedResponse<ShiftPattern> | null>(null);
  const [page, setPage] = useState(1);
  const [limit] = useState(10);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (user?.permissions.includes("manage_employees")) {
      shiftsApi
        .getShiftPatterns({ page, limit })
        .then(setShiftPatterns)
        .catch(() => setError("Failed to load shift patterns"));
    }
  }, [user, page, limit]);

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
        <Button
          variant="outline"
          size="sm"
          onClick={() => navigate(`/shift-patterns/edit/${row.original.id}`)}
        >
          Edit
        </Button>
      ),
    },
  ];

  if (!user?.permissions.includes("manage_employees")) {
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
        onClick={() => navigate("/shift-patterns/edit")}
        className="self-start"
      >
        Add Shift Pattern
      </Button>
      <GenericTable
        data={shiftPatterns?.items || []}
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
              disabled={
                !shiftPatterns?.total || page * limit >= shiftPatterns.total
              }
            />
          </PaginationItem>
        </PaginationContent>
      </Pagination>
    </div>
  );
}

export default ShiftPatternsList;
