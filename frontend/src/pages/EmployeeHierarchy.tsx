import { useEffect, useState, useCallback } from "react";
import { useSelector, useDispatch } from "react-redux";
import type { RootState } from "@/store";
import { hierarchyApi } from "@/api/hierarchy";
import { usersApi } from "@/api/users";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircleIcon } from "lucide-react";
import { Tree } from "react-d3-tree";
import type { User, EmployeeHierarchy } from "@/api/types";
import { z } from "zod";
import GenericForm, {
  type FormFieldConfig,
} from "@/components/common/GenericForm";
import { Skeleton } from "@/components/ui/skeleton";
import { useCenteredTree } from "@/hooks/use-centered-tree";
import { setHierarchy } from "@/store/slices/hierarchySlice";

interface TreeNode {
  name: string;
  children?: TreeNode[];
  id?: number;
}

const assignSchema = z.object({
  employee_id: z.number().min(1, "Employee required"),
  manager_id: z.number().min(1, "Manager required"),
});

const removeSchema = z.object({
  employee_id: z.number().min(1, "Employee required"),
});

function EmployeeHierarchy() {
  const dispatch = useDispatch();
  const { user } = useSelector((state: RootState) => state.auth);
  const [hierarchy, setLocalHierarchy] = useState<EmployeeHierarchy[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [containerRef, translate, separation] = useCenteredTree();

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [hierData, usersData] = await Promise.all([
        hierarchyApi.getHierarchy(),
        usersApi.getUsers({}),
      ]);
      setLocalHierarchy(hierData);
      dispatch(setHierarchy(hierData));
      setUsers(usersData.items);
    } catch {
      setError("Failed to load hierarchy data");
    } finally {
      setLoading(false);
    }
  }, [dispatch]);

  useEffect(() => {
    if (
      user?.permissions.includes("view_team_attendance") ||
      user?.permissions.includes("manage_employees")
    ) {
      fetchData();
    }
  }, [user, fetchData]);

  const buildTreeData = (): TreeNode => {
    const tree: TreeNode = { name: "Organization", children: [] };
    const userMap = new Map(users.map((u) => [u.id, u]));
    const hierarchyMap = new Map<number, TreeNode[]>();

    hierarchy.forEach((h) => {
      if (!hierarchyMap.has(h.manager_id)) {
        hierarchyMap.set(h.manager_id, []);
      }
      hierarchyMap.get(h.manager_id)!.push({
        name: `${userMap.get(h.employee_id)?.first_name || "Unknown"} ${
          userMap.get(h.employee_id)?.last_name || ""
        }`,
        id: h.employee_id,
      });
    });

    const buildNode = (userId: number): TreeNode => {
      const usr = userMap.get(userId);
      const node: TreeNode = {
        name: `${usr?.first_name || "Unknown"} ${usr?.last_name || ""} (${
          usr?.email || ""
        })`,
        children: hierarchyMap.get(userId) || [],
        id: userId,
      };
      node.children = (node.children || []).map((child) =>
        child.id !== undefined ? buildNode(child.id) : { name: child.name }
      );
      return node;
    };

    // Find root nodes (no manager)
    users.forEach((u) => {
      if (!hierarchy.some((h) => h.employee_id === u.id)) {
        tree.children!.push(buildNode(u.id));
      }
    });

    return tree;
  };

  const handleAssign = async (data: z.infer<typeof assignSchema>) => {
    try {
      await hierarchyApi.assignManager({
        ...data,
        effective_from: new Date().toISOString().split("T")[0], // Add required effective_from
      });
      await fetchData(); // Refresh
    } catch {
      setError("Failed to assign manager");
    }
  };

  const handleRemove = async (data: z.infer<typeof removeSchema>) => {
    try {
      await hierarchyApi.removeManager(data.employee_id);
      await fetchData(); // Refresh
    } catch {
      setError("Failed to remove manager");
    }
  };

  const userOptions = users.map((u) => ({
    value: u.id.toString(),
    label: `${u.first_name} ${u.last_name} (${u.email})`,
  }));

  // Explicit typing fixes the TS error + transform to number
  const assignFields: FormFieldConfig<z.infer<typeof assignSchema>>[] = [
    {
      name: "employee_id",
      label: "Employee",
      type: "select",
      options: userOptions,
      transform: {
        fromInput: (v) => Number(v),
        toInput: (v) => String(v ?? ""),
      },
    },
    {
      name: "manager_id",
      label: "Manager",
      type: "select",
      options: userOptions,
      transform: {
        fromInput: (v) => Number(v),
        toInput: (v) => String(v ?? ""),
      },
    },
  ];

  const removeFields: FormFieldConfig<z.infer<typeof removeSchema>>[] = [
    {
      name: "employee_id",
      label: "Employee",
      type: "select",
      options: userOptions,
      transform: {
        fromInput: (v) => Number(v),
        toInput: (v) => String(v ?? ""),
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
      {loading ? (
        <Skeleton className="h-[500px] w-full" />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Employee Hierarchy</CardTitle>
          </CardHeader>
          <CardContent>
            <div ref={containerRef} className="w-full h-[500px]">
              <Tree
                data={buildTreeData()}
                orientation="vertical"
                translate={translate}
                separation={separation}
                pathFunc="step"
              />
            </div>
          </CardContent>
        </Card>
      )}
      <Card>
        <CardHeader>
          <CardTitle>Manage Hierarchy</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-6 md:grid-cols-2">
          <div>
            <h3 className="text-lg font-semibold mb-4">Assign Manager</h3>
            <GenericForm
              schema={assignSchema}
              defaultValues={{ employee_id: 0, manager_id: 0 }}
              fields={assignFields}
              onSubmit={handleAssign}
              submitButtonText="Assign"
            />
          </div>
          <div>
            <h3 className="text-lg font-semibold mb-4">Remove Manager</h3>
            <GenericForm
              schema={removeSchema}
              defaultValues={{ employee_id: 0 }}
              fields={removeFields}
              onSubmit={handleRemove}
              submitButtonText="Remove"
            />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default EmployeeHierarchy;
