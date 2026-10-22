// Allowed attachments (compare in lowercase)
export const ALLOWED_EXTENSIONS = [".geojson"];

// Placeholder: confirm the real limit with the backend
export const MAX_FILE_SIZE_MB = 5;
export const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;

export const MAX_MESSAGE_LENGTH = 2000;

// Dates in the future cannot be searched (change to true if they can)
export const ALLOW_FUTURE_DATES = false;

// Shared by the "+" menu item and the modal so the id can't be mistyped
export const DATE_MODAL_ID = "date-modal";

// The backend waits 35 s for the agent, so the page waits a little longer
export const REQUEST_TIMEOUT_MS = 40000;

// After this many seconds the indicator tells the user it is taking longer
export const SLOW_RESPONSE_SECONDS = 15;

export const WELCOME_MESSAGE = `Hello! Tell me what you are looking for, attach a file (${ALLOWED_EXTENSIONS.join(", ")}, a single Polygon only), and choose a date or date range. Then press Send.`;// At this width and above, the sidebar starts open and has no dark backdrop
export const SIDEBAR_DESKTOP_QUERY = "(min-width: 1200px)";

// Links the toggle arrow to the sidebar (aria-controls)
export const SIDEBAR_ID = "app-sidebar";

// Links the sidebar's New Chat button to its confirmation modal
export const NEW_CHAT_MODAL_ID = "new-chat-modal";