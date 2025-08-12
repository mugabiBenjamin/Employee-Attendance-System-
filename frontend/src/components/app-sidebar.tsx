import * as React from "react";
import { Link, useLocation } from "react-router-dom";
import {
  Clock,
  Users,
  Building2,
  Phone,
  Calendar,
  Settings,
  BarChart3,
  GalleryVerticalEnd,
} from "lucide-react";

import { NavMain } from "@/components/nav-main";
import { NavProjects } from "@/components/nav-projects";
import { NavUser } from "@/components/nav-user";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar";

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const location = useLocation();

  const data = {
    user: {
      name: "Admin User",
      email: "admin@company.com",
      avatar: "/avatars/admin.jpg",
    },
    navMain: [
      {
        title: "Dashboard",
        url: "/",
        icon: BarChart3,
        isActive: location.pathname === "/",
        items: [
          {
            title: "Overview",
            url: "/",
          },
        ],
      },
      {
        title: "Attendance",
        url: "#",
        icon: Clock,
        isActive: location.pathname.startsWith("/attendance"),
        items: [
          {
            title: "Clock In/Out",
            url: "/attendance/clock",
          },
          {
            title: "History",
            url: "/attendance/history",
          },
          {
            title: "Time Correction",
            url: "/attendance/time-correction",
          },
          {
            title: "Summary",
            url: "/attendance/summary",
          },
        ],
      },
      {
        title: "Departments",
        url: "#",
        icon: Building2,
        isActive: location.pathname.startsWith("/departments"),
        items: [
          {
            title: "View All",
            url: "/departments",
          },
          {
            title: "Add New",
            url: "/departments/edit",
          },
        ],
      },
      {
        title: "Emergency Contacts",
        url: "#",
        icon: Phone,
        isActive: location.pathname.startsWith("/emergency-contacts"),
        items: [
          {
            title: "View All",
            url: "/emergency-contacts",
          },
          {
            title: "Add New",
            url: "/emergency-contacts/edit",
          },
        ],
      },
      {
        title: "Employee Management",
        url: "#",
        icon: Users,
        isActive:
          location.pathname.includes("employee") ||
          location.pathname.includes("user"),
        items: [
          {
            title: "Employee Hierarchy",
            url: "/employee-hierarchy",
          },
          {
            title: "User Management",
            url: "/user-management",
          },
        ],
      },
      {
        title: "Shift Patterns",
        url: "#",
        icon: Calendar,
        isActive: location.pathname.startsWith("/shift-patterns"),
        items: [
          {
            title: "View All",
            url: "/shift-patterns",
          },
          {
            title: "Add New",
            url: "/shift-patterns/edit",
          },
        ],
      },
      {
        title: "System",
        url: "#",
        icon: Settings,
        isActive: location.pathname.startsWith("/system"),
        items: [
          {
            title: "System Logs",
            url: "/system-logs",
          },
        ],
      },
    ],
    projects: [],
  };

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild>
              <Link to="/">
                <div className="bg-sidebar-primary text-sidebar-primary-foreground flex aspect-square size-8 items-center justify-center rounded-lg">
                  <GalleryVerticalEnd className="size-4" />
                </div>
                <div className="flex flex-col gap-0.5 leading-none">
                  <span className="font-medium">TimeTracker</span>
                  <span className="">v1.0.0</span>
                </div>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={data.navMain} />
        <NavProjects projects={data.projects} />
      </SidebarContent>
      <SidebarFooter>
        <NavUser user={data.user} />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
