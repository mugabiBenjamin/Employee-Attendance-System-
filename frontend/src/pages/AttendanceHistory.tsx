import { useEffect, useState } from "react";
import { useSelector, useDispatch } from "react-redux";
import type { RootState } from "@/store";
import { attendanceApi } from "@/api/attendance";
import { setHistory } from "@/store/slices/attendanceSlice";
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
import { AlertCircleIcon } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import type { AttendanceRecord } from "@/api/types";

// Zod schema for date validation
const dateSchema = z
  .string()
  .refine((val) => !val || isValid(new Date(val)), {
    message: "Invalid date format",
  })
  .optional();

function AttendanceHistory() {
  const dispatch = useDispatch();
  const { user } = useSelector((state: RootState) => state.auth);
  const { history } = useSelector((state: RootState) => state.attendance);
  const [page, setPage] = useState(1);
  const [limit] = useState(10);
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
      const errors = err instanceof z.ZodError ? err.issues : [];
      const newErrors: { start?: string; end?: string } = {};
      errors.forEach((e) => {
        if (e.path[0] === "startDate") newErrors.start = e.message;
        if (e.path[0] === "endDate") newErrors.end = e.message;
      });
      setDateError(newErrors);
      return false;
    }
  };

  useEffect(() => {
    if (user && validateDates(startDate, endDate)) {
      setLoading(true);
      attendanceApi
        .getHistory({
          user_id: user.id,
          page,
          limit,
          start_date: startDate || undefined,
          end_date: endDate || undefined,
        })
        .then((data) => {
          dispatch(setHistory(data));
          setError(null);
        })
        .catch(() => {
          setError("Failed to load attendance history");
        })
        .finally(() => setLoading(false));
    }
  }, [user, page, startDate, endDate, limit, dispatch]);

  const columns: ColumnDef<AttendanceRecord>[] = [
    {
      accessorKey: "created_at",
      header: "Date",
      cell: ({ row }) =>
        format(new Date(row.getValue("created_at")), "MMM d, yyyy"),
    },
    {
      accessorKey: "clock_in",
      header: "Clock In",
      cell: ({ row }) => format(new Date(row.getValue("clock_in")), "h:mm a"),
    },
    {
      accessorKey: "clock_out",
      header: "Clock Out",
      cell: ({ row }) =>
        row.getValue("clock_out")
          ? format(new Date(row.getValue("clock_out")), "h:mm a")
          : "-",
    },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => (
        <span
          className={`inline-flex items-center rounded-full px-2 py-1 text-xs font-medium ${
            row.getValue("status") === "present"
              ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300"
              : row.getValue("status") === "late"
              ? "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300"
              : "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300"
          }`}
        >
          {row.getValue("status")}
        </span>
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
            onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
              setStartDate(e.target.value)
            }
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
            onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
              setEndDate(e.target.value)
            }
            className={dateError.end ? "border-destructive" : ""}
          />
          {dateError.end && (
            <p className="text-sm text-destructive mt-1">{dateError.end}</p>
          )}
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
            data={history?.items || []}
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
                  disabled={!history || (history?.total ?? 0) <= page * limit}
                />
              </PaginationItem>
            </PaginationContent>
          </Pagination>
        </>
      )}
    </div>
  );
}

export default AttendanceHistory;
