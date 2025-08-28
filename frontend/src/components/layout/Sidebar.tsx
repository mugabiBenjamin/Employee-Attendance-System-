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
  enumsApi.getPermissions().then(allPermissions => {
    console.log("All Available Permissions:", allPermissions);
  });
}, [user]);

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
    ...(user?.permissions?.includes("manage_departments")
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
    ...(user?.permissions?.includes("manage_employees")
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
    ...(user?.permissions?.includes("view_own_attendance") ||
    user?.permissions?.includes("manage_overtime")
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
    ...(user?.permissions?.includes("request_leave") ||
    user?.permissions?.includes("manage_employees") ||
    user?.permissions?.includes("manage_leave_policies")
      ? [
          {
            title: "Leaves",
            url: "/leave-request",
            icon: Calendar,
            items: [
              ...(user?.permissions?.includes("request_leave")
                ? [{ title: "Request Leave", url: "/leave-request" }]
                : []),
              ...(user?.permissions?.includes("manage_employees") ||
              user?.permissions?.includes("manage_leave_policies")
                ? [{ title: "Leave Requests", url: "/leave-requests" }]
                : []),
              ...(user?.permissions?.includes("view_own_attendance") ||
              user?.permissions?.includes("manage_employees")
                ? [{ title: "Leave Balances", url: "/leave-balances" }]
                : []),
              ...(user?.permissions?.includes("manage_leave_policies")
                ? [{ title: "Leave Policies", url: "/leave-policies" }]
                : []),
            ],
          },
        ]
      : []),
    ...(user?.permissions?.includes("view_logs")
      ? [
          {
            title: "System Logs",
            url: "/system-logs",
            icon: Settings,
          },
        ]
      : []),
    ...(user?.permissions?.includes("manage_users")
      ? [
          {
            title: "User Management",
            url: "/user-management",
            icon: UserCog,
          },
        ]
      : []),
  ].filter(Boolean); // Remove any undefined/null entries

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
