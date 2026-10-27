require("dotenv").config();
const { testConnection } = require("./config/db");

testConnection();

const express = require("express");
const cors = require("cors");
const globalErrorHandler = require("./middlewares/globalErrorHandler");

const app = express();

const allowedOrigins = (process.env.CORS_ORIGIN || "http://localhost:5173")
  .split(",")
  .map((origin) => origin.trim())
  .filter(Boolean);

app.use(cors({ origin: allowedOrigins }));
app.use(express.json());

const chatRoutes = require("./modules/chat/chatRoutes");
app.use("/chat", chatRoutes)

app.use(globalErrorHandler);

module.exports = app;