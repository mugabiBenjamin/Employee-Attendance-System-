import { useSelector } from 'react-redux';
import type { RootState } from '@/store';
import { Button } from '@/components/ui/button';
import { clearAuth } from '@/store/slices/authSlice';
import { useDispatch } from 'react-redux';
import { useNavigate } from 'react-router-dom';

function Navbar() {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const user = useSelector((state: RootState) => state.auth.user);

  const handleLogout = () => {
    dispatch(clearAuth());
    navigate('/login');
  };

  return (
    <header className="flex items-center justify-between p-4 bg-background border-b">
      <h1 className="text-lg font-semibold">Employee Management System</h1>
      {user && (
        <div className="flex items-center gap-4">
          <span className="text-sm">{user.email}</span>
          <Button variant="destructive" onClick={handleLogout}>
            Log Out
          </Button>
        </div>
      )}
    </header>
  );
}

export default Navbar;