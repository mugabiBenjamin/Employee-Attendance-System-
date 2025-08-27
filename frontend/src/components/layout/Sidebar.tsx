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

function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const user = useSelector((state: RootState) => state.auth.user);

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
    ...(user?.permissions.includes("manage_departments")
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
    ...(user?.permissions.includes("manage_employees")
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
          },
        ]
      : []),
    ...(user?.permissions.includes("view_own_attendance") ||
    user?.permissions.includes("manage_overtime")
      ? [
          {
            title: "Overtime Records",
            url: "/overtime-records",
            icon: FileClock,
          },
        ]
      : []),
    ...(user?.permissions.includes("request_leave")
      ? [
          {
            title: "Leave Request",
            url: "/leave-request",
            icon: Calendar,
          },
        ]
      : []),
    ...(user?.permissions.includes("view_own_attendance") ||
    user?.permissions.includes("manage_employees")
      ? [
          {
            title: "Leave Balances",
            url: "/leave-balances",
            icon: FileText,
          },
        ]
      : []),
    ...(user?.permissions.includes("manage_leave_policies")
      ? [
          {
            title: "Leave Policies",
            url: "/leave-policies",
            icon: FileText,
          },
        ]
      : []),
    ...(user?.permissions.includes("view_logs")
      ? [
          {
            title: "System Logs",
            url: "/system-logs",
            icon: Settings,
          },
        ]
      : []),
    ...(user?.permissions.includes("manage_users")
      ? [
          {
            title: "User Management",
            url: "/user-management",
            icon: UserCog,
          },
        ]
      : []),
  ];

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
            name: user?.first_name || "",
            email: user?.email || "",
            avatar: "",
          }}
        />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}

export default AppSidebar;