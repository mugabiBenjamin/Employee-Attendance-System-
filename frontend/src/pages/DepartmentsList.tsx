import { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store";
import { departmentsApi } from "@/api/departments";
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
import type { Department, PaginatedResponse } from "@/api/types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircleIcon } from "lucide-react";

function DepartmentsList() {
  const navigate = useNavigate();
  const { user } = useSelector((state: RootState) => state.auth);
  const [departments, setDepartments] =
    useState<PaginatedResponse<Department> | null>(null);
  const [page, setPage] = useState(1);
  const [limit] = useState(10);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (user?.permissions.includes("manage_departments")) {
      departmentsApi
        .getDepartments({ page, limit })
        .then(setDepartments)
        .catch(() => setError("Failed to load departments"));
    }
  }, [user, page, limit]);

  const columns: ColumnDef<Department>[] = [
    {
      accessorKey: "name",
      header: "Name",
    },
    {
      accessorKey: "description",
      header: "Description",
      cell: ({ row }) => row.getValue("description") || "-",
    },
    {
      id: "actions",
      cell: ({ row }) => (
        <Button
          variant="outline"
          size="sm"
          onClick={() => navigate(`/departments/edit/${row.original.department_id}`)}
        >
          Edit
        </Button>
      ),
    },
  ];

  if (!user?.permissions.includes("manage_departments")) {
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
        onClick={() => navigate("/departments/edit")}
        className="self-start"
      >
        Add Department
      </Button>
      <GenericTable
        data={departments?.items || []}
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
                !departments?.total || page * limit >= departments.total
              }
            />
          </PaginationItem>
        </PaginationContent>
      </Pagination>
    </div>
  );
}

export default DepartmentsList;
