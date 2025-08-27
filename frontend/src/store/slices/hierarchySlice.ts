import { createSlice, type PayloadAction } from '@reduxjs/toolkit';
import type { EmployeeHierarchy } from '@/api/types';

interface HierarchyState {
    hierarchy: EmployeeHierarchy[];
}

const initialState: HierarchyState = {
    hierarchy: [],
};

const hierarchySlice = createSlice({
    name: 'hierarchy',
    initialState,
    reducers: {
        setHierarchy: (state, action: PayloadAction<EmployeeHierarchy[]>) => {
            state.hierarchy = action.payload;
        },
    },
});

export const { setHierarchy } = hierarchySlice.actions;
export default hierarchySlice.reducer;