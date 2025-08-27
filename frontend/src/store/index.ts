import { configureStore } from '@reduxjs/toolkit';
import authReducer from './slices/authSlice';
import attendanceReducer from './slices/attendanceSlice';
import userReducer from './slices/userSlice';
import hierarchyReducer from './slices/hierarchySlice';

const store = configureStore({
  reducer: {
    auth: authReducer,
    attendance: attendanceReducer,
    user: userReducer,
    hierarchy: hierarchyReducer,
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;

export default store;