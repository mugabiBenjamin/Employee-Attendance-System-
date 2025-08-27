import { useEffect, useState, useCallback } from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store";
import { logsApi } from "@/api/logs";
import type { ColumnDef } from "@tanstack/react-table";
import { format } from "date-fns";
import GenericTable from "@/components/common/GenericTable";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircleIcon, Download } from "lucide-react";
import type { PaginatedResponse, SystemLog } from "@/api/types";
import { debounce } from "lodash";
import { saveAs } from "file-saver";
import { Skeleton } from "@/components/ui/skeleton";

function SystemLogs() {
  const { user } = useSelector((state: RootState) => state.auth);
  const [logs, setLogs] = useState<PaginatedResponse<SystemLog> | null>(null);
  const [page, setPage] = useState(1);
  const [limit] = useState(10);
  const [actionFilter, setActionFilter] = useState("");
  const [tableFilter, setTableFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  // Debounced filter update functions
  const debouncedSetActionFilter = debounce((value: string) => {
    setActionFilter(value);
    setPage(1); // Reset to first page on filter change
  }, 300);

  const debouncedSetTableFilter = debounce((value: string) => {
    setTableFilter(value);
    setPage(1); // Reset to first page on filter change
  }, 300);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await logsApi.getLogs({
        page,
        limit,
        action: actionFilter || undefined,
        table_name: tableFilter || undefined,
      });
      setLogs(data);
    } catch {
      setError("Failed to load system logs");
    } finally {
      setLoading(false);
    }
  }, [page, limit, actionFilter, tableFilter]);

  useEffect(() => {
    if (user?.permissions.includes("view_logs")) {
      fetchLogs();
    }
  }, [user, fetchLogs]);

  const handleExportCSV = async () => {
    try {
      const allLogs = await logsApi.getLogs({
        page: 1,
        limit: logs?.total || 1000, // Fetch all available logs
        action: actionFilter || undefined,
        table_name: tableFilter || undefined,
      });
      const csv = [
        "Date,User ID,Action,Table,Record ID",
        ...allLogs.items.map((log) =>
          [
            format(new Date(log.created_at), "MMM d, yyyy HH:mm"),
            log.user_id || "-",
            log.action,
            log.table_name,
            log.record_id || "-",
          ].join(",")
        ),
      ].join("\n");
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
      saveAs(blob, `system_logs_${format(new Date(), "yyyy-MM-dd")}.csv`);
    } catch {
      setError("Failed to export logs");
    }
  };

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
        <Input
          placeholder="Filter by action..."
          onChange={(e) => debouncedSetActionFilter(e.target.value)}
        />
        <Input
          placeholder="Filter by table..."
          onChange={(e) => debouncedSetTableFilter(e.target.value)}
        />
        <Button onClick={handleExportCSV} variant="outline">
          <Download className="h-4 w-4 mr-2" />
          Export CSV
        </Button>
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
            data={logs?.items || []}
            columns={columns}
            filterColumn="action"
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
                  disabled={!logs || (logs?.total ?? 0) <= page * limit}
                />
              </PaginationItem>
            </PaginationContent>
          </Pagination>
        </>
      )}
    </div>
  );
}

export default SystemLogs;
