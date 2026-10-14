const axios = require("axios");
const AppError = require("../../utils/AppError");

const sendMsgToAgent = async ({
    message,
    date,
    startDate,
    endDate,
    conversationId,
    geojson,
}) => {
    try {
        const response = await axios.post(`${process.env.AGENT_URL}/agent/chat`,
            {
                message,
                date,
                startDate,
                endDate,
                conversationId,
                geojson,
            },
            {
                timeout: 30000,
            }
        );

        return response.data;
    } catch (error) {
        if (
            error.code === "ECONNABORTED" ||
            error.code === "ETIMEDOUT"
        ) {
            throw new AppError(
                "Agent request timed out",
                504
            );
        }

        if (error.response) {
            throw new AppError(
                "Agent service returned an error",
                502
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
};
