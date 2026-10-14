// What the user still has to provide before the message can be sent
export const getMissingItems = ({ text, file, date, isFirstMessage }) => {
  const missing = [];
  if (text.trim() === "") missing.push("a message");
  if (isFirstMessage && !file) missing.push("a file");
  if (isFirstMessage && !date) missing.push("a date");
  return missing;
};

// ["a message", "a file", "a date"] -> "a message, a file and a date"
export const joinWithAnd = (items) => {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
};