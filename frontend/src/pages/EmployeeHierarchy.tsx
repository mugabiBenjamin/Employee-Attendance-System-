import { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store";
import { hierarchyApi } from "@/api/hierarchy";
import { usersApi } from "@/api/users";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircleIcon } from "lucide-react";
import { Tree } from "react-d3-tree";
import type { User, EmployeeHierarchy } from "@/api/types";
import { Navigate } from "react-router-dom";

interface TreeNode {
  name: string;
  children?: TreeNode[];
  id?: number;
}

function EmployeeHierarchy() {
  const { user } = useSelector((state: RootState) => state.auth);
  const [hierarchy, setHierarchy] = useState<EmployeeHierarchy[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (
      user?.permissions.includes("view_team_attendance") ||
      user?.permissions.includes("manage_employees")
    ) {
      Promise.all([
        hierarchyApi.getHierarchy().then(setHierarchy),
        usersApi.getUsers({}).then((data) => setUsers(data.items)),
      ]).catch(() => setError("Failed to load hierarchy data"));
    }
  }, [user]);

  if (
    !user?.permissions.includes("view_team_attendance") &&
    !user?.permissions.includes("manage_employees")
  ) {
    return <Navigate to="/" replace />;
  }

  const buildTreeData = (): TreeNode => {
    const tree: TreeNode = { name: "Organization", children: [] };
    const userMap = new Map(users.map((u) => [u.id, u]));
    const hierarchyMap = new Map<number, TreeNode[]>();

    hierarchy.forEach((h) => {
      if (!hierarchyMap.has(h.manager_id)) {
        hierarchyMap.set(h.manager_id, []);
      }
      hierarchyMap.get(h.manager_id)!.push({
        name: userMap.get(h.employee_id)?.email || "Unknown",
        id: h.employee_id,
      });
    });

    const buildNode = (userId: number): TreeNode => {
      const user = userMap.get(userId);
      const node: TreeNode = {
        name: user?.email || "Unknown",
        children: hierarchyMap.get(userId) || [],
      };
      node.children = (node.children || []).map((child) =>
        child.id !== undefined ? buildNode(child.id) : { name: child.name }
      );
      return node;
    };

    users.forEach((u) => {
      if (!hierarchy.some((h) => h.employee_id === u.id)) {
        tree.children!.push(buildNode(u.id));
      }
    });

    return tree;
  };

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 md:p-6">
      {error && (
        <Alert variant="destructive">
          <AlertCircleIcon />
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <Card>
        <CardHeader>
          <CardTitle>Employee Hierarchy</CardTitle>
        </CardHeader>
        <CardContent>
          <div style={{ height: "500px" }}>
            <Tree
              data={buildTreeData()}
              orientation="vertical"
              translate={{ x: 300, y: 50 }}
            />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default EmployeeHierarchy;
