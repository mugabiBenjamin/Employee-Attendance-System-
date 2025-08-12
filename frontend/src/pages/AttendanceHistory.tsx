import { useEffect, useState } from "react";
import { useSelector, useDispatch } from "react-redux";
import type { RootState } from "@/store";
import { attendanceApi } from "@/api/attendance";
import { setHistory } from "@/store/slices/attendanceSlice";
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
import type { AttendanceRecord } from "@/api/types";

function AttendanceHistory() {
  const dispatch = useDispatch();
  const { user } = useSelector((state: RootState) => state.auth);
  const { history } = useSelector((state: RootState) => state.attendance);
  const [page, setPage] = useState(1);
  const [limit] = useState(10);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  useEffect(() => {
    if (user) {
      attendanceApi
        .getHistory({
          user_id: user.id,
          page,
          limit,
          start_date: startDate,
          end_date: endDate,
        })
        .then((data) => dispatch(setHistory(data)))
        .catch(() => {});
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
    },
  ];

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 md:p-6">
      <div className="flex gap-4">
        <Input
          type="date"
          placeholder="Start Date"
          value={startDate}
          onChange={(e) => setStartDate(e.target.value)}
        />
        <Input
          type="date"
          placeholder="End Date"
          value={endDate}
          onChange={(e) => setEndDate(e.target.value)}
        />
      </div>
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
            />
          </PaginationItem>
          <PaginationItem>
            <PaginationNext
              onClick={() => setPage((p) => p + 1)}
              disabled={!history?.total || page * limit >= history.total}
            />
          </PaginationItem>
        </PaginationContent>
      </Pagination>
    </div>
  );
}

export default AttendanceHistory;
