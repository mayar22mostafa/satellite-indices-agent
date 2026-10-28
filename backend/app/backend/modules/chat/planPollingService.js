const { getPlanResult } = require("../agent/agentService");
const { updateAnalysisPlanStatus } = require("./chatRepository");
const { publishPlanUpdate } = require("./planEventService");

const activePolls = new Set();

const wait = (milliseconds) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));

const startPlanPolling = (plan_id) => {
  if (activePolls.has(plan_id)) {
    return;
  }

  activePolls.add(plan_id);

  (async () => {
    let previousStatus = null;
    const pollingInterval = 2000;
    const maxDuration = 10 * 60 * 1000;
    const startTime = Date.now();

    try {
      while (Date.now() - startTime < maxDuration) {
        const response = await getPlanResult(plan_id);
        const { status } = response;

        // Save the Agent's actual status in PostgreSQL.
        if (["Running", "Done", "Failed"].includes(status)) {
          await updateAnalysisPlanStatus(
            plan_id,
            status,
            status === "Done" ? response.result : undefined
          );
        }

        const statusChanged = status !== previousStatus;
        const finalResultReady =
          status === "Done" && response.result !== undefined;

        if (statusChanged || finalResultReady) {
          publishPlanUpdate(plan_id, {
            ...response,
            plan_id: response.plan_id || plan_id,
          });

          previousStatus = status;
        }

        if (status === "Done" || status === "Failed") {
          return;
        }

        await wait(pollingInterval);
      }

      publishPlanUpdate(plan_id, {
        plan_id: plan_id,
        status: "error",
        message: "Analysis monitoring timed out",
      });
    } catch (error) {
      console.error(`Polling failed for plan ${plan_id}:`, error.message);

      publishPlanUpdate(planId, {
        plan_id: plan_id,
        status: "error",
        message: error.message || "Could not retrieve analysis status",
      });
    } finally {
      activePolls.delete(plan_id);
    }
  })();
};

module.exports = {
  startPlanPolling,
};
