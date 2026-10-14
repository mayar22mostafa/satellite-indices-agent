import { formatDateRange } from "../utils/dateUtils";

const REPLY_DELAY_MS = 1800;

// TEMPORARY: stands in for the real agent until Sprint 2 (Socket.IO)
export const askMockAgent = ({ file, date }) =>
  new Promise((resolve) => {
    setTimeout(() => {
      const parts = [];
      if (file) parts.push(`the file ${file.name}`);
      if (date) parts.push(`the date ${formatDateRange(date)}`);
      const received = parts.length > 0 ? ` along with ${parts.join(" and ")}` : "";
      resolve(
        `Thanks! I received your request${received}. (This is a test reply: the real agent connects in Sprint 2.)`,
      );
    }, REPLY_DELAY_MS);
  });