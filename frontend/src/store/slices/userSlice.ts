import { createSlice } from '@reduxjs/toolkit';
import type { PayloadAction } from '@reduxjs/toolkit';
import type { PaginatedResponse, User, UserRole, UserDepartment } from '@/api/types';

interface UserState {
  users: PaginatedResponse<User> | null;
  roles: UserRole[];
  departments: UserDepartment[];
}

const initialState: UserState = {
  users: null,
  roles: [],
  departments: [],
};

const userSlice = createSlice({
  name: 'user',
  initialState,
  reducers: {
    setUsers: (state, action: PayloadAction<PaginatedResponse<User>>) => {
      state.users = action.payload;
    },
    setRoles: (state, action: PayloadAction<UserRole[]>) => {
      state.roles = action.payload;
    },
    setUserDepartments: (state, action: PayloadAction<UserDepartment[]>) => {
      state.departments = action.payload;
    },
  },
});

export const { setUsers, setRoles, setUserDepartments } = userSlice.actions;
export default userSlice.reducer;