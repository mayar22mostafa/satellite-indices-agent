const Joi = require("joi");

const chatSchema = Joi.object({
  message: Joi.string()
    .trim()
    .required(),

  image_date: Joi.date()
    .iso()
    .optional(),

  start_date: Joi.date()
    .iso()
    .optional(),

  end_date: Joi.date()
    .iso()
    .optional(),

  session_id: Joi.string()
    .allow("", null)
    .optional(),
});

module.exports = chatSchema;