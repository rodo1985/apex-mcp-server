# APEX Tool Map

## Singleton context

Use these first when you need stable user context.

- `get_profile` / `set_profile`
  - Main user profile markdown
  - Use for identity, endurance background, stable personal context
- `get_user_data` / `set_user_data`
  - `weight_kg`, `height_cm`, `ftp_watts`
  - Use for body metrics and cycling threshold power
- `get_diet_preferences` / `set_diet_preferences`
  - Stable food likes, dislikes, restrictions, fueling habits
- `get_diet_goals` / `set_diet_goals`
  - Narrative diet goals
- `get_training_goals` / `set_training_goals`
  - Narrative training goals

## Product catalog

Use these before inventing a new food entry.

- `list_products`
  - Check whether a reusable food already exists
- `get_product`
  - Inspect one product in detail
- `add_product`
  - Create a reusable food with per-100g macros
- `update_product`
  - Correct or refine reusable product data
- `delete_product`
  - Remove a bad or duplicate product

## Daily planning

Use these for the planned target of a day.

- `list_daily_targets`
  - Review multiple days
- `get_daily_target`
  - Inspect one day's target
- `set_daily_target`
  - Create or replace the day's planned food calories, exercise calories, and macros
- `delete_daily_target`
  - Remove a target when it is no longer valid

## Meals and meal items

Use meal headers as containers, then meal items as the actual logged foods.

- `list_daily_meals`
  - Find meals for a day
- `get_meal`
  - Inspect one meal header
- `add_meal`
  - Create a meal container such as `breakfast`, `post-ride`, or `dinner`
- `update_meal`
  - Rename or adjust the date/notes of a meal
- `delete_meal`
  - Remove a meal header and its item list

- `list_meal_items`
  - Read the foods inside one meal
- `add_meal_item`
  - Log one ingredient or product
  - Use `product_id` whenever possible
  - Otherwise provide manual calories and macros
- `update_meal_item`
  - Correct a logged item
- `delete_meal_item`
  - Remove an incorrect item

### Meal logging playbook

1. Resolve the date and meal label
2. Create the meal if it does not exist
3. Look in `list_products` for a reusable match
4. Add the meal item
5. Call `get_daily_summary`
6. Explain current vs target and remaining values

## Activities

Use these for logged or imported training sessions.

- `list_activities`
  - Filter by date range or external source
- `get_activity`
  - Inspect one session
- `add_activity`
  - Log a new session or store a synced upstream activity
- `update_activity`
  - Correct metrics or metadata
- `delete_activity`
  - Remove a bad session

### Activity notes

- `external_source` and `external_activity_id` are for sync-safe upstream identity
- JSON fields such as `zones`, `laps`, `streams`, and `raw_payload` can hold richer provider data
- Do not claim Strava is connected unless data is actually present or the user says so

## Memory

Use memory for durable, high-value facts.

- `list_memory_items`
  - Review durable context, optionally by category
- `get_memory_item`
  - Inspect one saved memory
- `add_memory_item`
  - Save a durable fact or decision
- `update_memory_item`
  - Refine a saved memory
- `delete_memory_item`
  - Remove stale or incorrect memory

## Daily summary

- `get_daily_summary(target_date)`
  - Best single tool for "how did today go?"
  - Returns both target and actual values for:
    - food calories
    - exercise calories
    - protein
    - carbs
    - fat
  - Also returns:
    - `net_calories`
    - `meals_count`
    - `meal_items_count`
    - `activities_count`

### Remaining calculation

When a target exists:

- `remaining_food_calories = target_food_calories - actual_food_calories`
- `remaining_protein_g = target_protein_g - actual_protein_g`
- `remaining_carbs_g = target_carbs_g - actual_carbs_g`
- `remaining_fat_g = target_fat_g - actual_fat_g`

Say clearly when the user is over target instead of presenting negative numbers without explanation.

## Common request playbooks

### "Help me set up my profile"

1. Read all singleton documents and user data
2. Identify the missing pieces
3. Ask focused onboarding questions
4. Save answers immediately in the correct singleton tools

### "Log this meal"

1. Resolve date and meal label
2. Reuse product catalog if possible
3. Log the item
4. Summarize current vs target for the day

### "What should I eat later?"

1. Read singleton context
2. Read `get_daily_summary`
3. Use product catalog first
4. Recommend a meal or snack that closes the most important remaining gaps

### "Plan today"

1. Read singleton context
2. Ask for planned training if it is missing
3. Create or confirm the daily target
4. Recommend meals and fueling around that target

### "How did today go?"

1. Call `get_daily_summary`
2. Explain target vs actual
3. Highlight the biggest gap or success
4. Suggest the next most useful action
