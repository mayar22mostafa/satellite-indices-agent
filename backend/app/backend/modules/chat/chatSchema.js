const Joi = require("joi");

const chatSchema = Joi.object({
  message: Joi.string()
    .trim()
    .required(),

  date: Joi.date()
    .iso()
    .optional(),

  startDate: Joi.date()
    .iso()
    .optional(),

  endDate: Joi.date()
    .iso()
    .optional(),

  session_id: Joi.string()
    .allow("", null)
    .optional(),
});

module.exports = chatSchema;