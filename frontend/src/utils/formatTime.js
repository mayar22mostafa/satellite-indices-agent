/**
 * Formats a timestamp for chat messages so that:
 * - Messages from today show the current time (e.g. "Today, 10:30 AM" or "10:30 AM")
 * - Messages from yesterday show "Yesterday, 10:30 AM"
 * - Past messages show their original date and time (e.g. "Oct 25, 10:30 AM")
 * 
 * @param {number|string|Date} timestamp - Milliseconds since epoch or Date object
 * @returns {string} Formatted date and time string
 */
export const formatTime = (timestamp) => {
  if (!timestamp) return "";
  const date = new Date(timestamp);
  if (isNaN(date.getTime())) return "";

  const now = new Date();
  const timeStr = date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

  const isToday = date.toDateString() === now.toDateString();
  if (isToday) {
    return timeStr;
  }

  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (date.toDateString() === yesterday.toDateString()) {
    return `Yesterday, ${timeStr}`;
  }

  const isSameYear = date.getFullYear() === now.getFullYear();
  const dateStr = date.toLocaleDateString([], {
    month: "short",
    day: "numeric",
    year: isSameYear ? undefined : "numeric",
  });

  return `${dateStr}, ${timeStr}`;
};