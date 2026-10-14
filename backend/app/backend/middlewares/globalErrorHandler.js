const globalErrorHandler = (err, req, res, next) => {
  const statusCode = err.statusCode || 500;

  if (statusCode >= 500) {
    console.error("Server Error:", err);
  }

  const message =
    statusCode >= 500 && !err.isOperational
      ? "Internal Server Error"
      : err.message;

  return res.status(statusCode).json({
    status: "error",
    message,
  });
};

module.exports = globalErrorHandler;
