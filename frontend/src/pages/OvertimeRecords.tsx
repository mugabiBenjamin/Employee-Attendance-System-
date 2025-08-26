import { useEffect, useState } from "react";
import { useSelector, useDispatch } from "react-redux";
import type { RootState } from "@/store";
import { overtimeApi } from "@/api/overtime";
import type { ColumnDef } from "@tanstack/react-table";
import { format, isValid } from "date-fns";
import { z } from "zod";
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
import { Button } from "@/components/ui/button";
import { AlertCircleIcon, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import type { OvertimeRecord, OvertimeStatus } from "@/api/types";
import { Skeleton } from "@/components/ui/skeleton";

const dateSchema = z
  .string()
  .refine((val) => !val || isValid(new Date(val)), {
    message: "Invalid date format",
  })
  .optional();

function OvertimeRecords() {
  const dispatch = useDispatch();
  const { user } = useSelector((state: RootState) => state.auth);
  const [overtimeRecords, setOvertimeRecords] = useState<OvertimeRecord[]>([]);
  const [page, setPage] = useState(1);
  const [limit] = useState(10);
  const [statusFilter, setStatusFilter] = useState<OvertimeStatus | "">("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dateError, setDateError] = useState<{ start?: string; end?: string }>(
    {}
  );

  const validateDates = (start: string, end: string) => {
    setDateError({});
    try {
      dateSchema.parse(start);
      dateSchema.parse(end);
      if (start && end && new Date(start) > new Date(end)) {
        setDateError({ end: "End date must be after start date" });
        return false;
      }
      return true;
    } catch (err) {
      const errors = err instanceof z.ZodError ? err.errors : [];
      const newErrors: { start?: string; end?: string } = {};
      errors.forEach((e) => {
        if (e.path[0] === "startDate") newErrors.start = e.message;
        if (e.path[0] === "endDate") newErrors.end = e.message;
      });
      setDateError(newErrors);
      return false;
    }
  };

  const fetchOvertimeRecords = async () => {
    if (!user || !validateDates(startDate, endDate)) return;
    setLoading(true);
    try {
      const data = await overtimeApi.getOvertimeRecords({
        user_id: user.permissions.includes("manage_employees")
          ? undefined
          : user.id,
        page,
        limit,
        status: statusFilter || undefined,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
      });
      setOvertimeRecords(data.items);
      setError(null);
    } catch {
      setError("Failed to load overtime records");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOvertimeRecords();
  }, [user, page, statusFilter, startDate, endDate, limit]);

  const handleApprove = async (record: OvertimeRecord) => {
    try {
      await overtimeApi.updateOvertimeRecord(record.overtime_id, {
        status: "approved",
      });
      toast("Overtime Approved", {
        description: `Overtime request for ${format(
          new Date(record.date),
          "MMM d, yyyy"
        )} approved.`,
        style: {
          background: "var(--green-100)",
          color: "var(--green-800)",
        },
        duration: 3000,
      });
      fetchOvertimeRecords();
    } catch {
      setError("Failed to approve overtime record");
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await overtimeApi.deleteOvertimeRecord(id);
      toast("Overtime Deleted", {
        description: "Overtime record deleted successfully.",
        style: {
          background: "var(--green-100)",
          color: "var(--green-800)",
        },
        duration: 3000,
      });
      fetchOvertimeRecords();
    } catch {
      setError("Failed to delete overtime record");
    }
  };

  const columns: ColumnDef<OvertimeRecord>[] = [
    {
      accessorKey: "user_id",
      header: "User ID",
      cell: ({ row }) => row.getValue("user_id") || "-",
    },
    {
      accessorKey: "date",
      header: "Date",
      cell: ({ row }) => format(new Date(row.getValue("date")), "MMM d, yyyy"),
    },
    {
      accessorKey: "hours",
      header: "Hours",
      cell: ({ row }) => `${row.getValue("hours")} hours`,
    },
    {
      accessorKey: "reason",
      header: "Reason",
    },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => (
        <span
          className={`inline-flex items-center rounded-full px-2 py-1 text-xs font-medium ${
            row.getValue("status") === "approved"
              ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300"
              : row.getValue("status") === "pending"
              ? "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300"
              : "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300"
          }`}
        >
          {row.getValue("status")}
        </span>
      ),
    },
    {
      id: "actions",
      header: "Actions",
      cell: ({ row }) => (
        <div className="flex gap-2">
          {row.original.status === "pending" &&
            user?.permissions.includes("approve_overtime") && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleApprove(row.original)}
              >
                <CheckCircle2 className="h-4 w-4 mr-2" />
                Approve
              </Button>
            )}
          <Button
            variant="outline"
            size="sm"
            onClick={() => handleDelete(row.original.overtime_id)}
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
        <div className="flex-1">
          <Input
            type="date"
            placeholder="Start Date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className={dateError.start ? "border-destructive" : ""}
          />
          {dateError.start && (
            <p className="text-sm text-destructive mt-1">{dateError.start}</p>
          )}
        </div>
        <div className="flex-1">
          <Input
            type="date"
            placeholder="End Date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className={dateError.end ? "border-destructive" : ""}
          />
          {dateError.end && (
            <p className="text-sm text-destructive mt-1">{dateError.end}</p>
          )}
        </div>
        <div className="flex-1">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as OvertimeStatus)}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          >
            <option value="">All Statuses</option>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
          </select>
        </div>
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
            data={overtimeRecords}
            columns={columns}
            filterColumn="status"
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
                  disabled={overtimeRecords.length < limit}
                />
              </PaginationItem>
            </PaginationContent>
          </Pagination>
        </>
      )}
    </div>
  );
}

export default OvertimeRecords;
