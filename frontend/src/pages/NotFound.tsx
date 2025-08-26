import { Link } from "react-router-dom";
import { ROUTES } from "../routes/paths";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Search, Home } from "lucide-react";
import { useState } from "react";

export default function NotFound() {
  const [searchQuery, setSearchQuery] = useState<string>("");

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      // Redirect to a search results page or dashboard with query
      window.location.href = `${ROUTES.DASHBOARD}?search=${encodeURIComponent(
        searchQuery
      )}`;
    }
  };

  return (
    <div className="flex min-h-svh flex-col items-center justify-center p-4 md:p-6 bg-background text-foreground">
      <div className="text-center space-y-6 max-w-md">
        <div className="relative mx-auto w-64 h-64">
          <svg
            viewBox="0 0 200 200"
            className="w-full h-full text-muted-foreground"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <circle cx="100" cy="100" r="80" strokeOpacity="0.2" />
            <text
              x="50%"
              y="50%"
              textAnchor="middle"
              dy=".3em"
              fontSize="60"
              fontWeight="bold"
              fill="currentColor"
            >
              404
            </text>
            <path
              d="M60 120 Q100 140 140 120"
              stroke="currentColor"
              strokeOpacity="0.5"
            />
            <circle cx="80" cy="110" r="5" fill="currentColor" />
            <circle cx="120" cy="110" r="5" fill="currentColor" />
          </svg>
        </div>
        <h1 className="text-3xl font-bold">Page Not Found</h1>
        <p className="text-muted-foreground">
          The page you are looking for does not exist or has been moved.
        </p>
        <form onSubmit={handleSearch} className="flex gap-2">
          <Input
            type="text"
            placeholder="Search for something else..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="max-w-xs"
          />
          <Button type="submit" variant="outline">
            <Search className="h-4 w-4 mr-2" />
            Search
          </Button>
        </form>
        <Button asChild className="mt-4">
          <Link to={ROUTES.DASHBOARD}>
            <Home className="h-4 w-4 mr-2" />
            Go to Dashboard
          </Link>
        </Button>
      </div>
    </div>
  );
}
