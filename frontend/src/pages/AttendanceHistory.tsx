import { useEffect, useState, useCallback } from "react";
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
import type { AttendanceRecord, PaginatedResponse } from "@/api/types";

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

  const fetchHistory = useCallback(async () => {
    if (!user || !validateDates(startDate, endDate)) return;
    setLoading(true);
    setError(null);

    try {
      const response = await attendanceApi.getHistory({
        user_id: user.id,
        page,
        limit,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
      });

      // Handle both array and paginated response formats
      let data: PaginatedResponse<AttendanceRecord>;
      if (Array.isArray(response)) {
        data = {
          items: response,
          total: response.length,
          page,
          limit,
        };
      } else {
        data = response ?? {
          items: [],
          total: 0,
          page,
          limit,
        };
      }

      dispatch(setHistory(data));
    } catch (err) {
      console.error("Failed to fetch attendance history:", err);
      setError("Failed to load attendance history");
      dispatch(
        setHistory({
          items: [],
          total: 0,
          page,
          limit,
        })
      );
    } finally {
      setLoading(false);
    }
  }, [user, page, limit, startDate, endDate, dispatch]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const columns: ColumnDef<AttendanceRecord>[] = [
    {
      accessorKey: "date",
      header: "Date",
      cell: ({ row }) => format(new Date(row.getValue("date")), "MMM d, yyyy"),
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
      cell: ({ row }) => {
        const status = row.getValue("status") as string;
        return (
          <span
            className={`inline-flex items-center rounded-full px-2 py-1 text-xs font-medium ${
              status === "present"
                ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300"
                : status === "late"
                ? "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300"
                : "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300"
            }`}
          >
            {status?.toUpperCase()}
          </span>
        );
      },
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
      ) : !history || !history.items || history.items.length === 0 ? (
        <div className="text-center text-sm text-muted-foreground">
          No attendance records found
        </div>
      ) : (
        <>
          <GenericTable
            data={history.items || []}
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
                  disabled={history.total <= page * limit}
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
