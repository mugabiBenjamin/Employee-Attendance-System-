import { useEffect, useState, useCallback } from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store";
import { leaveApi } from "@/api/leave";
import type { ColumnDef } from "@tanstack/react-table";
import GenericTable from "@/components/common/GenericTable";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";
import { AlertCircleIcon } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import type { LeaveBalance } from "@/api/types";

function LeaveBalances() {
  const { user } = useSelector((state: RootState) => state.auth);
  const [leaveBalances, setLeaveBalances] = useState<LeaveBalance[]>([]);
  const [page, setPage] = useState(1);
  const [limit] = useState(10);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  const fetchLeaveBalances = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    setError(null);
    try {
      const data = await leaveApi.getLeaveBalances({
        user_id: user.permissions.includes("manage_employees")
          ? undefined
          : user.id,
        page,
        limit,
      });
      setLeaveBalances(data.items);
    } catch {
      setError("Failed to load leave balances");
    } finally {
      setLoading(false);
    }
  }, [user, page, limit]);

  useEffect(() => {
    fetchLeaveBalances();
  }, [fetchLeaveBalances]);

  const columns: ColumnDef<LeaveBalance>[] = [
    {
      accessorKey: "user_id",
      header: "User ID",
      cell: ({ row }) => (row.getValue("user_id") as number) || "-",
    },
    {
      accessorKey: "leave_type",
      header: "Leave Type",
      cell: ({ row }) =>
        (row.getValue("leave_type") as string)
          .replace(/_/g, " ")
          .replace(/\b\w/g, (l: string) => l.toUpperCase()),
    },
    {
      accessorKey: "balance",
      header: "Remaining Balance",
      cell: ({ row }) => `${row.getValue("balance") as number} days`,
    },
    {
      accessorKey: "used",
      header: "Used",
      cell: ({ row }) => `${row.getValue("used") as number} days`,
    },
  ];

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 md:p-6">
      {error && (
        <Alert variant="destructive">
          <AlertCircleIcon className="h-4 w-4" />
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>
            {error}
            <Button
              variant="outline"
              size="sm"
              className="ml-4"
              onClick={fetchLeaveBalances}
            >
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      )}
      <Card>
        <CardHeader>
          <CardTitle>Leave Balances</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-2">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : (
            <>
              <GenericTable
                data={leaveBalances}
                columns={columns}
                filterColumn="leave_type"
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
                      disabled={leaveBalances.length < limit}
                    />
                  </PaginationItem>
                </PaginationContent>
              </Pagination>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default LeaveBalances;
