import {
  ALLOWED_EXTENSIONS,
  MAX_FILE_SIZE_BYTES,
  MAX_FILE_SIZE_MB,
} from "../config/constants";

export const getExtension = (fileName) => {
  const dotIndex = fileName.lastIndexOf(".");
  return dotIndex === -1 ? "" : fileName.slice(dotIndex).toLowerCase();
};

// Returns an error message, or null when the file is valid
export const validateFile = (file) => {
  const extension = getExtension(file.name);

  if (!ALLOWED_EXTENSIONS.includes(extension)) {
    return `"${file.name}" is not supported. Allowed types: ${ALLOWED_EXTENSIONS.join(", ")}`;
  }
  if (file.size === 0) {
    return `"${file.name}" is empty.`;
  }
  if (file.size > MAX_FILE_SIZE_BYTES) {
    return `"${file.name}" is too large. Maximum size is ${MAX_FILE_SIZE_MB} MB.`;
  }
  return null;
};