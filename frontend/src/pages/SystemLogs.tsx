import { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store";
import { logsApi } from "@/api/logs";
import type { ColumnDef } from "@tanstack/react-table";
import { format } from "date-fns";
import GenericTable from "@/components/common/GenericTable";
import { Input } from "@/components/ui/input";
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircleIcon } from "lucide-react";
import type { PaginatedResponse, SystemLog } from "@/api/types";
import { Navigate } from "react-router-dom";

function SystemLogs() {
  const { user } = useSelector((state: RootState) => state.auth);
  const [logs, setLogs] = useState<PaginatedResponse<SystemLog> | null>(null);
  const [page, setPage] = useState(1);
  const [limit] = useState(10);
  const [actionFilter, setActionFilter] = useState("");
  const [tableFilter, setTableFilter] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (user?.permissions.includes("view_logs")) {
      logsApi
        .getLogs({ page, limit, action: actionFilter, table_name: tableFilter })
        .then(setLogs)
        .catch(() => setError("Failed to load system logs"));
    }
  }, [user, page, limit, actionFilter, tableFilter]);

  const columns: ColumnDef<SystemLog>[] = [
    {
      accessorKey: "created_at",
      header: "Date",
      cell: ({ row }) =>
        format(new Date(row.getValue("created_at")), "MMM d, yyyy HH:mm"),
    },
    {
      accessorKey: "user_id",
      header: "User ID",
      cell: ({ row }) => row.getValue("user_id") || "-",
    },
    {
      accessorKey: "action",
      header: "Action",
    },
    {
      accessorKey: "table_name",
      header: "Table",
    },
    {
      accessorKey: "record_id",
      header: "Record ID",
      cell: ({ row }) => row.getValue("record_id") || "-",
    },
  ];

  if (!user?.permissions.includes("view_logs")) {
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
      <div className="flex gap-4">
        <Input
          placeholder="Filter by action..."
          value={actionFilter}
          onChange={(e) => setActionFilter(e.target.value)}
        />
        <Input
          placeholder="Filter by table..."
          value={tableFilter}
          onChange={(e) => setTableFilter(e.target.value)}
        />
      </div>
      <GenericTable
        data={logs?.items || []}
        columns={columns}
        filterColumn="action"
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
              disabled={!logs?.total || page * limit >= logs.total}
            />
          </PaginationItem>
        </PaginationContent>
      </Pagination>
    </div>
  );
}

export default SystemLogs;
