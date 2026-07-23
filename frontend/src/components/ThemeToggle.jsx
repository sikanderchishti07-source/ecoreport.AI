import { useEffect, useState } from "react";
import { Monitor, Moon, Sun } from "lucide-react";
import { applyTheme, getTheme, setTheme, watchSystemTheme } from "@/lib/theme";

const OPTIONS = [
  { value: "light", label: "Light", Icon: Sun },
  { value: "dark", label: "Dark", Icon: Moon },
  { value: "system", label: "System", Icon: Monitor },
];

export default function ThemeToggle() {
  const [theme, setLocal] = useState(getTheme());

  useEffect(() => {
    applyTheme(theme);
    return watchSystemTheme();
  }, [theme]);

  const choose = (value) => {
    setTheme(value);
    setLocal(value);
  };

  return (
    <div
      className="hidden md:flex items-center gap-0.5 border border-border rounded-sm p-0.5 bg-secondary/40"
      role="group"
      aria-label="Colour theme"
    >
      {OPTIONS.map(({ value, label, Icon }) => (
        <button
          key={value}
          onClick={() => choose(value)}
          title={label}
          aria-label={label}
          aria-pressed={theme === value}
          data-testid={`theme-${value}`}
          className={`h-7 w-7 inline-flex items-center justify-center rounded-sm transition-colors ${
            theme === value
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground hover:text-foreground hover:bg-accent"
          }`}
        >
          <Icon className="w-3.5 h-3.5" />
        </button>
      ))}
    </div>
  );
}
