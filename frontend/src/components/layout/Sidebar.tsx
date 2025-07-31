import * as React from 'react';
import { useSelector } from 'react-redux';
import type { RootState } from '@/store';
import { NavMain } from '@/components/nav-main';
import { NavUser } from '@/components/nav-user';
import { TeamSwitcher } from '@/components/team-switcher';
import { Sidebar, SidebarContent, SidebarFooter, SidebarHeader, SidebarRail } from '@/components/ui/sidebar';
import { Briefcase, Calendar, Users, Clock, FileText, Settings, UserCog } from 'lucide-react';

function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const user = useSelector((state: RootState) => state.auth.user);

  const navItems = [
    {
      title: 'Dashboard',
      url: '/',
      icon: Briefcase,
      isActive: true,
    },
    {
      title: 'Attendance',
      url: '/attendance/clock',
      icon: Clock,
      items: [
        { title: 'Clock In/Out', url: '/attendance/clock' },
        { title: 'History', url: '/attendance/history' },
        { title: 'Time Correction', url: '/attendance/time-correction' },
        { title: 'Summary', url: '/attendance/summary' },
      ],
    },
    ...(user?.permissions.includes('manage_departments')
      ? [
          {
            title: 'Departments',
            url: '/departments',
            icon: Users,
            items: [{ title: 'List', url: '/departments' }, { title: 'Add/Edit', url: '/departments/edit' }],
          },
        ]
      : []),
    ...(user?.permissions.includes('manage_employees')
      ? [
          {
            title: 'Emergency Contacts',
            url: '/emergency-contacts',
            icon: FileText,
            items: [
              { title: 'List', url: '/emergency-contacts' },
              { title: 'Add/Edit', url: '/emergency-contacts/edit' },
            ],
          },
          {
            title: 'Shift Patterns',
            url: '/shift-patterns',
            icon: Calendar,
            items: [
              { title: 'List', url: '/shift-patterns' },
              { title: 'Add/Edit', url: '/shift-patterns/edit' },
            ],
          },
          { title: 'Employee Hierarchy', url: '/employee-hierarchy', icon: Users },
        ]
      : []),
    ...(user?.permissions.includes('view_logs')
      ? [{ title: 'System Logs', url: '/system-logs', icon: Settings }]
      : []),
    ...(user?.permissions.includes('manage_users')
      ? [{ title: 'User Management', url: '/user-management', icon: UserCog }]
      : []),
  ];

  const teams = [
    { name: 'Employee Management', logo: Briefcase, plan: 'Enterprise' },
  ];

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <TeamSwitcher teams={teams} />
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={navItems} />
      </SidebarContent>
      <SidebarFooter>
        <NavUser user={{ name: user?.first_name || '', email: user?.email || '', avatar: '' }} />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}

export default AppSidebar;