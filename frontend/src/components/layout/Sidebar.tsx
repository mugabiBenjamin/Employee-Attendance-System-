import * as React from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store";
import { NavMain } from "@/components/nav-main";
import { NavUser } from "@/components/nav-user";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarRail,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import {
  Briefcase,
  Calendar,
  Users,
  Clock,
  FileText,
  Settings,
  UserCog,
  GalleryVerticalEnd,
  FileClock,
  CalendarCheck,
} from "lucide-react";
import { enumsApi } from "@/api/enums";

function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const user = useSelector((state: RootState) => state.auth.user);

  // Log user and permissions for debugging
  React.useEffect(() => {
    console.log("User:", user);
    console.log("User Permissions:", user?.permissions || []);

    // Fetch all available permissions for comparison
    enumsApi.getPermissions().then((allPermissions) => {
      console.log("All Available Permissions:", allPermissions);
    });
  }, [user]);

  // Helper function to check if user has permission or all_permissions
  const hasPermission = (requiredPermission: string): boolean => {
    const hasAllPermissions =
      user?.permissions?.includes("all_permissions") || false;
    const hasSpecificPermission =
      user?.permissions?.includes(requiredPermission) || false;
    const result = hasAllPermissions || hasSpecificPermission;
    console.log(
      `Checking permission '${requiredPermission}': ${
        result ? "Granted" : "Denied"
      } (all_permissions: ${hasAllPermissions}, specific: ${hasSpecificPermission})`
    );
    return result;
  };

  const navItems = [
    {
      title: "Dashboard",
      url: "/",
      icon: Briefcase,
      isActive: true,
    },
    {
      title: "Attendance",
      url: "/attendance/clock",
      icon: Clock,
      items: [
        { title: "Clock In/Out", url: "/attendance/clock" },
        { title: "History", url: "/attendance/history" },
        { title: "Time Correction", url: "/attendance/time-correction" },
        { title: "Summary", url: "/attendance/summary" },
      ],
    },
    ...(hasPermission("manage_departments")
      ? [
          {
            title: "Departments",
            url: "/departments",
            icon: Users,
            items: [
              { title: "List", url: "/departments" },
              { title: "Add/Edit", url: "/departments/edit" },
            ],
          },
        ]
      : []),
    ...(hasPermission("manage_employees")
      ? [
          {
            title: "Emergency Contacts",
            url: "/emergency-contacts",
            icon: FileText,
            items: [
              { title: "List", url: "/emergency-contacts" },
              { title: "Add/Edit", url: "/emergency-contacts/edit" },
            ],
          },
          {
            title: "Shift Patterns",
            url: "/shift-patterns",
            icon: Calendar,
            items: [
              { title: "List", url: "/shift-patterns" },
              { title: "Add/Edit", url: "/shift-patterns/edit" },
            ],
          },
          {
            title: "Employee Hierarchy",
            url: "/employee-hierarchy",
            icon: Users,
          },
          {
            title: "Holidays",
            url: "/holidays",
            icon: CalendarCheck,
            items: [
              { title: "List", url: "/holidays" },
              { title: "Add/Edit", url: "/holidays/edit" },
            ],
          },
        ]
      : []),
    ...(hasPermission("view_own_attendance") || hasPermission("manage_overtime")
      ? [
          {
            title: "Overtime",
            url: "/overtime-records",
            icon: FileClock,
            items: [
              { title: "Records", url: "/overtime-records" },
              { title: "Add/Edit", url: "/overtime-records/edit" },
            ],
          },
        ]
      : []),
    ...(hasPermission("request_leave") ||
    hasPermission("manage_employees") ||
    hasPermission("manage_leave_policies")
      ? [
          {
            title: "Leaves",
            url: "/leave-request",
            icon: Calendar,
            items: [
              ...(hasPermission("request_leave")
                ? [{ title: "Request Leave", url: "/leave-request" }]
                : []),
              ...(hasPermission("manage_employees") ||
              hasPermission("manage_leave_policies")
                ? [{ title: "Leave Requests", url: "/leave-requests" }]
                : []),
              ...(hasPermission("view_own_attendance") ||
              hasPermission("manage_employees")
                ? [{ title: "Leave Balances", url: "/leave-balances" }]
                : []),
              ...(hasPermission("manage_leave_policies")
                ? [{ title: "Leave Policies", url: "/leave-policies" }]
                : []),
            ],
          },
        ]
      : []),
    ...(hasPermission("view_logs")
      ? [
          {
            title: "System Logs",
            url: "/system-logs",
            icon: Settings,
          },
        ]
      : []),
    ...(hasPermission("manage_users")
      ? [
          {
            title: "User Management",
            url: "/user-management",
            icon: UserCog,
          },
        ]
      : []),
  ].filter(Boolean); // Remove any undefined/null entries

  // Log navItems for debugging
  React.useEffect(() => {
    console.log(
      "Rendered navItems:",
      navItems.map((item) => item.title)
    );
  }, [navItems]);

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild className="my-2">
              <a href="/">
                <div className="bg-sidebar-primary text-sidebar-primary-foreground flex aspect-square size-8 items-center justify-center rounded-lg">
                  <GalleryVerticalEnd className="size-4 dark:text-foreground" />
                </div>
                <div className="flex flex-col gap-0.5 leading-none">
                  <span className="font-medium">EMS</span>
                  <span className="">v1.0.0</span>
                </div>
              </a>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={navItems} />
      </SidebarContent>
      <SidebarFooter>
        <NavUser
          user={{
            name: user?.first_name || "Guest",
            email: user?.email || "N/A",
            avatar: "",
          }}
        />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}

export default AppSidebar;
