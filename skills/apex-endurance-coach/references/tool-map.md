# APEX Tool Map

## Singleton context

Use these first when you need stable user context.

- `profile_documents(operation="get" | "set", document="profile")`
  - Main user profile markdown
  - Use for identity, endurance background, stable personal context
- `user_data(operation="get" | "set", ...)`
  - `weight_kg`, `height_cm`, `ftp_watts`
  - Use for body metrics and cycling threshold power
- `profile_documents(operation="get" | "set", document="diet_preferences")`
  - Stable food likes, dislikes, restrictions, fueling habits
- `profile_documents(operation="get" | "set", document="diet_goals")`
  - Narrative diet goals
- `profile_documents(operation="get" | "set", document="training_goals")`
  - Narrative training goals

## Product catalog

Use these before inventing a new food entry.

- `products(operation="list")`
  - Check whether a reusable food already exists
- `products(operation="get", product_id=...)`
  - Inspect one product in detail
- `products(operation="add", ...)`
  - Create a reusable food with per-100g macros
- `products(operation="update", product_id=..., ...)`
  - Correct or refine reusable product data
- `products(operation="delete", product_id=...)`
  - Remove a bad or duplicate product

## Daily planning

Use these for the planned target of a day.

- `daily_targets(operation="list", ...)`
  - Review multiple days
- `daily_targets(operation="get", target_date=...)`
  - Inspect one day's target
- `daily_targets(operation="set", target_date=..., ...)`
  - Create or replace the day's planned food calories, exercise calories, and macros
- `daily_targets(operation="delete", target_date=...)`
  - Remove a target when it is no longer valid

## Meals and meal items

Use meal headers as containers, then meal items as the actual logged foods.

- `meals(operation="list", meal_date=...)`
  - Find meals for a day
- `meals(operation="get", meal_id=...)`
  - Inspect one meal header
- `meals(operation="add", ...)`
  - Create a meal container such as `breakfast`, `post-ride`, or `dinner`
- `meals(operation="update", meal_id=..., ...)`
  - Rename or adjust the date/notes of a meal
- `meals(operation="delete", meal_id=...)`
  - Remove a meal header and its item list

- `meal_items(operation="list", meal_id=...)`
  - Read the foods inside one meal
- `meal_items(operation="add", meal_id=..., ...)`
  - Log one ingredient or product
  - Use `product_id` whenever possible
  - Otherwise provide manual calories and macros
- `meal_items(operation="update", meal_item_id=..., meal_id=..., ...)`
  - Correct a logged item
- `meal_items(operation="delete", meal_item_id=...)`
  - Remove an incorrect item

### Meal logging playbook

1. Resolve the date and meal label
2. Create the meal if it does not exist
3. Look in `products(operation="list")` for a reusable match
4. Add the meal item
5. Call `get_daily_summary`
6. Explain current vs target and remaining values

## Activities

Use these for logged or imported training sessions.

- `activities(operation="list", ...)`
  - Filter by date range or external source
- `activities(operation="get", activity_id=...)`
  - Inspect one session
- `activities(operation="add", ...)`
  - Log a new session or store a synced upstream activity
- `activities(operation="update", activity_id=..., ...)`
  - Correct metrics or metadata
- `activities(operation="delete", activity_id=...)`
  - Remove a bad session

### Activity notes

- `external_source` and `external_activity_id` are for sync-safe upstream identity
- JSON fields such as `zones`, `laps`, `streams`, and `raw_payload` can hold richer provider data
- Do not claim Strava is connected unless data is actually present or the user says so

## Memory

Use memory for durable, high-value facts.

- `memory_items(operation="list", ...)`
  - Review durable context, optionally by category
- `memory_items(operation="get", memory_item_id=...)`
  - Inspect one saved memory
- `memory_items(operation="add", ...)`
  - Save a durable fact or decision
- `memory_items(operation="update", memory_item_id=..., ...)`
  - Refine a saved memory
- `memory_items(operation="delete", memory_item_id=...)`
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
