import { Link } from "react-router-dom";
import { ROUTES } from "../routes/paths";

export default function NotFound() {
  return (
    <div style={{ padding: "2rem", textAlign: "center" }}>
      <h1>404 - Page Not Found</h1>
      <p>The page you are looking for does not exist.</p>
      <Link to={ROUTES.DASHBOARD}>Go to Dashboard</Link>
    </div>
  );
}
