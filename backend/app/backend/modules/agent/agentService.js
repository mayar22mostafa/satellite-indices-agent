const axios = require("axios");
const AppError = require("../../utils/AppError");

const sendMsgToAgent = async ({
    message,
    date,
    startDate,
    endDate,
    session_id,
    geojson,
}) => {
    try {
        const payload = {
            message,
        };

        if (date) payload.date = date;
        if (startDate) payload.startDate = startDate;
        if (endDate) payload.endDate = endDate;

        if (geojson) {
            payload.aoi = geojson;
        }
        if (session_id) {
            payload.session_id = session_id;
        }

        const response = await axios.post(
            `${process.env.AGENT_URL}/plans`,
            payload,
            { timeout: 35000 }
        );

        return response.data;
    } catch (error) {
        if (
            error.code === "ECONNABORTED" ||
            error.code === "ETIMEDOUT"
        ) {
            throw new AppError("Agent request timed out", 504);
        }

        if (error.response) {
            console.error("Agent API error:", error.response.data);
            throw new AppError(
                "Agent service returned an error",
                error.response.status >= 500 ? 502 : error.response.status
            );
        }

        if (error.request) {
            throw new AppError(
                "Could not connect to Agent service",
                503
            );
        }

        throw error;
    }
};

const approvePlan = async (planId) => {
  try {
    const response = await axios.post(
      `${process.env.AGENT_URL}/plans/${encodeURIComponent(planId)}/approve`,
      {},
      { timeout: 35000 }
    );

    return response.data;
  } catch (error) {
    if (error.code === "ECONNABORTED" || error.code === "ETIMEDOUT") {
      throw new AppError("Agent request timed out", 504);
    }

    if (error.response) {
      console.error("Agent API error:", error.response.data);

      throw new AppError(
        "Agent service returned an error",
        error.response.status >= 500 ? 502 : error.response.status
      );
    }

    if (error.request) {
      throw new AppError("Could not connect to Agent service", 503);
    }

    throw error;
  }
};
 

const getPlanResult = async (planId) => {
  try {
    const response = await axios.get(
      `${process.env.AGENT_URL}/plans/${encodeURIComponent(planId)}/result`,
      { timeout: 35000 }
    );

    return response.data;
  } catch (error) {
    if (
      error.code === "ECONNABORTED" ||
      error.code === "ETIMEDOUT"
    ) {
      throw new AppError("Agent request timed out", 504);
    }

    if (error.response) {
      console.error("Agent API error:", error.response.data);

      throw new AppError(
        "Agent service returned an error",
        error.response.status >= 500 ? 502 : error.response.status
      );
    }

    if (error.request) {
      throw new AppError(
        "Could not connect to Agent service",
        503
      );
    }

    throw error;
  }
};


module.exports = {
    sendMsgToAgent,
    approvePlan,
    getPlanResult
};
