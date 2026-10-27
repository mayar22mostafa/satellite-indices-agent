import { createSlice } from "@reduxjs/toolkit";

const getSavedTheme = () => {
  try {
    const saved = localStorage.getItem("egsa-theme");
    if (saved === "dark" || saved === "light") {
      return saved;
    }
  } catch {
    // ignore localStorage errors
  }
  return "dark"; // Dark mode by default
};

const initialTheme = getSavedTheme();

// Apply theme to document element immediately
if (typeof document !== "undefined") {
  document.documentElement.setAttribute("data-theme", initialTheme);
  document.documentElement.setAttribute("data-bs-theme", initialTheme);
}

const themeSlice = createSlice({
  name: "theme",
  initialState: {
    mode: initialTheme,
  },
  reducers: {
    toggleTheme: (state) => {
      const nextTheme = state.mode === "dark" ? "light" : "dark";
      state.mode = nextTheme;
      try {
        localStorage.setItem("egsa-theme", nextTheme);
      } catch {
        // ignore
      }
      if (typeof document !== "undefined") {
        document.documentElement.setAttribute("data-theme", nextTheme);
        document.documentElement.setAttribute("data-bs-theme", nextTheme);
      }
    },
    setTheme: (state, action) => {
      const nextTheme = action.payload === "light" ? "light" : "dark";
      state.mode = nextTheme;
      try {
        localStorage.setItem("egsa-theme", nextTheme);
      } catch {
        // ignore
      }
      if (typeof document !== "undefined") {
        document.documentElement.setAttribute("data-theme", nextTheme);
        document.documentElement.setAttribute("data-bs-theme", nextTheme);
      }
    },
  },
});

export const { toggleTheme, setTheme } = themeSlice.actions;

export const selectThemeMode = (state) => state.theme.mode;

export default themeSlice.reducer;
