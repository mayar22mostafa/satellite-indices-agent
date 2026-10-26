
const clients = new Map();
const latestUpdates = new Map();

const publishPlanUpdate = (planId, update) => {
  // Save the latest update for this plan
  latestUpdates.set(planId, update);

  // Send the update to all connected clients
  const planClients = clients.get(planId);

  if (!planClients) {
    return;
  }

  const event = `data: ${JSON.stringify(update)}\n\n`;

  for (const client of planClients) {
    if (!client.writableEnded) {
      client.write(event);
    }
  }
};

const subscribeToPlan = (planId, res) => {
  // Configure the response as an SSE connection
  res.status(200);
  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache, no-transform");
  res.setHeader("Connection", "keep-alive");
  res.flushHeaders();

  // Register this client for the requested plan
  if (!clients.has(planId)) {
    clients.set(planId, new Set());
  }

  clients.get(planId).add(res);

  // Send the latest status immediately, if available
  const latestUpdate = latestUpdates.get(planId);

  if (latestUpdate) {
    res.write(`data: ${JSON.stringify(latestUpdate)}\n\n`);
  }

  // Remove the client when its connection closes
  res.on("close", () => {
    const planClients = clients.get(planId);

    if (planClients) {
      planClients.delete(res);

      if (planClients.size === 0) {
        clients.delete(planId);
      }
    }
  });
};

module.exports = {
  publishPlanUpdate,
  subscribeToPlan,
};
