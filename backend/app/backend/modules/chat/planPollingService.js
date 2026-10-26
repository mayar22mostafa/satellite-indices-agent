const { getPlanResult } = require("../agent/agentService");
const { updateAnalysisPlanStatus } = require("./chatRepository");
const { publishPlanUpdate } = require("./planEventService");

const activePolls = new Set();

const wait = (milliseconds) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));

const startPlanPolling = (planId) => {
  if (activePolls.has(planId)) {
    return;
  }

  activePolls.add(planId);

  (async () => {
    let previousStatus = null;
    const pollingInterval = 2000;
    const maxDuration = 10 * 60 * 1000;
    const startTime = Date.now();

    try {
      while (Date.now() - startTime < maxDuration) {
        const response = await getPlanResult(planId);
        const { status } = response;

        // Save the Agent's actual status in PostgreSQL.
        if (["Running", "Done", "Failed"].includes(status)) {
          await updateAnalysisPlanStatus(
            planId,
            status,
            status === "Done" ? response.result : undefined
          );
        }

        const statusChanged = status !== previousStatus;
        const finalResultReady =
          status === "Done" && response.result !== undefined;

        if (statusChanged || finalResultReady) {
          publishPlanUpdate(planId, {
            ...response,
            plan_id: response.plan_id || planId,
          });

          previousStatus = status;
        }

        if (status === "Done" || status === "Failed") {
          return;
        }

        await wait(pollingInterval);
      }

      publishPlanUpdate(planId, {
        plan_id: planId,
        status: "error",
        message: "Analysis monitoring timed out",
      });
    } catch (error) {
      console.error(`Polling failed for plan ${planId}:`, error.message);

      publishPlanUpdate(planId, {
        plan_id: planId,
        status: "error",
        message: error.message || "Could not retrieve analysis status",
      });
    } finally {
      activePolls.delete(planId);
    }
  })();
};

module.exports = {
  startPlanPolling,
};
