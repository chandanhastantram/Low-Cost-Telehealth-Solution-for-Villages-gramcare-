import { Link } from "react-router-dom";
import ThemeToggle from "../components/ThemeToggle";
import { PaddyField } from "../ui/doodles";

export default function NotFound() {
  const signedIn = Boolean(localStorage.getItem("access_token"));
  return (
    <div className="lost">
      <div className="theme-float">
        <ThemeToggle />
      </div>
      <div>
        <PaddyField />
        <div className="big">404</div>
        <h2>This path ends in a paddy field</h2>
        <p>
          Lovely view, but no clinic here. The page you're after may have moved, or the link took a
          wrong turn at the banyan tree.
        </p>
        <Link className="btn btn-primary" to={signedIn ? "/dashboard" : "/login"}>
          Take me back to the village
        </Link>
      </div>
    </div>
  );
}
