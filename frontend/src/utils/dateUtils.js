import { ALLOW_FUTURE_DATES } from "../config/constants";

// Today as "YYYY-MM-DD" in the user's own time zone
export const getTodayISO = () => {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
};

// "2026-10-01" -> "1 Oct 2026" (parsed by parts so the time zone can't shift the day)
export const formatDate = (iso) => {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString([], {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
};

export const formatDateRange = ({ from, to }) =>
  from === to ? formatDate(from) : `${formatDate(from)} – ${formatDate(to)}`;

// Returns an error message, or null when the selection is valid
export const validateDateSelection = ({ mode, from, to }) => {
  const today = getTodayISO();

  if (!from) {
    return mode === "range" ? "Choose a start date." : "Choose a date.";
  }
  if (mode === "range" && !to) {
    return "Choose an end date.";
  }
  if (mode === "range" && to < from) {
    return "The end date can't be before the start date.";
  }
  if (!ALLOW_FUTURE_DATES && (from > today || (mode === "range" && to > today))) {
    return "Dates in the future are not available.";
  }
  return null;
};