import { Moon, Sun } from "lucide-react";
import { useTheme } from "../theme";

export default function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const next = theme === "dark" ? "Daylight" : "Lantern";
  return (
    <button
      className="theme-toggle"
      onClick={toggle}
      aria-label={`Switch to ${next} mode`}
      data-tip={`${next} mode`}
      aria-pressed={theme === "dark"}
    >
      <span className="tt-stars">
        <i />
        <i />
        <i />
      </span>
      <span className="tt-knob">{theme === "dark" ? <Moon size={14} /> : <Sun size={14} />}</span>
    </button>
  );
}
